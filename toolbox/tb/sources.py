"""Find and import existing designs, keeping attribution with every file.

Only services whose terms allow programmatic access are queried:
  OSHWA certification API   https://certificationapi.oshwa.org/documentation
  KiCad libraries (GitLab)  https://docs.gitlab.com/api/repositories/  (repository tree, public, no token)
  GitHub search             https://docs.github.com/en/rest/search/search
  EPO Open Patent Services  https://www.epo.org/en/searching-for-patents/data/web-services/ops
                            (OpenAPI: http://ops.epo.org/wsdl/ops.yaml)
Model-sharing sites that do not permit automated access are never fetched: design_links only
builds search URLs for a person to open.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import ipaddress
import os
import re
import socket
import time
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

from . import common
from .common import DATA, inside, load_json, save_json

TIMEOUT_S = 20.0
MAX_BYTES = 50 * 1024 * 1024
MAX_REDIRECTS = 5
FETCH_EXT = {".step", ".stp", ".stl", ".3mf", ".dxf", ".svg"}
# Servers label CAD files loosely, so this list only exists to turn away web pages and other clear mismatches.
_CONTENT_TYPES = ("application/octet-stream", "binary/octet-stream", "model/", "application/step", "application/sla",
                  "application/vnd.ms-pki.stl", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
                  "application/zip", "image/svg+xml", "image/vnd.dxf", "application/dxf", "text/plain",
                  "application/xml", "text/xml")
KICAD_REPOS = {
    "symbol": ("kicad/libraries/kicad-symbols", (".kicad_sym",)),
    "footprint": ("kicad/libraries/kicad-footprints", (".kicad_mod",)),
    "3d-model": ("kicad/libraries/kicad-packages3D", (".step", ".stp", ".wrl")),
}
KICAD_LICENCE = "CC-BY-SA-4.0 with the KiCad library exception (free use in designs; attribution and share-alike only when redistributing the libraries)"
KICAD_LICENCE_URL = "https://www.kicad.org/libraries/license/"
SOURCES = ("oshwa", "kicad", "github", "epo")
KEYS = {
    "oshwa": (("OSHWA_API_TOKEN",), "https://certificationapi.oshwa.org/ (free token: sign up on that page)"),
    "epo": (("EPO_OPS_KEY", "EPO_OPS_SECRET"), "https://developers.epo.org/user/register (free; create an app for the consumer key and secret)"),
}

_transport: httpx.BaseTransport | None = None  # tests swap in httpx.MockTransport
_ops_token: dict = {}


def _client(**kw) -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, transport=_transport,
                        headers={"User-Agent": "3d-agent-toolbox"}, **kw)


def _tokens(query: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", query.lower()) if t]


def _hit(title: str, url: str, licence: str, source: str, formats: list[str], **extra) -> dict:
    return {"title": title, "url": url, "licence": licence, "source": source, "file_formats": formats, **extra}


# ---------------------------------------------------------------- OSHWA

def _search_oshwa(c: httpx.Client, query: str, limit: int) -> list[dict]:
    r = c.get("https://certificationapi.oshwa.org/api/projects", params={"q": query, "limit": limit},
              headers={"Authorization": f"Bearer {os.environ['OSHWA_API_TOKEN']}"})
    r.raise_for_status()
    out = []
    for p in r.json().get("items", [])[:limit]:
        out.append(_hit(p.get("projectName", ""), p.get("documentationUrl") or p.get("projectWebsite") or "",
                        f"hardware {p.get('hardwareLicense')}; software {p.get('softwareLicense')}; docs {p.get('documentationLicense')}",
                        "oshwa", [], oshwa_uid=p.get("oshwaUid"), maker=p.get("responsibleParty"),
                        kind=p.get("primaryType"), description=(p.get("projectDescription") or "")[:300]))
    return out


# ---------------------------------------------------------------- KiCad libraries on GitLab

def _gitlab_tree(c: httpx.Client, repo: str, path: str = "", max_pages: int = 6) -> list[dict]:
    url = f"https://gitlab.com/api/v4/projects/{quote(repo, safe='')}/repository/tree"
    params: dict | None = {"per_page": 100, "pagination": "keyset", **({"path": path} if path else {})}
    rows: list[dict] = []
    for _ in range(max_pages):
        r = c.get(url, params=params)
        r.raise_for_status()
        rows += r.json()
        nxt = r.links.get("next", {}).get("url")
        if not nxt:
            break
        url, params = nxt, None
    return rows


def _search_kicad(c: httpx.Client, query: str, limit: int) -> list[dict]:
    """Library folders whose name matches any query word are opened; files must match every word."""
    toks = _tokens(query)
    out: list[dict] = []
    for kind, (repo, exts) in KICAD_REPOS.items():
        libs = [e for e in _gitlab_tree(c, repo) if e["type"] == "tree" and not e["name"].startswith(".")]
        norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
        # library folders are named by family ("Package_TO_SOT_SMD"), so match them on word fragments
        frags = {w for t in toks for w in re.findall(r"[a-z]{3,}|[a-z0-9]{4,}", t)} or set(toks)
        score = {e["name"]: sum(norm(w) in norm(e["name"]) for w in frags) for e in libs}
        picked = sorted((e for e in libs if score[e["name"]]), key=lambda e: -score[e["name"]])[:4]
        for lib in picked:
            for f in _gitlab_tree(c, repo, lib["path"], max_pages=4):
                name = f["name"]
                hay = norm(f["path"])
                if f["type"] != "blob" or not name.lower().endswith(exts) or not all(norm(t) in hay for t in toks):
                    continue
                out.append(_hit(name, f"https://gitlab.com/{repo}/-/raw/master/{quote(f['path'])}", KICAD_LICENCE, "kicad",
                                [Path(name).suffix.lstrip(".").lower()], kind=kind, library=lib["name"],
                                licence_url=KICAD_LICENCE_URL, page=f"https://gitlab.com/{repo}/-/blob/master/{quote(f['path'])}"))
                if sum(1 for h in out if h.get("kind") == kind) >= limit:
                    break
    return out[: limit * len(KICAD_REPOS)]


# ---------------------------------------------------------------- GitHub

def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return h


def _search_github(c: httpx.Client, query: str, limit: int) -> list[dict]:
    r = c.get("https://api.github.com/search/repositories", params={"q": query, "per_page": min(limit, 100)}, headers=_gh_headers())
    if r.status_code in (403, 429):
        reset = r.headers.get("x-ratelimit-reset")
        wait = f" Retry in {max(0, int(reset) - int(time.time()))} s." if reset and reset.isdigit() else ""
        raise RuntimeError("GitHub search rate limit reached (10 requests/min without a token)." + wait + " Set GITHUB_TOKEN for 30/min.")
    r.raise_for_status()
    out = [_hit(i["full_name"], i["html_url"], (i.get("license") or {}).get("spdx_id") or "none stated (all rights reserved by default)",
                "github", [], description=(i.get("description") or "")[:300], stars=i.get("stargazers_count"), topics=i.get("topics", []))
           for i in r.json().get("items", [])[:limit]]
    if os.environ.get("GITHUB_TOKEN"):  # code search needs authentication
        for ext in ("step", "stl"):
            r = c.get("https://api.github.com/search/code", params={"q": f"{query} in:path extension:{ext}", "per_page": min(limit, 30)},
                      headers=_gh_headers())
            if r.status_code != 200:
                break
            out += [_hit(i["path"], i["html_url"], "see the repository's LICENSE file", "github", [ext],
                         repository=i["repository"]["full_name"]) for i in r.json().get("items", [])[:limit]]
    return out


# ---------------------------------------------------------------- EPO Open Patent Services

def _ops_access_token(c: httpx.Client) -> str:
    """OAuth client-credentials flow: POST the key:secret pair as HTTP Basic, receive a short-lived bearer token."""
    if _ops_token.get("expires", 0) > time.time() + 30:
        return _ops_token["token"]
    pair = f"{os.environ['EPO_OPS_KEY']}:{os.environ['EPO_OPS_SECRET']}".encode()
    r = c.post("https://ops.epo.org/3.2/auth/accesstoken", data={"grant_type": "client_credentials"},
               headers={"Authorization": "Basic " + base64.b64encode(pair).decode()})
    if r.status_code in (400, 401):
        raise RuntimeError("EPO OPS rejected EPO_OPS_KEY / EPO_OPS_SECRET")
    r.raise_for_status()
    body = r.json()
    _ops_token.update(token=body["access_token"], expires=time.time() + float(body.get("expires_in", 1200)))
    return _ops_token["token"]


def _as_list(v) -> list:
    return v if isinstance(v, list) else [] if v is None else [v]


def _text(v, lang: str = "en") -> str:
    """OPS JSON holds text as {"$": "..."} objects, sometimes one per language."""
    items = _as_list(v)
    pick = next((i for i in items if isinstance(i, dict) and i.get("@lang") == lang), items[0] if items else None)
    if isinstance(pick, dict):
        inner = pick.get("p", pick)
        return " ".join(str(i.get("$", "")) if isinstance(i, dict) else str(i) for i in _as_list(inner)).strip()
    return str(pick or "")


def _search_epo(c: httpx.Client, query: str, limit: int) -> list[dict]:
    cql = query if re.search(r"\b(ti|ab|ta|txt|pa|in|pn|cpc|ipc)\s*=", query) else f'ta="{query}"'
    r = c.get("https://ops.epo.org/3.2/rest-services/published-data/search/biblio",
              params={"q": cql, "Range": f"1-{min(limit, 25)}"},
              headers={"Authorization": f"Bearer {_ops_access_token(c)}", "Accept": "application/json"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    search = r.json().get("ops:world-patent-data", {}).get("ops:biblio-search", {})
    out = []
    for wrap in _as_list(search.get("ops:search-result", {}).get("exchange-documents")):
        for d in _as_list(wrap.get("exchange-document")):
            num = f"{d.get('@country', '')}{d.get('@doc-number', '')}{d.get('@kind', '')}"
            out.append(_hit(_text(d.get("bibliographic-data", {}).get("invention-title")) or num,
                            f"https://worldwide.espacenet.com/patent/search?q=pn%3D{num}",
                            "patent document: free to read, but the invention may be protected. Check legal status before copying it",
                            "epo", ["pdf", "tiff"], publication=num, abstract=_text(d.get("abstract"))[:500],
                            drawings_api=f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{num}/images"))
    return out[:limit]


_SEARCHERS = {"oshwa": _search_oshwa, "kicad": _search_kicad, "github": _search_github, "epo": _search_epo}


def _missing_keys(source: str) -> list[str]:
    return [k for k in KEYS.get(source, ((), ""))[0] if not os.environ.get(k)]


def design_search(query: str, sources: str = "auto", limit: int = 10) -> dict:
    """Search open design sources. Returns results with title, url, licence, source and file_formats.

    sources: comma-separated from oshwa (certified open hardware; needs OSHWA_API_TOKEN), kicad (official
    symbol / footprint / 3D-model libraries), github (repositories; plus STEP/STL file search when
    GITHUB_TOKEN is set), epo (patent abstracts via Open Patent Services; needs EPO_OPS_KEY and
    EPO_OPS_SECRET; query may be CQL such as ti="hinge"). "auto" uses every source whose key is present.
    limit is per source. Per-source outcomes are in `status`. Use design_links for sites that need a person.
    """
    if not query.strip():
        return {"ok": False, "error": "query is empty"}
    want = list(SOURCES) if sources.strip().lower() in ("auto", "all", "") else [s.strip().lower() for s in sources.split(",") if s.strip()]
    unknown = [s for s in want if s not in SOURCES]
    if unknown:
        return {"ok": False, "error": f"Unknown source(s) {unknown}. Choose from {list(SOURCES)}"}
    limit = max(1, min(int(limit), 50))
    results, status = [], {}
    with _client() as c:
        for s in want:
            missing = _missing_keys(s)
            if missing:
                status[s] = {"ok": False, "error": f"Set {' and '.join(missing)}", "apply": KEYS[s][1]}
                continue
            try:
                found = _SEARCHERS[s](c, query, limit)
                results += found
                status[s] = {"ok": True, "results": len(found)}
            except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as e:
                status[s] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    ok = any(v["ok"] for v in status.values())
    out = {"ok": ok, "query": query, "count": len(results), "results": results, "status": status}
    if not ok:
        out["error"] = "No source could be searched: " + "; ".join(f"{k}: {v['error']}" for k, v in status.items())
    return out


# ---------------------------------------------------------------- fetch

def _resolve(host: str) -> list[str]:
    return sorted({i[4][0] for i in socket.getaddrinfo(host, None)})


def _public_https(url: str) -> str | None:
    """None if url is https to a public host, else the reason it is refused."""
    u = urlsplit(url)
    if u.scheme != "https" or not u.hostname:
        return "only https:// URLs are fetched"
    if u.username or u.password:
        return "URLs with embedded credentials are refused"
    try:
        ips = [u.hostname] if re.fullmatch(r"[0-9.]+|\[?[0-9a-fA-F:]+\]?", u.hostname) else _resolve(u.hostname)
    except OSError:
        return f"cannot resolve {u.hostname}"
    for ip in ips:
        a = ipaddress.ip_address(ip.strip("[]"))
        if not a.is_global:
            return f"{u.hostname} resolves to a non-public address ({ip})"
    return None


def _blocked_site(host: str) -> dict | None:
    for s in load_json(DATA / "make" / "design_sites.json", {}).get("sites", []):
        if any(host == h or host.endswith("." + h) for h in s["hosts"]):
            return s
    return None


def _raw_url(url: str) -> str:
    """Turn GitHub / GitLab file page links into their raw-file form."""
    m = re.match(r"https://github\.com/([^/]+/[^/]+)/blob/(.+)$", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}"
    return re.sub(r"^(https://gitlab\.com/.+?/-/)blob/", r"\1raw/", url)


def _looks_wrong(ext: str, head: bytes) -> str | None:
    text = head[:2048].lstrip().lower()
    if text.startswith((b"<!doctype html", b"<html")):
        return "the server sent a web page, not a design file"
    if ext in (".step", ".stp") and not text.startswith(b"iso-10303-21"):
        return "not a STEP file (missing ISO-10303-21 header)"
    if ext == ".3mf" and not head.startswith(b"PK"):
        return "not a 3MF file (not a zip archive)"
    if ext == ".svg" and b"<svg" not in text:
        return "not an SVG file"
    return None


def design_fetch(project: str, url: str, licence: str = "", title: str = "", name: str = "") -> dict:
    """Download a STEP/STL/3MF/DXF/SVG file into projects/<slug>/imports/ with an attribution sidecar.

    https only, 50 MB cap, public hosts only (redirects are re-checked), extension and content type checked.
    Pass the licence and title from design_search so they are recorded; the sidecar <file>.source.json keeps
    origin URL, licence, date and SHA-256. Sites that forbid automated downloads are refused: download those
    by hand and use cad_import. Returns the path to use in model.py.
    """
    try:
        d = common.project_dir(project)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}
    current = _raw_url(url.strip())
    try:
        with _client() as c:
            for _ in range(MAX_REDIRECTS + 1):
                bad = _public_https(current)
                if bad:
                    return {"ok": False, "error": f"Refused {current}: {bad}"}
                site = _blocked_site(urlsplit(current).hostname or "")
                if site:
                    return {"ok": False, "error": f"{site['name']} does not permit automated downloads. Open the page, download the file "
                                                  f"yourself, then import it with cad_import.", "open": url}
                with c.stream("GET", current) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        current = urljoin(current, r.headers["location"])
                        continue
                    if r.status_code != 200:
                        return {"ok": False, "error": f"HTTP {r.status_code} from {current}"}
                    return _save_download(d, r, url, current, licence, title, name)
        return {"ok": False, "error": f"More than {MAX_REDIRECTS} redirects"}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Download failed: {type(e).__name__}: {e}"}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


def _save_download(d: Path, r: httpx.Response, origin: str, final: str, licence: str, title: str, name: str) -> dict:
    cd = re.search(r'filename="?([^";]+)"?', r.headers.get("content-disposition", ""))
    fname = name or (cd.group(1) if cd else unquote(Path(urlsplit(final).path).name))
    fname = re.sub(r"[^A-Za-z0-9._-]", "_", Path(fname).name)
    ext = Path(fname).suffix.lower()
    if ext not in FETCH_EXT:
        return {"ok": False, "error": f"'{fname}' is not one of {sorted(FETCH_EXT)}. Link to the file itself, not a page."}
    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype and not ctype.startswith(_CONTENT_TYPES):
        return {"ok": False, "error": f"Unexpected content type '{ctype}' for a {ext} file"}
    declared = r.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        return {"ok": False, "error": f"File is {int(declared) / 1e6:.1f} MB: over the 50 MB limit"}
    dest = inside(d, f"imports/{fname}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    sha, size, head = hashlib.sha256(), 0, b""
    try:
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Download passed the 50 MB limit and was stopped")
                if len(head) < 2048:
                    head += chunk[:2048]
                    wrong = _looks_wrong(ext, head)
                    if wrong:
                        raise ValueError(f"Refused: {wrong}")
                sha.update(chunk)
                fh.write(chunk)
        if size == 0:
            raise ValueError("The server sent an empty file")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    sidecar = {"file": dest.name, "origin_url": origin, "downloaded_from": final, "title": title or dest.name,
               "licence": licence or "unknown: confirm at the origin before reuse",
               "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "sha256": sha.hexdigest(), "size_bytes": size, "content_type": ctype or None}
    save_json(dest.with_name(dest.name + ".source.json"), sidecar)
    loader = {".step": "import_step", ".stp": "import_step", ".stl": "import_stl", ".svg": "import_svg"}.get(ext)
    return {"ok": True, "path": f"imports/{dest.name}", "sidecar": f"imports/{dest.name}.source.json", **sidecar,
            "hint": f'{loader}("imports/{dest.name}")' if loader else None}


# ---------------------------------------------------------------- links for a person

def design_links(query: str) -> dict:
    """Search URLs for model sites that do not allow automated access, for a person to open in a browser.

    Covers Printables, MakerWorld, Thingiverse, GrabCAD, Thangs, TraceParts and McMaster-Carr. Nothing is
    fetched. Each entry carries a reuse note; where the site's terms could not be confirmed it says so.
    Files downloaded by hand come in through cad_import.
    """
    if not query.strip():
        return {"ok": False, "error": "query is empty"}
    data = load_json(DATA / "make" / "design_sites.json", {})
    links = [{"site": s["name"], "url": s["search_url"].format(q=quote(query.strip())), "reuse_note": s["reuse_note"],
              "terms_url": s["terms_url"], "terms_confirmed": s["terms_confirmed"]} for s in data.get("sites", [])]
    return {"ok": True, "query": query, "links": links,
            "note": "Open these yourself: the toolbox does not query or scrape these sites. Record the licence shown on the "
                    "model page when importing a file with cad_import."}


# ---------------------------------------------------------------- STEP inspection

def step_inspect(project: str, file: str) -> dict:
    """Load a STEP file from the project (for example imports/bracket.step) and report its solids.

    Returns solid count, overall bounding box (size and min corner, mm), total volume (mm3), and per solid:
    bounding box, volume, surface area (mm2), centre of mass and face count. Lists the first 50 solids.
    """
    try:
        d = common.project_dir(project)
        f = inside(d, file)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}
    if not f.is_file() and inside(d, f"imports/{file}").is_file():
        f = inside(d, f"imports/{file}")
    if not f.is_file():
        return {"ok": False, "error": f"No such file in the project: {file}"}
    if f.suffix.lower() not in (".step", ".stp"):
        return {"ok": False, "error": "step_inspect reads .step / .stp files only"}
    try:
        from build123d import import_step

        shape = import_step(str(f))
    except Exception as e:  # noqa: BLE001 - OCCT raises many types on a bad file
        return {"ok": False, "error": f"Could not read STEP: {type(e).__name__}: {e}"[:300]}

    def box(s) -> dict:
        b = s.bounding_box()
        return {"bbox_mm": [round(b.size.X, 3), round(b.size.Y, 3), round(b.size.Z, 3)],
                "bbox_min": [round(b.min.X, 3), round(b.min.Y, 3), round(b.min.Z, 3)]}

    solids = list(shape.solids())
    if not solids and not shape.faces():
        return {"ok": False, "error": f"{f.name} holds no geometry: it is empty or not a valid STEP file"}
    rows = []
    for i, s in enumerate(solids[:50]):
        c = s.center()
        rows.append({"index": i, **box(s), "volume_mm3": round(s.volume, 2), "area_mm2": round(s.area, 2),
                     "centre_of_mass": [round(c.X, 3), round(c.Y, 3), round(c.Z, 3)], "faces": len(s.faces()), "valid": bool(s.is_valid)})
    out = {"ok": True, "file": str(f.relative_to(d.resolve())), "solids": len(solids), **box(shape),
           "volume_mm3": round(sum(s.volume for s in solids), 2), "surfaces_only": not solids and bool(shape.faces()),
           "solid_list": rows, "units_note": "build123d converts STEP units to mm on import"}
    side = load_json(f.with_name(f.name + ".source.json"))
    if side:
        out["attribution"] = {k: side.get(k) for k in ("origin_url", "licence", "fetched")}
    return out


def register(mcp) -> None:
    for fn in (design_search, design_fetch, design_links, step_inspect):
        mcp.tool()(fn)
