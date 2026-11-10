"""Adapter tests against in-process fake servers (httpx.MockTransport) built from each API's
documented response shapes. No real printer is contacted."""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import printers as P  # noqa: E402

KEY = "test-key-123"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("THREED_AGENT_PRINTERS", str(tmp_path / "cfg" / "printers.json"))
    monkeypatch.setenv("TEST_PRINTER_KEY", KEY)
    gcode = tmp_path / "part.gcode"
    gcode.write_text("G28\n")
    return {"gcode": gcode, "log": []}


def serve(monkeypatch, env, handler):
    def wrapped(request: httpx.Request) -> httpx.Response:
        env["log"].append((request.method, request.url.path, request))
        return handler(request)

    monkeypatch.setattr(P, "_transport", httpx.MockTransport(wrapped))


def sent(env, method, path):
    return [r for m, p, r in env["log"] if m == method and p == path]


# ---------------------------------------------------------------- config and safety

def test_add_and_list_never_store_a_key(env):
    r = P.printer_add("voron", "moonraker", "http://192.168.1.50:7125", api_key_env="TEST_PRINTER_KEY")
    assert r["ok"] and r["api_key_set"]
    text = Path(r["config"]).read_text()
    assert "TEST_PRINTER_KEY" in text and KEY not in text
    assert oct(Path(r["config"]).stat().st_mode)[-3:] == "600"
    listed = P.printer_list()
    assert listed["printers"][0]["name"] == "voron" and KEY not in json.dumps(listed)

    raw = P.printer_add("bad", "octoprint", "http://10.0.0.9", api_key_env="A1B2C3D4E5F60718293A4B5C6D7E8F90")
    assert not raw["ok"] and "NAME" in raw["error"]
    assert not P.printer_add("bad", "octoprint", "http://10.0.0.9", api_key_env="abc123secret")["ok"]
    assert "bad" not in Path(r["config"]).read_text()
    assert not P.printer_add("Bad Name", "octoprint", "http://10.0.0.9")["ok"]
    assert not P.printer_add("x", "marlin", "http://10.0.0.9")["ok"]


def test_base_url_must_be_private(env, monkeypatch):
    monkeypatch.setattr(P, "_resolve", lambda host: {"printer.example.com": ["93.184.216.34"], "nas.corp": ["10.1.2.3"]}[host])
    for ok_url in ("http://192.168.0.7", "http://10.0.0.5:7125", "http://127.0.0.1:5000", "http://localhost", "http://mk4.local",
                   "http://100.101.102.103", "http://[fd00::1]", "http://nas.corp"):
        assert P.check_base_url(ok_url) is None, ok_url
    for bad_url in ("http://8.8.8.8", "https://printer.example.com", "ftp://192.168.0.7", "http://user:pw@192.168.0.7", "not a url"):
        assert P.check_base_url(bad_url), bad_url
    assert not P.printer_add("far", "octoprint", "https://printer.example.com", "TEST_PRINTER_KEY")["ok"]
    assert P.printer_add("far", "octoprint", "https://printer.example.com", "TEST_PRINTER_KEY", allow_remote=True)["ok"]
    assert P.printer_list()["printers"][0]["allow_remote"] is True


def test_config_edited_to_public_host_is_refused(env, monkeypatch):
    P.printer_add("p", "octoprint", "http://10.0.0.9", "TEST_PRINTER_KEY")
    cfg = Path(P.config_path())
    cfg.write_text(cfg.read_text().replace("10.0.0.9", "8.8.8.8"))
    serve(monkeypatch, env, lambda r: pytest.fail("must not send"))
    assert "public address" in P.printer_status("p")["error"]


def test_missing_key_and_unknown_printer(env, monkeypatch):
    P.printer_add("p", "octoprint", "http://10.0.0.9", "OTHER_PRINTER_KEY")
    r = P.printer_status("p")
    assert not r["ok"] and "OTHER_PRINTER_KEY" in r["error"]
    assert "No printer" in P.printer_status("nope")["error"]


def test_start_resume_cancel_need_confirm(env, monkeypatch):
    P.printer_add("p", "moonraker", "http://10.0.0.9")
    serve(monkeypatch, env, lambda r: pytest.fail("must not send without confirm"))
    for call in (lambda: P.printer_start("p", "a.gcode"), lambda: P.printer_resume("p"), lambda: P.printer_cancel("p")):
        r = call()
        assert r["ok"] is False and r["confirm_required"] and r["would"] and not env["log"]
    assert "a.gcode" in P.printer_start("p", "a.gcode")["would"]


def test_upload_checks_the_file(env, tmp_path):
    P.printer_add("p", "moonraker", "http://10.0.0.9")
    assert not P.printer_upload("p", str(tmp_path / "missing.gcode"))["ok"]
    txt = tmp_path / "notes.txt"
    txt.write_text("x")
    assert not P.printer_upload("p", str(txt))["ok"]


def test_unreachable_and_auth_errors(env, monkeypatch):
    P.printer_add("p", "octoprint", "http://10.0.0.9", "TEST_PRINTER_KEY")

    def down(request):
        raise httpx.ConnectError("refused")

    serve(monkeypatch, env, down)
    assert "Cannot reach" in P.printer_status("p")["error"]
    serve(monkeypatch, env, lambda r: httpx.Response(403))
    r = P.printer_status("p")
    assert not r["ok"] and "TEST_PRINTER_KEY" in r["error"] and KEY not in r["error"]


def test_bambu_stub_is_explicit(env, monkeypatch):
    added = P.printer_add("x1", "bambu", "http://192.168.1.60")
    assert added["ok"] and "restricts third-party control" in added["warning"]
    serve(monkeypatch, env, lambda r: pytest.fail("the stub must not send"))
    for r in (P.printer_status("x1"), P.printer_files("x1"), P.printer_start("x1", "a.gcode", confirm=True),
              P.printer_pause("x1"), P.printer_cancel("x1", confirm=True), P.printer_upload("x1", str(env["gcode"])), P.printer_camera("x1")):
        assert r["ok"] is False and "wiki.bambulab.com/en/software/third-party-integration" in r["docs"]


# ---------------------------------------------------------------- Moonraker

def moonraker(request: httpx.Request) -> httpx.Response:
    path, wrap = request.url.path, lambda v, code=200: httpx.Response(code, json={"result": v})
    if path == "/printer/objects/query":
        return wrap({"eventtime": 578243.57, "status": {
            "webhooks": {"state": "ready", "state_message": "Printer is ready"},
            "print_stats": {"filename": "benchy.gcode", "total_duration": 660.0, "print_duration": 600.0, "filament_used": 500.0,
                            "state": "printing", "message": ""},
            "virtual_sdcard": {"progress": 0.25, "is_active": True, "file_position": 1000},
            "extruder": {"temperature": 214.93, "target": 215.0, "power": 0.4},
            "heater_bed": {"temperature": 59.6, "target": 60.0, "power": 0.2}}})
    if path == "/server/files/list":
        return wrap([{"path": "benchy.gcode", "modified": 1615077020.2, "size": 4926481, "permissions": "rw"},
                     {"path": "test_dir/A-Wing.gcode", "modified": 1605202259, "size": 1687387, "permissions": "rw"}])
    if path == "/server/files/upload":
        return wrap({"item": {"path": "part.gcode", "root": "gcodes", "modified": 1676984527.6, "size": 4, "permissions": "rw"},
                     "print_started": False, "print_queued": False, "action": "create_file"}, 201)
    if path in ("/printer/print/start", "/printer/print/pause", "/printer/print/resume", "/printer/print/cancel"):
        return wrap("ok")
    if path == "/server/webcams/list":
        return wrap({"webcams": [{"name": "off", "enabled": False, "snapshot_url": "/x"},
                                 {"name": "cam", "enabled": True, "snapshot_url": "/webcam/?action=snapshot", "uid": "55d3"}]})
    return httpx.Response(404, json={"error": {"code": 404, "message": "Not Found"}})


def test_moonraker(env, monkeypatch):
    P.printer_add("voron", "moonraker", "http://192.168.1.50:7125", "TEST_PRINTER_KEY")
    serve(monkeypatch, env, moonraker)
    s = P.printer_status("voron")
    assert s == {"printer": "voron", "type": "moonraker", "ok": True, "state": "printing", "state_raw": "printing",
                 "nozzle_temp_c": 214.9, "nozzle_target_c": 215.0, "bed_temp_c": 59.6, "bed_target_c": 60.0,
                 "progress_pct": 25.0, "time_left_s": 1800.0, "time_printing_s": 600.0, "file": "benchy.gcode"}
    query = sent(env, "POST", "/printer/objects/query")[0]
    assert query.headers["x-api-key"] == KEY
    assert set(json.loads(query.content)["objects"]) >= {"webhooks", "print_stats", "virtual_sdcard", "extruder", "heater_bed"}

    files = P.printer_files("voron")["files"]
    assert files[1] == {"name": "A-Wing.gcode", "path": "test_dir/A-Wing.gcode", "size_bytes": 1687387, "modified_unix": 1605202259}
    assert sent(env, "GET", "/server/files/list")[0].url.params["root"] == "gcodes"

    up = P.printer_upload("voron", str(env["gcode"]))
    assert up["ok"] and up["file"] == "part.gcode"
    body = sent(env, "POST", "/server/files/upload")[0]
    assert body.headers["content-type"].startswith("multipart/form-data") and b'name="file"; filename="part.gcode"' in body.content
    assert b'name="print"' not in body.content  # never auto-start on upload

    assert P.printer_start("voron", "test_dir/A-Wing.gcode", confirm=True)["ok"]
    assert sent(env, "POST", "/printer/print/start")[0].url.params["filename"] == "test_dir/A-Wing.gcode"
    assert P.printer_pause("voron")["action"] == "pause"
    assert P.printer_resume("voron", confirm=True)["action"] == "resume"
    assert P.printer_cancel("voron", confirm=True)["action"] == "cancel"
    cam = P.printer_camera("voron")
    assert cam["url"] == "http://192.168.1.50:7125/webcam/?action=snapshot" and cam["camera"] == "cam"


def test_moonraker_klippy_not_ready(env, monkeypatch):
    P.printer_add("voron", "moonraker", "http://192.168.1.50:7125")
    serve(monkeypatch, env, lambda r: httpx.Response(200, json={"result": {"status": {"webhooks": {"state": "shutdown"}}}}))
    s = P.printer_status("voron")
    assert s["ok"] and s["state"] == "error" and s["state_raw"] == "klippy shutdown" and s["progress_pct"] is None
    assert "x-api-key" not in env["log"][0][2].headers


# ---------------------------------------------------------------- PrusaLink

def prusalink_server(printing: bool = True):
    def handler(request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if path == "/api/v1/status":
            body = {"printer": {"state": "PRINTING" if printing else "IDLE", "temp_nozzle": 214.9, "target_nozzle": 215.0,
                                "temp_bed": 59.5, "target_bed": 60.0, "axis_z": 0.5, "flow": 95, "speed": 100},
                    "storage": {"path": "/usb/", "name": "usb", "read_only": False}}
            if printing:
                body["job"] = {"id": 420, "progress": 42.0, "time_remaining": 520, "time_printing": 526}
            return httpx.Response(200, json=body)
        if path == "/api/v1/job" and method == "GET":
            if not printing:
                return httpx.Response(204)
            return httpx.Response(200, json={"id": 420, "state": "PRINTING", "progress": 42.0, "time_remaining": 520, "time_printing": 526,
                                             "file": {"name": "SPICE~1.GCO", "display_name": "Spice_Harvester.gcode", "path": "/usb",
                                                      "size": 2393142, "m_timestamp": 1648042843}})
        if path == "/api/v1/storage":
            return httpx.Response(200, json={"storage_list": [
                {"name": "PrusaLink gcodes", "type": "LOCAL", "path": "/local", "available": True, "read_only": True},
                {"name": "usb", "type": "USB", "path": "/usb/", "available": True, "read_only": False}]})
        if path == "/api/v1/files/usb/" and method == "GET":
            return httpx.Response(200, json={"name": "usb", "read_only": False, "type": "FOLDER", "m_timestamp": 1648042843, "children": [
                {"name": "SPICE~1.GCO", "display_name": "Spice_Harvester.gcode", "read_only": False, "type": "PRINT_FILE",
                 "m_timestamp": 1648042843, "size": 424242, "refs": {"download": "/usb/SPICE~1.GCO"}},
                {"name": "examples", "read_only": False, "type": "FOLDER", "m_timestamp": 1648042843}]})
        if path == "/api/v1/files/usb/part.gcode" and method == "PUT":
            return httpx.Response(201)
        if path == "/api/v1/files/usb/SPICE~1.GCO" and method == "POST":
            return httpx.Response(204)
        if path in ("/api/v1/job/420/pause", "/api/v1/job/420/resume") and method == "PUT":
            return httpx.Response(204)
        if path == "/api/v1/job/420" and method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, json={"title": "Not Found"})

    return handler


def test_prusalink(env, monkeypatch):
    P.printer_add("mk4", "prusalink", "http://192.168.1.70", "TEST_PRINTER_KEY", auth="api_key")
    serve(monkeypatch, env, prusalink_server())
    s = P.printer_status("mk4")
    assert (s["state"], s["progress_pct"], s["time_left_s"], s["time_printing_s"]) == ("printing", 42.0, 520.0, 526.0)
    assert (s["nozzle_temp_c"], s["nozzle_target_c"], s["bed_temp_c"], s["bed_target_c"]) == (214.9, 215.0, 59.5, 60.0)
    assert s["file"] == "Spice_Harvester.gcode"
    assert sent(env, "GET", "/api/v1/status")[0].headers["x-api-key"] == KEY

    files = P.printer_files("mk4")
    assert files["storage"] == "usb"  # the read-only LOCAL storage is skipped
    assert files["files"] == [{"name": "Spice_Harvester.gcode", "path": "usb/SPICE~1.GCO", "size_bytes": 424242, "modified_unix": 1648042843}]

    up = P.printer_upload("mk4", str(env["gcode"]))
    put = sent(env, "PUT", "/api/v1/files/usb/part.gcode")[0]
    assert up["file"] == "usb/part.gcode" and put.content == b"G28\n"
    assert put.headers["print-after-upload"] == "?0" and put.headers["overwrite"] == "?0"
    assert put.headers["content-type"] == "application/octet-stream" and put.headers["content-length"] == "4"

    assert P.printer_start("mk4", "usb/SPICE~1.GCO", confirm=True)["ok"]
    assert sent(env, "POST", "/api/v1/files/usb/SPICE~1.GCO")
    assert P.printer_pause("mk4")["job_id"] == 420 and sent(env, "PUT", "/api/v1/job/420/pause")
    assert P.printer_resume("mk4", confirm=True)["ok"] and sent(env, "PUT", "/api/v1/job/420/resume")
    assert P.printer_cancel("mk4", confirm=True)["ok"] and sent(env, "DELETE", "/api/v1/job/420")
    assert P.printer_camera("mk4")["url"] == "http://192.168.1.70/api/v1/cameras/snap"


def test_prusalink_idle_and_digest_default(env, monkeypatch):
    P.printer_add("mk4", "prusalink", "http://192.168.1.70", "TEST_PRINTER_KEY")
    serve(monkeypatch, env, prusalink_server(printing=False))
    s = P.printer_status("mk4")
    assert s["ok"] and s["state"] == "idle" and s["file"] is None and s["progress_pct"] is None
    assert "x-api-key" not in env["log"][0][2].headers  # digest is the spec's scheme: no key header is sent
    r = P.printer_pause("mk4")
    assert not r["ok"] and "No active job" in r["error"]
    adapter = P._adapter("mk4")
    assert isinstance(adapter.http.auth, httpx.DigestAuth)
    adapter.http.close()


# ---------------------------------------------------------------- OctoPrint

def octoprint_server(operational: bool = True, job_conflict: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if request.headers.get("x-api-key") != KEY:
            return httpx.Response(403)
        if path == "/api/printer":
            if not operational:
                return httpx.Response(409, text="Printer is not operational")
            return httpx.Response(200, json={
                "temperature": {"tool0": {"actual": 214.8821, "target": 220.0, "offset": 0},
                                "bed": {"actual": 50.221, "target": 70.0, "offset": 5}},
                "state": {"text": "Printing", "flags": {"operational": True, "paused": False, "printing": True, "cancelling": False,
                                                         "pausing": False, "sdReady": True, "error": False, "ready": False,
                                                         "closedOrError": False}}})
        if path == "/api/job" and method == "GET":
            return httpx.Response(200, json={
                "job": {"file": {"name": "whistle_v2.gcode", "origin": "local", "size": 1468987, "date": 1378847754},
                        "estimatedPrintTime": 8811, "filament": {"tool0": {"length": 810, "volume": 5.36}}},
                "progress": {"completion": 22.98468264184775, "filepos": 337942, "printTime": 276, "printTimeLeft": 912},
                "state": "Printing"})
        if path == "/api/job" and method == "POST":
            return httpx.Response(409 if job_conflict else 204)
        if path == "/api/files" and method == "GET":
            return httpx.Response(200, json={"files": [
                {"name": "whistle_v2.gcode", "path": "whistle_v2.gcode", "type": "machinecode", "typePath": ["machinecode", "gcode"],
                 "origin": "local", "size": 1468987, "date": 1378847754, "refs": {"resource": "http://x/api/files/local/whistle_v2.gcode"}},
                {"name": "folderA", "path": "folderA", "type": "folder", "typePath": ["folder"], "origin": "local", "children": [
                    {"name": "whistle_.gco", "path": "folderA/whistle_.gco", "type": "machinecode", "origin": "local", "size": 10, "date": 5}]}],
                "free": "3.2GB"})
        if path == "/api/files/local" and method == "POST":
            return httpx.Response(201, json={"files": {"local": {"name": "part.gcode", "path": "part.gcode", "origin": "local",
                                                                 "refs": {"resource": "http://x/api/files/local/part.gcode"}}}, "done": True})
        if path == "/api/files/local/folderA/whistle_.gco" and method == "POST":
            return httpx.Response(204)
        if path == "/api/settings":
            return httpx.Response(200, json={"webcam": {"streamUrl": "/webcam/?action=stream", "snapshotUrl": "http://127.0.0.1:8080/?action=snapshot"}})
        return httpx.Response(404)

    return handler


def test_octoprint(env, monkeypatch):
    P.printer_add("ender", "octoprint", "http://octopi.local", "TEST_PRINTER_KEY")
    serve(monkeypatch, env, octoprint_server())
    s = P.printer_status("ender")
    assert (s["state"], s["state_raw"], s["file"]) == ("printing", "Printing", "whistle_v2.gcode")
    assert (s["nozzle_temp_c"], s["nozzle_target_c"], s["bed_temp_c"], s["bed_target_c"]) == (214.9, 220.0, 50.2, 70.0)
    assert (s["progress_pct"], s["time_left_s"], s["time_printing_s"]) == (23.0, 912.0, 276.0)

    files = P.printer_files("ender")["files"]
    assert [f["path"] for f in files] == ["local/whistle_v2.gcode", "local/folderA/whistle_.gco"]
    assert sent(env, "GET", "/api/files")[0].url.params["recursive"] == "true"

    up = P.printer_upload("ender", str(env["gcode"]))
    body = sent(env, "POST", "/api/files/local")[0].content
    assert up["file"] == "local/part.gcode" and b'name="file"; filename="part.gcode"' in body
    assert b'name="print"\r\n\r\nfalse' in body and b'name="select"\r\n\r\nfalse' in body

    assert P.printer_start("ender", "local/folderA/whistle_.gco", confirm=True)["ok"]
    assert json.loads(sent(env, "POST", "/api/files/local/folderA/whistle_.gco")[0].content) == {"command": "select", "print": True}
    P.printer_pause("ender"), P.printer_resume("ender", confirm=True), P.printer_cancel("ender", confirm=True)
    bodies = [json.loads(r.content) for r in sent(env, "POST", "/api/job")]
    assert bodies == [{"command": "pause", "action": "pause"}, {"command": "pause", "action": "resume"}, {"command": "cancel"}]
    assert P.printer_camera("ender")["url"] == "http://127.0.0.1:8080/?action=snapshot"


def test_octoprint_offline_and_conflict(env, monkeypatch):
    P.printer_add("ender", "octoprint", "http://octopi.local", "TEST_PRINTER_KEY")
    serve(monkeypatch, env, octoprint_server(operational=False, job_conflict=True))
    s = P.printer_status("ender")
    assert s["ok"] and s["state"] == "offline" and s["nozzle_temp_c"] is None
    r = P.printer_cancel("ender", confirm=True)
    assert not r["ok"] and "409" in r["error"]


def test_every_adapter_returns_the_same_status_keys(env, monkeypatch):
    P.printer_add("a", "moonraker", "http://10.0.0.1", "TEST_PRINTER_KEY")
    P.printer_add("b", "prusalink", "http://10.0.0.2", "TEST_PRINTER_KEY", auth="api_key")
    P.printer_add("c", "octoprint", "http://10.0.0.3", "TEST_PRINTER_KEY")
    keys = []
    for name, handler in (("a", moonraker), ("b", prusalink_server()), ("c", octoprint_server())):
        serve(monkeypatch, env, handler)
        s = P.printer_status(name)
        assert s["state"] in P.STATES
        keys.append(set(s) - {"type", "printer"})
    assert keys[0] == keys[1] == keys[2]
