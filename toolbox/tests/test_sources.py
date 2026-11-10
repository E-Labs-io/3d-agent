"""Tests for tb.sources. Everything runs offline against httpx.MockTransport fakes shaped like the
documented API responses; one opt-in live test (TB_LIVE=1) hits the public KiCad GitLab API."""
import base64
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import common, sources as S  # noqa: E402
from tb.cad import cad_build  # noqa: E402

EXAMPLE = "mif4-cradle"
STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
PUBLIC = {"files.example.org": ["93.184.216.34"], "raw.githubusercontent.com": ["185.199.108.133"],
          "cdn.example.org": ["93.184.216.35"], "inside.example.org": ["10.0.0.8"], "meta.example.org": ["169.254.169.254"],
          "www.printables.com": ["104.18.0.1"], "gitlab.com": ["172.65.251.78"]}


@pytest.fixture
def net(monkeypatch):
    """Route all HTTP through a handler table and record requests; clear every API key."""
    for k in ("OSHWA_API_TOKEN", "GITHUB_TOKEN", "EPO_OPS_KEY", "EPO_OPS_SECRET"):
        monkeypatch.delenv(k, raising=False)
    state = {"log": [], "handler": lambda r: httpx.Response(404)}

    def dispatch(request):
        state["log"].append(request)
        return state["handler"](request)

    monkeypatch.setattr(S, "_transport", httpx.MockTransport(dispatch))
    monkeypatch.setattr(S, "_resolve", lambda host: PUBLIC[host])
    S._ops_token.clear()
    return state


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", tmp_path)
    (tmp_path / "demo" / "out").mkdir(parents=True)
    return tmp_path / "demo"


# ---------------------------------------------------------------- search

def test_auto_reports_missing_keys_and_never_calls_those_sources(net):
    net["handler"] = lambda r: httpx.Response(200, json=[] if "gitlab" in r.url.host else {"items": []})
    r = S.design_search("hinge")
    assert r["ok"] and r["count"] == 0
    assert r["status"]["oshwa"] == {"ok": False, "error": "Set OSHWA_API_TOKEN", "apply": S.KEYS["oshwa"][1]}
    assert "EPO_OPS_KEY and EPO_OPS_SECRET" in r["status"]["epo"]["error"] and "developers.epo.org" in r["status"]["epo"]["apply"]
    assert {q.url.host for q in net["log"]} == {"gitlab.com", "api.github.com"}
    only = S.design_search("hinge", sources="oshwa")
    assert not only["ok"] and "OSHWA_API_TOKEN" in only["error"]
    assert not S.design_search("hinge", sources="thingiverse")["ok"]
    assert not S.design_search("  ")["ok"]


def test_oshwa(net, monkeypatch):
    monkeypatch.setenv("OSHWA_API_TOKEN", "tok-abc")
    net["handler"] = lambda r: httpx.Response(200, json={"total": 1, "offset": 0, "limit": 5, "items": [{
        "oshwaUid": "US000001", "responsibleParty": "Acme Labs", "country": "United States", "projectName": "Open Hinge",
        "projectWebsite": "https://acme.example/hinge", "projectVersion": "1.0", "projectDescription": "A printable hinge",
        "primaryType": "3D Printing", "additionalType": [], "projectKeywords": ["hinge"],
        "documentationUrl": "https://github.com/acme/hinge", "hardwareLicense": "CERN-OHL-P-2.0", "softwareLicense": "MIT",
        "documentationLicense": "CC-BY-4.0", "certificationDate": "2020-01-01T00:00-04:00"}]})
    r = S.design_search("hinge", sources="oshwa", limit=5)
    hit = r["results"][0]
    assert {"title", "url", "licence", "source", "file_formats"} <= set(hit)
    assert hit["title"] == "Open Hinge" and hit["url"] == "https://github.com/acme/hinge" and hit["source"] == "oshwa"
    assert "CERN-OHL-P-2.0" in hit["licence"] and hit["oshwa_uid"] == "US000001"
    q = net["log"][0]
    assert str(q.url).startswith("https://certificationapi.oshwa.org/api/projects?") and q.url.params["q"] == "hinge" and q.url.params["limit"] == "5"
    assert q.headers["authorization"] == "Bearer tok-abc"


def kicad_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.params.get("path", "")
    repo = request.url.path.split("/projects/")[1].split("/repository")[0]
    kind = {"kicad%2Flibraries%2Fkicad-symbols": "sym", "kicad%2Flibraries%2Fkicad-footprints": "fp",
            "kicad%2Flibraries%2Fkicad-packages3D": "3d"}[request.url.raw_path.decode().split("/projects/")[1].split("/repository")[0]]
    assert repo.startswith("kicad/libraries/")
    tree = lambda name, t="tree", p=None: {"id": "abc", "name": name, "type": t, "path": p or name, "mode": "040000"}  # noqa: E731
    if not path:
        top = {"sym": [tree("Device.kicad_symdir"), tree("Transistor_FET.kicad_symdir")],
               "fp": [tree("Package_TO_SOT_SMD.pretty"), tree("Battery.pretty"), tree("LICENSE.md", "blob")],
               "3d": [tree(".github"), tree("Package_TO_SOT_SMD.3dshapes")]}[kind]
        return httpx.Response(200, json=top)
    files = {"Package_TO_SOT_SMD.pretty": ["SOT-23-3.kicad_mod", "SOT-23-5.kicad_mod", "SOT-223.kicad_mod", "README.md"],
             "Package_TO_SOT_SMD.3dshapes": ["SOT-23-3.step", "SOT-23-3.wrl", "TO-252-2.step"]}[path]
    if request.url.params.get("page_token") is None and path.endswith(".pretty"):
        nxt = str(request.url.copy_add_param("page_token", "p2"))
        return httpx.Response(200, json=[tree(files[0], "blob", f"{path}/{files[0]}")], headers={"Link": f'<{nxt}>; rel="next"'})
    rows = files[1:] if path.endswith(".pretty") else files
    return httpx.Response(200, json=[tree(f, "blob", f"{path}/{f}") for f in rows])


def test_kicad_libraries(net):
    net["handler"] = kicad_handler
    r = S.design_search("SOT-23", sources="kicad", limit=5)
    assert r["ok"]
    got = {(h["kind"], h["title"]) for h in r["results"]}
    assert got == {("footprint", "SOT-23-3.kicad_mod"), ("footprint", "SOT-23-5.kicad_mod"),
                   ("3d-model", "SOT-23-3.step"), ("3d-model", "SOT-23-3.wrl")}  # keyset paging followed; SOT-223 and README filtered
    step = next(h for h in r["results"] if h["title"] == "SOT-23-3.step")
    assert step["url"] == "https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/master/Package_TO_SOT_SMD.3dshapes/SOT-23-3.step"
    assert step["file_formats"] == ["step"] and "CC-BY-SA-4.0" in step["licence"] and step["licence_url"].startswith("https://www.kicad.org")
    assert all("authorization" not in q.headers and "private-token" not in q.headers for q in net["log"])
    assert net["log"][0].url.params["pagination"] == "keyset"


def test_github_repositories_and_rate_limit(net, monkeypatch):
    def handler(request):
        assert request.url.path == "/search/repositories"
        return httpx.Response(200, json={"total_count": 2, "incomplete_results": False, "items": [
            {"full_name": "acme/open-hinge", "html_url": "https://github.com/acme/open-hinge", "description": "Parametric hinge",
             "license": {"key": "cern-ohl-p-2.0", "spdx_id": "CERN-OHL-P-2.0"}, "stargazers_count": 42, "topics": ["cad"]},
            {"full_name": "bob/hinge", "html_url": "https://github.com/bob/hinge", "description": None, "license": None,
             "stargazers_count": 1, "topics": []}]})

    net["handler"] = handler
    r = S.design_search("hinge", sources="github", limit=2)
    a, b = r["results"]
    assert (a["title"], a["licence"], a["stars"]) == ("acme/open-hinge", "CERN-OHL-P-2.0", 42)
    assert "none stated" in b["licence"]
    q = net["log"][0]
    assert q.headers["accept"] == "application/vnd.github+json" and "authorization" not in q.headers and q.url.params["q"] == "hinge"

    net["handler"] = lambda r: httpx.Response(403, json={"message": "API rate limit exceeded"}, headers={"x-ratelimit-reset": "0"})
    limited = S.design_search("hinge", sources="github")
    assert not limited["ok"] and "rate limit" in limited["status"]["github"]["error"] and "GITHUB_TOKEN" in limited["error"]


def test_github_code_search_only_with_token(net, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")

    def handler(request):
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"items": []})
        ext = request.url.params["q"].rsplit("extension:", 1)[1]
        return httpx.Response(200, json={"items": [{"name": f"hinge.{ext}", "path": f"cad/hinge.{ext}",
                                                    "html_url": f"https://github.com/acme/open-hinge/blob/main/cad/hinge.{ext}",
                                                    "repository": {"full_name": "acme/open-hinge"}}]})

    net["handler"] = handler
    r = S.design_search("hinge", sources="github")
    assert [h["file_formats"] for h in r["results"]] == [["step"], ["stl"]]
    assert all(q.headers["authorization"] == "Bearer ghp_test" for q in net["log"])
    assert [q.url.path for q in net["log"]] == ["/search/repositories", "/search/code", "/search/code"]


def test_epo_oauth_flow_and_search(net, monkeypatch):
    monkeypatch.setenv("EPO_OPS_KEY", "key1")
    monkeypatch.setenv("EPO_OPS_SECRET", "sec2")

    def handler(request):
        if request.url.path == "/3.2/auth/accesstoken":
            assert request.method == "POST" and request.content == b"grant_type=client_credentials"
            assert request.headers["authorization"] == "Basic " + base64.b64encode(b"key1:sec2").decode()
            return httpx.Response(200, json={"access_token": "AT-1", "token_type": "BearerToken", "expires_in": "1199"})
        assert request.url.path == "/3.2/rest-services/published-data/search/biblio"
        assert request.headers["authorization"] == "Bearer AT-1" and request.headers["accept"] == "application/json"
        return httpx.Response(200, json={"ops:world-patent-data": {"ops:biblio-search": {"@total-result-count": "2", "ops:search-result": {
            "exchange-documents": [
                {"exchange-document": {"@country": "EP", "@doc-number": "1000000", "@kind": "A1", "bibliographic-data": {
                    "invention-title": [{"@lang": "de", "$": "Scharnier"}, {"@lang": "en", "$": "Hinge apparatus"}]},
                    "abstract": {"@lang": "en", "p": {"$": "A hinge with two leaves."}}}},
                {"exchange-document": {"@country": "US", "@doc-number": "2020123456", "@kind": "A1", "bibliographic-data": {
                    "invention-title": {"@lang": "en", "$": "Door hinge"}}}}]}}}})

    net["handler"] = handler
    r = S.design_search("hinge", sources="epo", limit=5)
    a, b = r["results"]
    assert (a["title"], a["publication"], a["abstract"]) == ("Hinge apparatus", "EP1000000A1", "A hinge with two leaves.")
    assert a["url"] == "https://worldwide.espacenet.com/patent/search?q=pn%3DEP1000000A1" and a["source"] == "epo"
    assert b["title"] == "Door hinge" and b["abstract"] == ""
    search = net["log"][1]
    assert search.url.params["q"] == 'ta="hinge"' and search.url.params["Range"] == "1-5"
    S.design_search('ti="latch"', sources="epo")
    assert len([q for q in net["log"] if q.url.path.endswith("accesstoken")]) == 1  # token reused until it expires
    assert net["log"][-1].url.params["q"] == 'ti="latch"'

    S._ops_token.clear()
    net["handler"] = lambda r: httpx.Response(401, json={"error": "invalid_client"})
    bad = S.design_search("hinge", sources="epo")
    assert not bad["ok"] and "EPO_OPS_KEY" in bad["error"] and "sec2" not in json.dumps(bad)


# ---------------------------------------------------------------- fetch

def test_fetch_saves_file_and_sidecar(net, proj):
    net["handler"] = lambda r: httpx.Response(200, content=STEP, headers={"content-type": "application/octet-stream"})
    r = S.design_fetch("demo", "https://files.example.org/parts/bracket%20v2.step", licence="CC-BY-4.0", title="Bracket")
    assert r["ok"] and r["path"] == "imports/bracket_v2.step" and r["hint"] == 'import_step("imports/bracket_v2.step")'
    assert (proj / "imports" / "bracket_v2.step").read_bytes() == STEP
    side = json.loads((proj / "imports" / "bracket_v2.step.source.json").read_text())
    assert side["origin_url"] == "https://files.example.org/parts/bracket%20v2.step" and side["licence"] == "CC-BY-4.0"
    assert side["title"] == "Bracket" and side["size_bytes"] == len(STEP) and len(side["sha256"]) == 64
    assert side["fetched"].startswith("20") and side["fetched"].endswith("+00:00")
    unknown = S.design_fetch("demo", "https://files.example.org/x.step")
    assert "unknown" in json.loads((proj / "imports" / "x.step.source.json").read_text())["licence"] and unknown["ok"]


def test_fetch_rewrites_github_blob_links(net, proj):
    net["handler"] = lambda r: httpx.Response(200, content=STEP, headers={"content-type": "text/plain; charset=utf-8"})
    r = S.design_fetch("demo", "https://github.com/acme/open-hinge/blob/main/cad/hinge.step")
    assert r["ok"] and str(net["log"][0].url) == "https://raw.githubusercontent.com/acme/open-hinge/main/cad/hinge.step"
    assert r["origin_url"].startswith("https://github.com/") and r["downloaded_from"].startswith("https://raw.githubusercontent.com/")


@pytest.mark.parametrize("url, why", [
    ("http://files.example.org/a.step", "https"),
    ("https://inside.example.org/a.step", "non-public"),
    ("https://meta.example.org/latest/a.step", "non-public"),
    ("https://127.0.0.1/a.stl", "non-public"),
    ("https://192.168.1.10/a.stl", "non-public"),
    ("https://[::1]/a.stl", "non-public"),
    ("https://user:pw@files.example.org/a.step", "credentials"),
    ("https://www.printables.com/model/123/files/a.stl", "does not permit automated"),
    ("ftp://files.example.org/a.step", "https"),
])
def test_fetch_refuses_before_any_request(net, proj, url, why):
    r = S.design_fetch("demo", url)
    assert not r["ok"] and why in r["error"] and not net["log"]
    assert not (proj / "imports").exists()


def test_fetch_checks_every_redirect_hop(net, proj):
    def to_private(request):
        return httpx.Response(302, headers={"location": "https://inside.example.org/a.step"})

    net["handler"] = to_private
    r = S.design_fetch("demo", "https://files.example.org/a.step")
    assert not r["ok"] and "non-public" in r["error"] and len(net["log"]) == 1

    net["handler"] = lambda q: httpx.Response(302, headers={"location": "http://cdn.example.org/a.step"})
    assert "https" in S.design_fetch("demo", "https://files.example.org/a.step")["error"]

    def to_cdn(request):
        if request.url.host == "files.example.org":
            return httpx.Response(302, headers={"location": "https://cdn.example.org/store/a.step"})
        return httpx.Response(200, content=STEP)

    net["handler"] = to_cdn
    ok = S.design_fetch("demo", "https://files.example.org/dl?id=7")
    assert ok["ok"] and ok["path"] == "imports/a.step" and ok["downloaded_from"] == "https://cdn.example.org/store/a.step"

    net["handler"] = lambda q: httpx.Response(302, headers={"location": str(q.url)})
    assert "redirects" in S.design_fetch("demo", "https://files.example.org/loop.step")["error"]


def test_fetch_rejects_wrong_content(net, proj, monkeypatch):
    cases = [
        ("https://files.example.org/page.html", httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}), "not one of"),
        ("https://files.example.org/a.exe", httpx.Response(200, content=b"MZ"), "not one of"),
        ("https://files.example.org/a.step", httpx.Response(200, content=b"<html>login</html>", headers={"content-type": "text/html"}), "content type"),
        ("https://files.example.org/a.step", httpx.Response(200, content=b"<!DOCTYPE html><html>", headers={"content-type": "text/plain"}), "web page"),
        ("https://files.example.org/a.step", httpx.Response(200, content=b"solid x\nendsolid x\n"), "not a STEP"),
        ("https://files.example.org/a.3mf", httpx.Response(200, content=b"not a zip"), "not a 3MF"),
        ("https://files.example.org/a.svg", httpx.Response(200, content=b"hello", headers={"content-type": "image/svg+xml"}), "not an SVG"),
        ("https://files.example.org/a.stl", httpx.Response(200, content=b""), "empty"),
        ("https://files.example.org/a.stl", httpx.Response(404), "HTTP 404"),
        ("https://files.example.org/a.stl", httpx.Response(200, content=b"x", headers={"content-length": str(60 * 1024 * 1024)}), "50 MB"),
    ]
    for url, response, why in cases:
        net["handler"] = lambda q, response=response: response
        r = S.design_fetch("demo", url)
        assert not r["ok"] and why in r["error"], (url, r)
    assert not list((proj / "imports").glob("*")) if (proj / "imports").exists() else True

    monkeypatch.setattr(S, "MAX_BYTES", 1000)  # body larger than declared: stopped while streaming
    net["handler"] = lambda q: httpx.Response(200, content=b"x" * 5000, headers={"content-type": "model/stl"})
    r = S.design_fetch("demo", "https://files.example.org/big.stl")
    assert not r["ok"] and "limit" in r["error"] and not list((proj / "imports").glob("*"))


def test_fetch_accepts_other_formats_and_names(net, proj):
    net["handler"] = lambda q: httpx.Response(200, content=b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>",
                                              headers={"content-type": "image/svg+xml", "content-disposition": 'attachment; filename="logo final.svg"'})
    r = S.design_fetch("demo", "https://files.example.org/download?id=9")
    assert r["ok"] and r["path"] == "imports/logo_final.svg"
    net["handler"] = lambda q: httpx.Response(200, content=b"PK\x03\x04rest", headers={"content-type": "application/zip"})
    assert S.design_fetch("demo", "https://files.example.org/x", name="../../evil.3mf")["path"] == "imports/evil.3mf"
    assert not S.design_fetch("no-such-project", "https://files.example.org/a.stl")["ok"]


# ---------------------------------------------------------------- links and STEP

def test_design_links_makes_no_requests(net):
    r = S.design_links("gt2 pulley 20T")
    assert r["ok"] and not net["log"]
    sites = {link["site"]: link for link in r["links"]}
    assert set(sites) == {"Printables", "MakerWorld", "Thingiverse", "GrabCAD Community Library", "Thangs", "TraceParts", "McMaster-Carr"}
    assert sites["Printables"]["url"] == "https://www.printables.com/search/models?q=gt2%20pulley%2020T"
    assert all(link["url"].startswith("https://") and link["reuse_note"] and "terms_confirmed" in link for link in r["links"])
    assert not S.design_links("")["ok"]
    for s in json.loads((common.DATA / "make" / "design_sites.json").read_text())["sites"]:
        assert s["source"] and S._blocked_site("www." + s["hosts"][0])


def test_step_inspect_example_part():
    if not (common.PROJECTS / EXAMPLE / "out" / "build.json").exists():
        assert cad_build(EXAMPLE, show=False)["ok"]
    build = json.loads((common.PROJECTS / EXAMPLE / "out" / "build.json").read_text())["parts"]["body"]
    r = S.step_inspect(EXAMPLE, "out/body.step")
    assert r["ok"] and r["solids"] == 1
    assert r["bbox_mm"] == pytest.approx(build["bbox_mm"], abs=0.01)
    assert r["volume_mm3"] == pytest.approx(build["volume_mm3"], rel=1e-4)
    assert r["solid_list"][0]["area_mm2"] == pytest.approx(build["area_mm2"], rel=1e-4)
    asm = S.step_inspect(EXAMPLE, "out/assembly.step")
    assert asm["solids"] == 2 and len(asm["solid_list"]) == 2


def test_step_inspect_box_and_errors(proj):
    from build123d import Box, export_step

    (proj / "imports").mkdir()
    export_step(Box(10, 20, 30), str(proj / "imports" / "box.step"))
    (proj / "imports" / "box.step.source.json").write_text(json.dumps({"origin_url": "https://x/box.step", "licence": "CC0-1.0", "fetched": "2026-11-10"}))
    r = S.step_inspect("demo", "box.step")  # bare names resolve inside imports/
    assert r["ok"] and r["solids"] == 1 and r["volume_mm3"] == pytest.approx(6000) and r["bbox_mm"] == [10.0, 20.0, 30.0]
    assert r["solid_list"][0]["area_mm2"] == pytest.approx(2200) and r["solid_list"][0]["faces"] == 6
    assert r["attribution"]["licence"] == "CC0-1.0"
    (proj / "imports" / "junk.step").write_text("not a step file")
    assert not S.step_inspect("demo", "imports/junk.step")["ok"]
    assert not S.step_inspect("demo", "imports/none.step")["ok"]
    assert not S.step_inspect("demo", "../../etc/passwd")["ok"]
    (proj / "imports" / "a.stl").write_text("solid")
    assert "only" in S.step_inspect("demo", "imports/a.stl")["error"]


@pytest.mark.skipif(os.environ.get("TB_LIVE") != "1", reason="live network test: set TB_LIVE=1")
def test_live_kicad_search():
    r = S.design_search("SOT-23", sources="kicad", limit=2)
    assert r["ok"] and any(h["title"].startswith("SOT-23") for h in r["results"])
