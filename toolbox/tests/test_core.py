"""Core loop: build, check, draw, bill of materials, on the example project."""
import json

from tb import bom, cad, check, drawings
from tb.common import PROJECTS, SCENE_FILE, inside, project_dir

P = "mif4-cradle"


def test_build_outputs():
    r = cad.cad_build(P)
    assert r["ok"]
    body = r["parts"]["body"]
    assert body["valid"] and body["bbox_mm"] == [193.0, 115.0, 56.5]
    assert r["parts"]["mif4"]["reference"] and "step" not in r["parts"]["mif4"]["files"]
    for ext in ("step", "stl", "3mf"):
        assert (PROJECTS / P / body["files"][ext]).stat().st_size > 1000
    assert (PROJECTS / P / "out" / "assembly.step").exists()
    scene = json.loads(SCENE_FILE.read_text())
    assert {o["id"] for o in scene["objects"]} == {"body", "top-plate", "mif4"}
    assert next(o for o in scene["objects"] if o["id"] == "mif4")["_reference"] is True


def test_print_mesh_sits_on_bed_and_flips():
    import trimesh

    plate = trimesh.load_mesh(PROJECTS / P / "out" / "top-plate.stl")
    assert abs(plate.bounds[0][2]) < 1e-6 and abs(plate.bounds[1][2] - 12.0) < 1e-3
    assert abs(plate.bounds[0][0] + plate.bounds[1][0]) < 1e-3  # centred in X


def test_model_error_is_reported_not_raised():
    cad.project_new("broken", "Broken")
    cad.cad_write("broken", "from build123d import *\nPARTS = {'a': undefined_name}\n")
    r = cad.cad_build("broken", show=False)
    assert r["ok"] is False and "NameError" in r["error"]


def test_slug_and_path_are_contained():
    import pytest

    for bad in ("../x", "a/b", "", "..", "A b"):
        with pytest.raises(ValueError):
            project_dir(bad)
    with pytest.raises(ValueError):
        inside(project_dir(P), "../../etc/passwd")


def test_checks_pass_on_example():
    r = check.check_all(P)
    assert r["ok"] and r["pass"], r["problems"]
    assert r["mesh"]["parts"]["body"]["watertight"]
    assert abs(r["mesh"]["parts"]["body"]["volume_vs_cad_pct"]) < 0.5
    assert r["interference"]["clear"]


def test_interference_catches_a_clash():
    cad.project_new("clash", "Clash")
    cad.cad_write("clash", "from build123d import *\nfrom tb.model import part\n"
                           "PARTS = {'a': part(Box(20,20,20)), 'b': part(Pos(10,0,0)*Box(20,20,20))}\n")
    assert cad.cad_build("clash", show=False)["ok"]
    r = check.check_interference("clash")
    assert not r["clear"] and abs(r["clashes"][0]["overlap_mm3"] - 4000) < 5


def test_drawings():
    r = drawings.drawing_make(P)
    assert r["ok"] and [d["part"] for d in r["drawings"]] == ["assembly", "body", "top-plate"]
    svg = (PROJECTS / P / r["drawings"][1]["files"]["svg"]).read_text()
    assert "193" in svg and "56.5" in svg and "FIRST ANGLE" in svg
    assert (PROJECTS / P / r["drawings"][1]["files"]["dxf"]).stat().st_size > 1000


def test_bom_lines_mass_links_and_tracking():
    r = bom.bom_make(P)
    assert r["ok"] and r["summary"]["lines"] == 7
    body = next(l for l in r["lines"] if l["id"] == "part:body")
    assert body["mass_g_each"] and 100 < body["mass_g_each"] < 450  # PETG, 332 cm3 at 30% infill
    nut = next(l for l in r["lines"] if "3/8" in l["name"])
    assert nut["qty"] == 5 and nut["links"]
    assert bom.bom_set_status(P, "part:body", "printed")["ok"]
    assert next(l for l in bom.bom_make(P)["lines"] if l["id"] == "part:body")["status"] == "printed"
    assert bom.bom_set_status(P, "nope", "ordered")["ok"] is False


def test_thin_wall_fails_the_gate():
    cad.project_new("thin", "Thin")
    cad.cad_write("thin", "from build123d import *\nfrom tb.model import part\n"
                          "PARTS = {'fin': part(Box(40, 0.3, 20, align=(Align.CENTER, Align.CENTER, Align.MIN)))}\n")
    assert cad.cad_build("thin", show=False)["ok"]
    r = check.check_all("thin")
    assert not r["pass"] and any("under the" in p for p in r["problems"])
