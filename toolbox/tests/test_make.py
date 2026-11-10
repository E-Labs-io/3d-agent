"""Tests for tb.make. No slicer is installed here: slicer routes are tested with a fake subprocess."""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import common, make  # noqa: E402
from tb.cad import cad_build  # noqa: E402

EXAMPLE = "mif4-cradle"

GCODE_PRUSA = """G1 X10 Y10 E1
; filament used [mm] = 4321.50
; filament used [cm3] = 10.39
; filament used [g] = 13.20
; filament cost = 0.33
; estimated printing time (normal mode) = 1h 2m 3s
; estimated printing time (silent mode) = 1h 5m 0s
"""
GCODE_ORCA = """; HEADER_BLOCK_START
; model printing time: 4m 55s; total estimated time: 10m 53s
; total filament length [mm] : 1200.50,300.25
; total filament weight [g] : 3.58,0.90
; HEADER_BLOCK_END
"""


@pytest.fixture(scope="module", autouse=True)
def built():
    if not (common.PROJECTS / EXAMPLE / "out" / "build.json").exists():
        assert cad_build(EXAMPLE, show=False)["ok"]


@pytest.fixture
def cubes(tmp_path, monkeypatch):
    """A throwaway project: a 20 mm cube (qty 2), a 100x60x10 slab and a T-shape with an overhang."""
    monkeypatch.setattr(common, "PROJECTS", tmp_path)
    out = tmp_path / "shapes" / "out"
    out.mkdir(parents=True)

    def add(name, mesh):
        lo, hi = mesh.bounds
        mesh.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
        mesh.export(out / f"{name}.stl")

    add("cube", trimesh.creation.box([20, 20, 20]))
    add("slab", trimesh.creation.box([100, 60, 10]))
    stem = trimesh.creation.box([10, 10, 20])
    cap = trimesh.creation.box([40, 10, 5])
    cap.apply_translation([0, 0, 12.5])
    add("tee", trimesh.boolean.union([stem, cap]))
    parts = {n: {"material": "petg", "reference": False, "qty": q, "files": {"stl": f"out/{n}.stl"}}
             for n, q in (("cube", 2), ("slab", 1), ("tee", 1))}
    parts["ghost"] = {"material": "petg", "reference": True, "qty": 1, "files": {}}
    (out / "build.json").write_text(json.dumps({"ok": True, "parts": parts}))
    return "shapes"


def test_estimate_matches_hand_calculation(cubes):
    r = make.print_estimate(cubes, "cube", route="estimate", density_g_cm3=1.25, price_per_kg=20)
    assert r["ok"] and r["basis"] == "estimate" and r["route"] == "estimate"
    p = r["parts"]["cube"]
    # 20 mm cube: area 2400 mm2 x (2 x 0.45 mm) = 2160 shell; (8000 - 2160) x 0.15 = 876 infill; no support
    assert p["shell_volume_mm3"] == pytest.approx(2160, abs=0.5)
    assert p["infill_volume_mm3"] == pytest.approx(876, abs=0.5)
    assert p["support_volume_mm3"] == 0
    assert p["layers"] == 100
    one = 3036.0
    assert p["filament_g"] == pytest.approx(one / 1000 * 1.25, abs=0.06)
    # totals carry qty 2
    assert r["filament_g"] == pytest.approx(2 * one / 1000 * 1.25, abs=0.06)
    assert r["filament_length_m"] == pytest.approx(2 * one / (math.pi * 0.875**2) / 1000, abs=0.01)
    assert r["print_time_s"] == pytest.approx(2 * one / 6.0 * 1.25, abs=2)
    assert r["material_cost"] == pytest.approx(2 * one / 1000 * 1.25 / 1000 * 20, abs=0.01)
    assert r["likely_error_pct"]["time"] and "ESTIMATE" in r["note"] and r["assumptions"]["infill_fraction"] == 0.15


def test_estimate_profile_override_and_support(cubes):
    solid = make.print_estimate(cubes, "cube", route="estimate", profile={"infill_fraction": 1.0})
    assert solid["parts"]["cube"]["extruded_volume_mm3"] == pytest.approx(8000, abs=1)
    tee = make.print_estimate(cubes, "tee", route="estimate")["parts"]["tee"]
    # cap underside: (40 x 10 - 10 x 10) mm2, 20 mm above the bed (top of the stem), 15% dense
    assert tee["support_area_mm2"] == pytest.approx(300, abs=1)
    assert tee["support_volume_mm3"] == pytest.approx(300 * 20 * 0.15, abs=1)
    off = make.print_estimate(cubes, "tee", route="estimate", profile={"support": False})["parts"]["tee"]
    assert off["support_volume_mm3"] == 0


def test_estimate_without_density_omits_mass(cubes):
    r = make.print_estimate(cubes, "cube", route="estimate", material="definitely-not-a-material")
    assert r["ok"] and r["filament_g"] is None and r["material_cost"] is None
    assert r["filament_length_m"] > 0 and "density" in r["note"]


def test_estimate_example_project_and_auto_fallback(monkeypatch):
    monkeypatch.setattr(make, "which", lambda *n: None)
    r = make.print_estimate(EXAMPLE, density_g_cm3=1.27)
    assert r["ok"] and r["route"] == "estimate" and "install" in r
    assert set(r["parts"]) == {"body", "top-plate"}  # the reference part is skipped
    build = json.loads((common.PROJECTS / EXAMPLE / "out" / "build.json").read_text())
    for name, p in r["parts"].items():
        assert p["solid_volume_mm3"] == pytest.approx(build["parts"][name]["volume_mm3"], rel=0.01)
        assert 0 < p["extruded_volume_mm3"] < p["solid_volume_mm3"]


def test_errors_are_returned_not_raised(cubes):
    assert not make.print_estimate("no-such-project")["ok"]
    assert not make.print_estimate("../etc")["ok"]
    r = make.print_estimate(cubes, "ghost", route="estimate")
    assert not r["ok"] and "cube" in r["error"]
    assert not make.print_orient(cubes, "cube", load_axis="q")["ok"]
    assert not make.print_bed_layout(cubes, [0, 100])["ok"]


def test_slicer_routes_degrade_cleanly(cubes, monkeypatch):
    monkeypatch.setattr(make, "which", lambda *n: None)
    for route in ("prusaslicer", "orcaslicer"):
        r = make.print_estimate(cubes, "cube", route=route)
        assert not r["ok"] and "install" in r and "not installed" in r["error"]
        s = make.slice(cubes, "cube", route=route)
        assert not s["ok"] and "install" in s
    assert not make.slice(cubes, "cube")["ok"]
    assert not make.slice(cubes, "cube", route="cura")["ok"]


def test_parse_gcode_comments():
    p = make.parse_gcode_stats(GCODE_PRUSA)
    assert p == {"print_time_s": 3723, "filament_length_mm": 4321.5, "filament_volume_cm3": 10.39, "filament_g": 13.2}
    o = make.parse_gcode_stats(GCODE_ORCA)
    assert o["print_time_s"] == 653
    assert o["filament_length_mm"] == pytest.approx(1500.75)
    assert o["filament_g"] == pytest.approx(4.48)
    assert make.parse_gcode_stats("G28\n")["print_time_s"] is None


def test_prusaslicer_route_with_fake_binary(cubes, monkeypatch, tmp_path):
    ini = tmp_path / "printer.ini"
    ini.write_text("layer_height = 0.2\n")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        open(cmd[cmd.index("--output") + 1], "w").write(GCODE_PRUSA)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(make, "which", lambda *n: "/fake/prusa-slicer" if "prusa-slicer" in n else None)
    monkeypatch.setattr(make.subprocess, "run", fake_run)
    s = make.slice(cubes, "cube", profile=str(ini))
    assert s["ok"] and s["route"] == "prusaslicer" and s["gcode"] == "out/make/cube.gcode"
    assert (common.PROJECTS / cubes / "out" / "make" / "cube.gcode").exists()
    cmd = calls[0]
    # only flags documented in the PrusaSlicer man page
    assert cmd[:2] == ["/fake/prusa-slicer", "--export-gcode"] and cmd[2:4] == ["--load", str(ini)]
    assert cmd[-1].endswith("out/cube.stl") and set(a for a in cmd if a.startswith("--")) == {"--export-gcode", "--load", "--output"}

    r = make.print_estimate(cubes, "cube", route="auto", price_per_kg=20, profile={"layer_height_mm": 0.3})
    assert r["ok"] and r["basis"] == "sliced" and r["route"] == "prusaslicer"
    assert "--layer-height" in calls[-1] and "0.3" in calls[-1]
    assert r["print_time_s"] == 2 * 3723 and r["filament_g"] == pytest.approx(26.4)
    assert r["filament_length_m"] == pytest.approx(8.64, abs=0.01)
    assert r["material_cost"] == pytest.approx(0.53, abs=0.01)
    assert not make.slice(cubes, "cube", profile=str(tmp_path / "missing.ini"))["ok"]


def test_orcaslicer_route_with_fake_binary(cubes, monkeypatch, tmp_path):
    machine, process, filament = (tmp_path / n for n in ("machine.json", "process.json", "filament.json"))
    for f in (machine, process, filament):
        f.write_text("{}")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        outdir = cmd[cmd.index("--outputdir") + 1]
        open(f"{outdir}/plate_1.gcode", "w").write(GCODE_ORCA)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(make, "which", lambda *n: "/fake/orca-slicer" if "orca-slicer" in n else None)
    monkeypatch.setattr(make.subprocess, "run", fake_run)
    assert not make.slice(cubes, "cube", route="orcaslicer")["ok"]  # profiles are mandatory
    s = make.slice(cubes, "cube", route="orcaslicer", profile=f"{machine};{process}", filament_profile=str(filament))
    assert s["ok"] and s["print_time_s"] == 653 and s["gcode"] == "out/make/cube.gcode"
    cmd = calls[0]
    assert cmd[cmd.index("--load-settings") + 1] == f"{machine};{process}"
    assert cmd[cmd.index("--load-filaments") + 1] == str(filament)
    assert cmd[cmd.index("--slice") + 1] == "0" and cmd[cmd.index("--arrange") + 1] == "1"

    def failing(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "bad profile")

    (common.PROJECTS / cubes / "out" / "make" / "cube.gcode").unlink()
    monkeypatch.setattr(make.subprocess, "run", failing)
    bad = make.slice(cubes, "cube", route="orcaslicer", profile=f"{machine};{process}")
    assert not bad["ok"] and "bad profile" in bad["stderr"]


def test_orient_ranks_flat_side_first(cubes):
    r = make.print_orient(cubes, "slab")
    assert r["ok"] and r["candidates"] == 6
    best = r["ranked"][0]
    assert best["weak_axis"] == "z" and best["contact_area_mm2"] == pytest.approx(6000, abs=1)
    assert best["height_mm"] == pytest.approx(10) and best["support_area_mm2"] == 0 and best["rank"] == 1
    on_end = next(c for c in r["ranked"] if c["orientation"] == "+x down")
    assert on_end["height_mm"] == pytest.approx(100) and on_end["contact_area_mm2"] == pytest.approx(600, abs=1)
    assert any("weakest in tension" in why for why in best["reasons"])


def test_orient_overhang_and_load_axis(cubes):
    r = make.print_orient(cubes, "tee")
    by = {c["orientation"]: c for c in r["ranked"]}
    assert by["-z down"]["support_area_mm2"] == pytest.approx(300, abs=1)   # cap overhangs the stem
    assert by["+z down"]["support_area_mm2"] == 0                            # upside down: cap on the bed
    assert by["+z down"]["contact_area_mm2"] == pytest.approx(400, abs=1)
    assert r["ranked"][0]["orientation"] in ("+z down", "-y down", "+y down")
    loaded = make.print_orient(cubes, "tee", load_axis="z")
    top = loaded["ranked"][0]
    assert top["weak_axis"] != "z" and top["load_across_layers"] is False
    flagged = next(c for c in loaded["ranked"] if c["orientation"] == "+z down")
    assert flagged["load_across_layers"] and any("avoid" in w for w in flagged["reasons"])


def test_orient_adds_large_flat_faces(cubes, monkeypatch):
    wedge = trimesh.creation.extrude_triangulation(
        vertices=[[0, 0], [40, 0], [0, 30]], faces=[[0, 1, 2]], height=20)
    wedge.export(common.PROJECTS / cubes / "out" / "cube.stl")
    r = make.print_orient(cubes, "cube", top=20)
    flat = [c for c in r["ranked"] if c["orientation"].startswith("flat face")]
    assert len(flat) == 1 and flat[0]["weak_axis"] == "oblique"
    assert flat[0]["contact_area_mm2"] == pytest.approx(50 * 20, abs=1)  # hypotenuse 50 mm x 20 mm deep


def test_bed_layout(cubes):
    r = make.print_bed_layout(cubes, [220, 220])
    assert r["ok"] and r["fits_one_plate"] and r["plates_needed"] == 1
    placed = r["plates"][0]["parts"]
    assert sorted(p["part"] for p in placed) == ["cube", "cube", "slab", "tee"]
    for a in placed:  # inside the bed and not overlapping, with the gap
        assert a["x_mm"] + a["size_mm"][0] <= 220 and a["y_mm"] + a["size_mm"][1] <= 220
        for b in placed:
            if a is not b:
                apart_x = a["x_mm"] + a["size_mm"][0] + 5 <= b["x_mm"] + 1e-6 or b["x_mm"] + b["size_mm"][0] + 5 <= a["x_mm"] + 1e-6
                apart_y = a["y_mm"] + a["size_mm"][1] + 5 <= b["y_mm"] + 1e-6 or b["y_mm"] + b["size_mm"][1] + 5 <= a["y_mm"] + 1e-6
                assert apart_x or apart_y

    small = make.print_bed_layout(cubes, [110, 70])
    assert not small["fits_one_plate"] and small["plates_needed"] >= 2 and "slab" in small["own_plate"]
    tiny = make.print_bed_layout(cubes, [50, 50, 15])
    assert {t["part"] for t in tiny["too_big"]} == {"slab", "cube", "tee"}
    turned = make.print_bed_layout(cubes, [60, 100])
    assert any(p["part"] == "slab" and p["rotated_90"] for pl in turned["plates"] for p in pl["parts"])


def test_bed_layout_example_project():
    assert make.print_bed_layout(EXAMPLE, [256, 256])["fits_one_plate"]
    two = make.print_bed_layout(EXAMPLE, [220, 220])   # 115 + 5 + 115 mm > 220 mm
    assert two["plates_needed"] == 2 and sorted(two["own_plate"]) == ["body", "top-plate"]


def test_register_includes_printer_tools():
    names = []

    class FakeMCP:
        def tool(self):
            return lambda fn: names.append(fn.__name__)

    make.register(FakeMCP())
    assert {"print_estimate", "print_orient", "print_bed_layout", "slice", "printer_status", "printer_start"} <= set(names)
