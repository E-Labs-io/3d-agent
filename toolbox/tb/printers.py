"""Printer monitoring and control behind one adapter interface.

Adapters: Moonraker (Klipper), PrusaLink, OctoPrint, and a Bambu Lab stub.
Printers are configured in ~/.config/3d-agent/printers.json (outside git). The file holds the
NAME of the environment variable carrying each API key, never the key.
No adapter has been exercised against a real printer: they are built from the published API
documents cited on each class and tested against in-process fakes.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .common import load_json, save_json

TIMEOUT_S = 10.0
UPLOAD_TIMEOUT_S = 120.0
GCODE_EXT = {".gcode", ".gco", ".g", ".bgcode", ".3mf"}
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{1,63}$")
_LOCAL_SUFFIXES = (".local", ".lan", ".home.arpa", ".internal", ".localhost")
# 100.64.0.0/10 is carrier-grade NAT space, which is where Tailscale addresses live.
_EXTRA_PRIVATE = (ipaddress.ip_network("100.64.0.0/10"),)

_transport: httpx.BaseTransport | None = None  # tests swap in httpx.MockTransport


def config_path() -> Path:
    return Path(os.environ.get("THREED_AGENT_PRINTERS", "~/.config/3d-agent/printers.json")).expanduser()


# ---------------------------------------------------------------- address policy

def _is_private_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return a.is_private or a.is_loopback or a.is_link_local or any(a in n for n in _EXTRA_PRIVATE)


def _resolve(host: str) -> list[str]:
    return sorted({i[4][0] for i in socket.getaddrinfo(host, None)})


def check_base_url(base_url: str, allow_remote: bool = False) -> str | None:
    """None if the URL is acceptable, else the reason it is refused."""
    u = urlsplit(base_url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return "base_url must look like http://192.168.1.50 or https://printer.local"
    if u.username or u.password:
        return "Do not put credentials in base_url: use api_key_env"
    if allow_remote:
        return None
    host = u.hostname
    try:
        return None if _is_private_ip(host) else f"{host} is a public address: pass allow_remote=True if this is intended"
    except ValueError:
        pass
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return None
    try:
        ips = _resolve(host)
    except OSError:
        return f"Cannot resolve {host}. Use the printer's IP address, or pass allow_remote=True"
    if ips and all(_is_private_ip(i) for i in ips):
        return None
    return f"{host} resolves to a public address: pass allow_remote=True if this is intended"


# ---------------------------------------------------------------- adapter interface

STATES = ("idle", "printing", "paused", "complete", "cancelled", "error", "busy", "offline", "unknown")


def _status(state: str, raw: str, *, nozzle=None, nozzle_target=None, bed=None, bed_target=None,
            progress=None, left=None, elapsed=None, file=None) -> dict:
    """The one status shape every adapter returns."""
    def r(v, n=1):
        return round(float(v), n) if isinstance(v, (int, float)) else None

    return {"ok": True, "state": state if state in STATES else "unknown", "state_raw": raw,
            "nozzle_temp_c": r(nozzle), "nozzle_target_c": r(nozzle_target),
            "bed_temp_c": r(bed), "bed_target_c": r(bed_target),
            "progress_pct": r(progress), "time_left_s": r(left, 0), "time_printing_s": r(elapsed, 0),
            "file": file or None}


def _file(name: str, path: str, size=None, modified=None) -> dict:
    return {"name": name, "path": path, "size_bytes": size, "modified_unix": modified}


class PrinterError(Exception):
    pass


class PrinterAdapter(ABC):
    """Every method returns a JSON-serialisable dict with "ok"."""

    kind = ""
    docs = ""

    def __init__(self, cfg: dict, client: httpx.Client):
        self.cfg, self.http = cfg, client

    def _call(self, method: str, path: str, ok: tuple[int, ...] = (200,), **kw) -> httpx.Response:
        r = self.http.request(method, path, **kw)
        if r.status_code in (401, 403):
            raise PrinterError(f"{self.kind} refused the credentials (HTTP {r.status_code}). Check the key in ${self.cfg.get('api_key_env') or '<api_key_env not set>'}")
        if r.status_code not in ok:
            raise PrinterError(f"{self.kind} {method} {path} returned HTTP {r.status_code}: {r.text[:200]}")
        return r

    @abstractmethod
    def status(self) -> dict: ...
    @abstractmethod
    def files(self) -> dict: ...
    @abstractmethod
    def upload(self, gcode_path: Path) -> dict: ...
    @abstractmethod
    def start(self, file: str) -> dict: ...
    @abstractmethod
    def pause(self) -> dict: ...
    @abstractmethod
    def resume(self) -> dict: ...
    @abstractmethod
    def cancel(self) -> dict: ...
    @abstractmethod
    def camera_snapshot_url(self) -> dict: ...


class MoonrakerAdapter(PrinterAdapter):
    """Klipper via Moonraker. Docs: https://moonraker.readthedocs.io/en/latest/external_api/printer/
    (status query, print start/pause/resume/cancel), .../external_api/file_manager/ (list, upload),
    .../external_api/webcams/ and .../external_api/authorization/ (X-Api-Key header).
    HTTP responses are wrapped as {"result": ...}.
    """

    kind = "moonraker"
    docs = "https://moonraker.readthedocs.io/en/latest/external_api/introduction/"
    _STATE = {"standby": "idle", "printing": "printing", "paused": "paused", "complete": "complete",
              "cancelled": "cancelled", "error": "error"}

    def _result(self, method: str, path: str, **kw):
        return self._call(method, path, ok=(200, 201), **kw).json().get("result")

    def status(self) -> dict:
        objects = {k: None for k in ("webhooks", "print_stats", "virtual_sdcard", "extruder", "heater_bed")}
        s = (self._result("POST", "/printer/objects/query", json={"objects": objects}) or {}).get("status", {})
        klippy = s.get("webhooks", {}).get("state")
        ps, sd = s.get("print_stats", {}), s.get("virtual_sdcard", {})
        raw = ps.get("state", "") if klippy == "ready" else f"klippy {klippy}"
        state = self._STATE.get(ps.get("state", ""), "unknown") if klippy == "ready" else ("error" if klippy in ("error", "shutdown") else "offline")
        progress, elapsed = sd.get("progress"), ps.get("print_duration")
        # ETA from file progress, as the Moonraker introduction recommends when no metadata is fetched.
        left = elapsed / progress - elapsed if state in ("printing", "paused") and progress and elapsed else None
        ex, bed = s.get("extruder", {}), s.get("heater_bed", {})
        return _status(state, raw, nozzle=ex.get("temperature"), nozzle_target=ex.get("target"),
                       bed=bed.get("temperature"), bed_target=bed.get("target"),
                       progress=progress * 100 if isinstance(progress, (int, float)) else None,
                       left=left, elapsed=elapsed, file=ps.get("filename"))

    def files(self) -> dict:
        rows = self._result("GET", "/server/files/list", params={"root": "gcodes"}) or []
        return {"ok": True, "files": [_file(Path(f["path"]).name, f["path"], f.get("size"), f.get("modified")) for f in rows]}

    def upload(self, gcode_path: Path) -> dict:
        with gcode_path.open("rb") as fh:
            res = self._result("POST", "/server/files/upload", timeout=UPLOAD_TIMEOUT_S,
                               files={"file": (gcode_path.name, fh, "application/octet-stream")}, data={"root": "gcodes"})
        return {"ok": True, "file": (res or {}).get("item", {}).get("path", gcode_path.name)}

    def start(self, file: str) -> dict:
        self._result("POST", "/printer/print/start", params={"filename": file})
        return {"ok": True, "action": "start", "file": file}

    def pause(self) -> dict:
        self._result("POST", "/printer/print/pause")
        return {"ok": True, "action": "pause"}

    def resume(self) -> dict:
        self._result("POST", "/printer/print/resume")
        return {"ok": True, "action": "resume"}

    def cancel(self) -> dict:
        self._result("POST", "/printer/print/cancel")
        return {"ok": True, "action": "cancel"}

    def camera_snapshot_url(self) -> dict:
        cams = (self._result("GET", "/server/webcams/list") or {}).get("webcams", [])
        for cam in cams:
            if cam.get("enabled", True) and cam.get("snapshot_url"):
                return {"ok": True, "url": urljoin(self.cfg["base_url"].rstrip("/") + "/", cam["snapshot_url"]), "camera": cam.get("name")}
        return {"ok": False, "error": "No enabled webcam with a snapshot_url is configured in Moonraker"}


class PrusaLinkAdapter(PrinterAdapter):
    """PrusaLink v1 API. Spec: https://github.com/prusa3d/Prusa-Link-Web/blob/master/spec/openapi.yaml
    The spec declares HTTP digest auth (user name + password from the printer's network screen).
    Set "auth": "api_key" in the config to send the same secret as an X-Api-Key header instead:
    that header is not described in the spec.
    """

    kind = "prusalink"
    docs = "https://github.com/prusa3d/Prusa-Link-Web/blob/master/spec/openapi.yaml"
    _STATE = {"IDLE": "idle", "READY": "idle", "FINISHED": "complete", "STOPPED": "cancelled", "PRINTING": "printing",
              "PAUSED": "paused", "ERROR": "error", "ATTENTION": "error", "BUSY": "busy"}

    def _job(self) -> dict | None:
        r = self._call("GET", "/api/v1/job", ok=(200, 204))
        return r.json() if r.status_code == 200 else None

    def _storage(self) -> str:
        if self.cfg.get("storage"):
            return self.cfg["storage"].strip("/")
        stores = self._call("GET", "/api/v1/storage").json().get("storage_list", [])
        usable = [s for s in stores if s.get("available") and not s.get("read_only")] or [s for s in stores if s.get("available")]
        if not usable:
            raise PrinterError("PrusaLink reports no available storage (insert a USB drive or SD card)")
        return usable[0]["path"].strip("/")

    def status(self) -> dict:
        s = self._call("GET", "/api/v1/status").json()
        p, j = s.get("printer", {}), s.get("job") or {}
        job = self._job() if j else None
        f = (job or {}).get("file", {})
        return _status(self._STATE.get(p.get("state", ""), "unknown"), p.get("state", ""),
                       nozzle=p.get("temp_nozzle"), nozzle_target=p.get("target_nozzle"),
                       bed=p.get("temp_bed"), bed_target=p.get("target_bed"),
                       progress=j.get("progress"), left=j.get("time_remaining"), elapsed=j.get("time_printing"),
                       file=f.get("display_name") or f.get("name"))

    def files(self) -> dict:
        store = self._storage()
        info = self._call("GET", f"/api/v1/files/{store}/", headers={"Accept": "application/json"}).json()
        rows = [_file(c.get("display_name") or c["name"], f"{store}/{c['name']}", c.get("size"), c.get("m_timestamp"))
                for c in info.get("children", []) if c.get("type") != "FOLDER"]
        return {"ok": True, "storage": store, "files": rows}

    def upload(self, gcode_path: Path) -> dict:
        store = self._storage()
        data = gcode_path.read_bytes()
        self._call("PUT", f"/api/v1/files/{store}/{quote(gcode_path.name)}", ok=(201,), content=data, timeout=UPLOAD_TIMEOUT_S,
                   headers={"Content-Type": "application/octet-stream", "Content-Length": str(len(data)),
                            "Print-After-Upload": "?0", "Overwrite": "?0"})
        return {"ok": True, "file": f"{store}/{gcode_path.name}"}

    def start(self, file: str) -> dict:
        path = file.strip("/")
        if "/" not in path:
            path = f"{self._storage()}/{path}"
        self._call("POST", f"/api/v1/files/{quote(path)}", ok=(204,))
        return {"ok": True, "action": "start", "file": path}

    def _job_action(self, action: str, method: str, suffix: str) -> dict:
        job = self._job()
        if not job:
            return {"ok": False, "error": f"No active job to {action}"}
        self._call(method, f"/api/v1/job/{job['id']}{suffix}", ok=(204,))
        return {"ok": True, "action": action, "job_id": job["id"]}

    def pause(self) -> dict:
        return self._job_action("pause", "PUT", "/pause")

    def resume(self) -> dict:
        return self._job_action("resume", "PUT", "/resume")

    def cancel(self) -> dict:
        return self._job_action("cancel", "DELETE", "")

    def camera_snapshot_url(self) -> dict:
        return {"ok": True, "url": self.cfg["base_url"].rstrip("/") + "/api/v1/cameras/snap",
                "note": "Returns a PNG from the default camera and needs the same credentials as the API (204 when no image)."}


class OctoPrintAdapter(PrinterAdapter):
    """OctoPrint REST API. Docs: https://docs.octoprint.org/en/master/api/general.html (X-Api-Key),
    .../api/printer.html, .../api/job.html, .../api/files.html, .../api/settings.html (webcam URLs).
    """

    kind = "octoprint"
    docs = "https://docs.octoprint.org/en/master/api/"

    def status(self) -> dict:
        r = self._call("GET", "/api/printer", ok=(200, 409), params={"exclude": "sd"})
        if r.status_code == 409:  # documented response when the printer is not operational
            return _status("offline", "not operational")
        p = r.json()
        job = self._call("GET", "/api/job").json()
        flags, temp = p.get("state", {}).get("flags", {}), p.get("temperature", {})
        text = p.get("state", {}).get("text", "")
        state = ("error" if flags.get("error") or flags.get("closedOrError") else "paused" if flags.get("paused") or flags.get("pausing")
                 else "printing" if flags.get("printing") or flags.get("cancelling") else "idle" if flags.get("operational") else "unknown")
        prog = job.get("progress") or {}
        if state == "idle" and prog.get("completion") == 100:
            state = "complete"
        tool, bed = temp.get("tool0", {}), temp.get("bed", {})
        return _status(state, text, nozzle=tool.get("actual"), nozzle_target=tool.get("target"),
                       bed=bed.get("actual"), bed_target=bed.get("target"), progress=prog.get("completion"),
                       left=prog.get("printTimeLeft"), elapsed=prog.get("printTime"),
                       file=((job.get("job") or {}).get("file") or {}).get("name"))

    def files(self) -> dict:
        def walk(items):
            for f in items:
                if f.get("type") == "folder":
                    yield from walk(f.get("children", []))
                else:
                    yield _file(f["name"], f"{f.get('origin', 'local')}/{f.get('path', f['name'])}", f.get("size"), f.get("date"))

        data = self._call("GET", "/api/files", params={"recursive": "true"}).json()
        return {"ok": True, "files": list(walk(data.get("files", [])))}

    def upload(self, gcode_path: Path) -> dict:
        with gcode_path.open("rb") as fh:
            r = self._call("POST", "/api/files/local", ok=(200, 201), timeout=UPLOAD_TIMEOUT_S,
                           files={"file": (gcode_path.name, fh, "application/octet-stream")},
                           data={"select": "false", "print": "false"})
        local = (r.json().get("files") or {}).get("local") or {}
        return {"ok": True, "file": f"local/{local.get('path', gcode_path.name)}"}

    def start(self, file: str) -> dict:
        path = file.strip("/")
        if path.split("/")[0] not in ("local", "sdcard"):
            path = f"local/{path}"
        self._call("POST", f"/api/files/{quote(path)}", ok=(200, 204), json={"command": "select", "print": True})
        return {"ok": True, "action": "start", "file": path}

    def _job(self, action: str, body: dict) -> dict:
        r = self._call("POST", "/api/job", ok=(204, 409), json=body)
        if r.status_code == 409:
            return {"ok": False, "error": f"OctoPrint cannot {action} now: no job in the right state (HTTP 409)"}
        return {"ok": True, "action": action}

    def pause(self) -> dict:
        return self._job("pause", {"command": "pause", "action": "pause"})

    def resume(self) -> dict:
        return self._job("resume", {"command": "pause", "action": "resume"})

    def cancel(self) -> dict:
        return self._job("cancel", {"command": "cancel"})

    def camera_snapshot_url(self) -> dict:
        s = self._call("GET", "/api/settings").json()
        url = (s.get("webcam") or {}).get("snapshotUrl") or ((s.get("plugins") or {}).get("classicwebcam") or {}).get("snapshot")
        if not url:
            return {"ok": False, "error": "OctoPrint settings hold no webcam snapshot URL"}
        return {"ok": True, "url": urljoin(self.cfg["base_url"].rstrip("/") + "/", url)}


class BambuAdapter(PrinterAdapter):
    """Stub. Bambu Lab's current firmware puts third-party control behind its own authorisation,
    so nothing is attempted. See https://wiki.bambulab.com/en/software/third-party-integration
    """

    kind = "bambu"
    docs = "https://wiki.bambulab.com/en/software/third-party-integration"

    def _no(self) -> dict:
        return {"ok": False, "error": "Bambu Lab printers are not supported: current firmware restricts third-party control "
                                      "(print start, upload and other control commands go through Bambu's own software). "
                                      "Use Bambu Studio / Bambu Connect or the printer's screen.",
                "docs": self.docs}

    status = files = start = pause = resume = cancel = camera_snapshot_url = lambda self, *a, **k: self._no()

    def upload(self, gcode_path: Path) -> dict:
        return self._no()


ADAPTERS: dict[str, type[PrinterAdapter]] = {a.kind: a for a in (MoonrakerAdapter, PrusaLinkAdapter, OctoPrintAdapter, BambuAdapter)}


# ---------------------------------------------------------------- config and dispatch

def _load() -> dict:
    return (load_json(config_path(), {}) or {}).get("printers", {})


def _adapter(name: str) -> PrinterAdapter:
    cfg = _load().get(name)
    if not cfg:
        raise PrinterError(f"No printer '{name}'. Configured: {sorted(_load())}. Add one with printer_add.")
    bad = check_base_url(cfg["base_url"], bool(cfg.get("allow_remote")))
    if bad:
        raise PrinterError(bad)
    env = cfg.get("api_key_env", "")
    secret = os.environ.get(env, "") if env else ""
    if env and not secret:
        raise PrinterError(f"Environment variable {env} is not set. It must hold the API key for printer '{name}' "
                           f"(find it in the printer's web interface; see {ADAPTERS[cfg['type']].docs})")
    headers, auth = {}, None
    if secret:
        if cfg["type"] == "prusalink" and cfg.get("auth", "digest") == "digest":
            auth = httpx.DigestAuth(cfg.get("username") or "maker", secret)
        else:
            headers["X-Api-Key"] = secret
    client = httpx.Client(base_url=cfg["base_url"].rstrip("/"), headers=headers, auth=auth, timeout=TIMEOUT_S,
                          follow_redirects=False, transport=_transport)
    return ADAPTERS[cfg["type"]](cfg, client)


def _do(name: str, fn) -> dict:
    try:
        a = _adapter(name)
    except PrinterError as e:
        return {"ok": False, "error": str(e)}
    try:
        return {"printer": name, "type": a.kind, **fn(a)}
    except PrinterError as e:
        return {"ok": False, "printer": name, "error": str(e)}
    except httpx.HTTPError as e:
        return {"ok": False, "printer": name, "error": f"Cannot reach {a.cfg['base_url']}: {type(e).__name__}: {e}"}
    except (ValueError, KeyError, TypeError) as e:
        return {"ok": False, "printer": name, "error": f"Unexpected response from {a.kind}: {type(e).__name__}: {e}"}
    finally:
        a.http.close()


def _needs_confirm(name: str, action: str, detail: str) -> dict:
    return {"ok": False, "confirm_required": True, "printer": name, "would": f"{action} {detail}".strip(),
            "error": f"Not sent. This would {action} {detail} on '{name}'. Call again with confirm=True once the user has agreed."}


# ---------------------------------------------------------------- tools

def printer_list() -> dict:
    """List configured printers: name, type, base URL, and whether each API key variable is set (never the key)."""
    rows = [{"name": n, "type": c["type"], "base_url": c["base_url"], "api_key_env": c.get("api_key_env") or None,
             "api_key_set": bool(os.environ.get(c.get("api_key_env") or "")), "allow_remote": bool(c.get("allow_remote"))}
            for n, c in sorted(_load().items())]
    return {"ok": True, "config": str(config_path()), "printers": rows, "types": sorted(ADAPTERS)}


def printer_add(name: str, type: str, base_url: str, api_key_env: str = "", allow_remote: bool = False,  # noqa: A002
                username: str = "", auth: str = "") -> dict:
    """Save a printer to ~/.config/3d-agent/printers.json. type: moonraker, prusalink, octoprint or bambu.

    api_key_env is the NAME of an environment variable that holds the API key (for example OCTOPRINT_KEY),
    never the key itself. base_url must be a private-network, Tailscale or localhost address unless
    allow_remote=True. PrusaLink uses digest auth by default (username, default "maker", plus the secret);
    pass auth="api_key" to send it as X-Api-Key instead. Replaces an existing printer of the same name.
    """
    if not _NAME.match(name or ""):
        return {"ok": False, "error": "name: lowercase letters, digits, '-' and '_' only (max 40)"}
    if type not in ADAPTERS:
        return {"ok": False, "error": f"type must be one of {sorted(ADAPTERS)}"}
    if api_key_env and (not _ENV_NAME.match(api_key_env) or re.fullmatch(r"[0-9A-F]{16,}", api_key_env)):
        return {"ok": False, "error": "api_key_env must be the NAME of an environment variable (like OCTOPRINT_KEY), not the key. "
                                      "Nothing was saved. If that was a real key, treat it as exposed in this chat and rotate it."}
    if auth not in ("", "digest", "api_key"):
        return {"ok": False, "error": "auth must be '', 'digest' or 'api_key'"}
    bad = check_base_url(base_url, allow_remote)
    if bad:
        return {"ok": False, "error": bad}
    path = config_path()
    data = load_json(path, {}) or {}
    entry = {"type": type, "base_url": base_url.rstrip("/"), "api_key_env": api_key_env, "allow_remote": bool(allow_remote)}
    if username:
        entry["username"] = username
    if auth:
        entry["auth"] = auth
    data.setdefault("printers", {})[name] = entry
    save_json(path, data)
    path.chmod(0o600)
    out = {"ok": True, "printer": name, "config": str(path), "saved": entry, "api_key_set": bool(os.environ.get(api_key_env or ""))}
    if type == "bambu":
        out["warning"] = BambuAdapter(entry, None)._no()["error"]  # type: ignore[arg-type]
    elif api_key_env and not out["api_key_set"]:
        out["warning"] = f"{api_key_env} is not set in this process: export it where the toolbox server starts."
    return out


def printer_status(name: str) -> dict:
    """Live status of a printer: state, nozzle/bed temperatures (C), progress (%), time left (s), current file."""
    return _do(name, lambda a: a.status())


def printer_files(name: str) -> dict:
    """List G-code files stored on the printer: name, path (use it with printer_start), size, modified time."""
    return _do(name, lambda a: a.files())


def printer_camera(name: str) -> dict:
    """URL of a still image from the printer's camera, if it has one."""
    return _do(name, lambda a: a.camera_snapshot_url())


def printer_upload(name: str, gcode_path: str) -> dict:
    """Upload a G-code file to the printer's storage without starting it. Returns the remote path."""
    f = Path(gcode_path).expanduser()
    if not f.is_file():
        return {"ok": False, "error": f"No such file: {f}"}
    if f.suffix.lower() not in GCODE_EXT:
        return {"ok": False, "error": f"{f.suffix} is not a print file ({sorted(GCODE_EXT)})"}
    return _do(name, lambda a: a.upload(f))


def printer_start(name: str, file: str, confirm: bool = False) -> dict:
    """Start printing a file already on the printer. HEATS AND MOVES the machine: needs confirm=True.

    Without confirm it sends nothing and returns what it would do. Ask the user first.
    """
    if not confirm:
        return _needs_confirm(name, "start printing", file)
    return _do(name, lambda a: a.start(file))


def printer_pause(name: str) -> dict:
    """Pause the current print."""
    return _do(name, lambda a: a.pause())


def printer_resume(name: str, confirm: bool = False) -> dict:
    """Resume a paused print. Reheats and moves the machine: needs confirm=True, otherwise returns what it would do."""
    if not confirm:
        return _needs_confirm(name, "resume", "the paused print")
    return _do(name, lambda a: a.resume())


def printer_cancel(name: str, confirm: bool = False) -> dict:
    """Cancel the current print. Cannot be undone: needs confirm=True, otherwise returns what it would do."""
    if not confirm:
        return _needs_confirm(name, "cancel", "the current print")
    return _do(name, lambda a: a.cancel())


def register(mcp) -> None:
    for fn in (printer_list, printer_add, printer_status, printer_files, printer_camera, printer_upload,
               printer_start, printer_pause, printer_resume, printer_cancel):
        mcp.tool()(fn)
