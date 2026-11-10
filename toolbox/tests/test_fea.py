"""FEA verified against Euler-Bernoulli hand formulae, plus one load case on the mif4-cradle top plate."""
import math
from pathlib import Path

import pytest

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import common, fea

L, B, H, E, F = 100.0, 10.0, 10.0, 2000.0, 10.0
I = B * H ** 3 / 12


@pytest.fixture(scope="module")
def beam_root(tmp_path_factory):
    """A 100 x 10 x 10 mm bar along +X in a throwaway projects folder."""
    from build123d import Align, Box, export_step

    root = tmp_path_factory.mktemp("projects")
    (root / "beam" / "out").mkdir(parents=True)
    export_step(Box(L, B, H, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(root / "beam" / "out" / "beam.step"))
    return root


@pytest.fixture
def beam(beam_root, monkeypatch):
    monkeypatch.setattr(common, "PROJECTS", beam_root)
    return "beam"


def run(beam, loads, **kw):
    kw.setdefault("E_mpa", E)
    kw.setdefault("nu", 0.3)
    kw.setdefault("mesh_size_mm", 2.5)
    r = fea.fea_static(beam, "beam", [{"side": "xmin"}], loads, **kw)
    assert r["ok"], r
    return r


def test_cantilever_tip_load_matches_euler_bernoulli(beam):
    r = run(beam, [{"side": "xmax", "force_n": [0, 0, -F]}], yield_mpa=50, probes=[[20, 0, 5], [50, 0, 5]])
    hand_tip = F * L ** 3 / (3 * E * I)          # 2.000 mm
    hand_root = F * L * (H / 2) / I              # 6.000 MPa
    print(f"\ntip: FEA {r['max_displacement_mm']} vs hand {hand_tip} mm; "
          f"root: FEA {r['max_von_mises_mpa']} vs hand {hand_root} MPa; solve {r['solve_time_s']} s")
    assert r["max_displacement_mm"] == pytest.approx(hand_tip, rel=0.01)
    assert r["max_displacement_at"][0] == pytest.approx(L)
    assert r["max_von_mises_mpa"] == pytest.approx(hand_root, rel=0.05)
    assert r["max_von_mises_at"][0] < 2.6 and r["peak_is_near_support_or_load"]
    for p in r["probes"]:  # bending stress on the top fibre away from the clamp
        hand = F * (L - p["node_at"][0]) * (H / 2) / I
        print(f"sigma_xx at x={p['node_at'][0]}: FEA {p['stress_mpa']['xx']:.4f} vs hand {hand:.4f}")
        assert p["stress_mpa"]["xx"] == pytest.approx(hand, rel=0.02)
    assert r["reaction_force_n"] == pytest.approx([0, 0, F], abs=1e-6)
    assert r["equilibrium_error_pct"] < 1e-4
    assert r["safety_factors"]["at_peak"] == pytest.approx(50 / r["max_von_mises_mpa"], rel=1e-3)
    assert r["material"]["sources"]["nu"] == "explicit override"
    assert Path(r["result_file"]).exists() and Path(r["summary_file"]).exists()
    assert "out/fea" in r["result_file"]
    assert r["mesh"]["unknowns"] > 0 and r["solve_time_s"] > 0


def test_pressure_and_self_weight_match_uniform_load_formula(beam):
    p = 0.01  # MPa on the top face = 0.1 N/mm
    r = run(beam, [{"side": "zmax", "pressure_mpa": p}])
    assert r["max_displacement_mm"] == pytest.approx(p * B * L ** 4 / (8 * E * I), rel=0.015)
    assert r["reaction_force_n"][2] == pytest.approx(p * B * L, rel=1e-4)
    rho = 1.25
    w = rho * 1e-9 * 9806.65 * B * H
    g = run(beam, [{"gravity_g": 50, "direction": [0, 0, -1]}], density_g_cm3=rho)
    assert g["max_displacement_mm"] == pytest.approx(50 * w * L ** 4 / (8 * E * I), rel=0.015)
    assert g["reaction_force_n"][2] == pytest.approx(50 * w * L, rel=1e-4)
    assert any("assumed" in a for a in run(beam, [{"side": "zmax", "pressure_mpa": p}], nu=0)["assumptions"])


def test_layered_material_and_interlayer_factor(beam):
    """Pull along the build axis: stretch follows the Z modulus, and the interlayer factor uses the Z strength."""
    pull = [{"side": "xmax", "force_n": [500, 0, 0]}]
    r = run(beam, pull, yield_mpa=50, build_direction="x", z_stiffness_ratio=0.8, z_strength_ratio=0.5, mesh_size_mm=4)
    assert r["max_displacement_mm"] == pytest.approx(500 * L / (B * H * E * 0.8), rel=0.02)
    assert "Transversely isotropic" in r["layered_material"]
    probe = run(beam, pull, yield_mpa=50, build_direction="x", z_strength_ratio=0.5, mesh_size_mm=4, probes=[[50, 0, 0]])
    assert probe["probes"][0]["stress_mpa"]["xx"] == pytest.approx(5.0, rel=0.02)
    inter = r["interlayer"]
    assert inter["z_strength_mpa"] == 25 and inter["build_direction"] == "x"
    # the clamp's Poisson restraint lifts the stress a little near the root, hence the loose tolerance
    assert inter["safety_factor_interlayer_away"] == pytest.approx(25 / 5.0, rel=0.1)
    assert "Isotropic" in probe["layered_material"]


def test_partial_axes_box_region_and_convergence(beam):
    # sliding supports on three faces (given as a side, a box and a side): the bar is free to contract
    fixed = [{"side": "xmin", "axes": "x"}, {"box": [-1, -5, -6, 101, -5, 6], "axes": "y", "tol_mm": 0.1},
             {"side": "zmin", "axes": "z"}]
    r = fea.fea_static(beam, "beam", fixed, [{"side": "xmax", "force_n": [500, 0, 0]}], E_mpa=E, nu=0.3, mesh_size_mm=5,
                       convergence=True)
    assert r["ok"], r
    assert r["max_displacement_mm"] == pytest.approx(500 * L / (B * H * E), rel=0.01)  # free to contract: exact PL/AE
    c = r["convergence"]
    assert c["converged"] and c["unknowns"][1] > c["unknowns"][0]
    assert abs(c["max_displacement_change_pct"]) < 1
    assert any("Coarse mesh" in w for w in r["warnings"])


def test_bad_requests_are_reported_not_raised(beam):
    load = [{"side": "xmax", "force_n": [0, 0, -1]}]
    assert "E_mpa" in fea.fea_static(beam, "beam", [{"side": "xmin"}], load)["error"]
    assert "slide" in fea.fea_static(beam, "beam", [{"side": "xmin", "axes": "x"}], load, E_mpa=E)["error"]
    assert "selects no surface" in fea.fea_static(beam, "beam", [{"box": [200, 0, 0, 201, 1, 1]}], load, E_mpa=E)["error"]
    assert "No loads" in fea.fea_static(beam, "beam", [{"side": "xmin"}], [], E_mpa=E)["error"]
    assert "density" in fea.fea_static(beam, "beam", [{"side": "xmin"}], [{"gravity_g": 1}], E_mpa=E)["error"]
    assert "Built parts" in fea.fea_static(beam, "nope", [{"side": "xmin"}], load, E_mpa=E)["error"]
    assert not fea.fea_static("no-such-project", "beam", [{"side": "xmin"}], load, E_mpa=E)["ok"]
    ccx = fea.fea_static(beam, "beam", [{"side": "xmin"}], load, E_mpa=E, route="ccx")
    assert not ccx["ok"] and ("install" in ccx or "not implemented" in ccx["error"])


def test_top_plate_load_case():
    """50 N down on the central 3/8 inch hole, the four corner fixing holes held."""
    d = common.project_dir("mif4-cradle")
    if not (d / "out" / "top-plate.step").exists():
        from tb.cad import cad_build

        assert cad_build("mif4-cradle", show=False)["ok"]
    faces = fea.fea_faces("mif4-cradle", "top-plate")
    assert faces["ok"], faces
    cyl = faces["cylinders"]
    centre = min((c for c in cyl if c["radius_mm"] > 4.5), key=lambda c: math.hypot(*c["axis_start"][:2]))
    r_fix = min(c["radius_mm"] for c in cyl)
    corners = [c for c in cyl if c["radius_mm"] == r_fix]
    assert len(corners) == 4
    fixed = [{"hole": c["axis_start"], "radius_mm": r_fix} for c in corners]
    # E and yield are test inputs so this runs before tb.materials exists; they are not material data.
    r = fea.fea_static("mif4-cradle", "top-plate", fixed, [{"hole": centre["axis_start"], "force_n": [0, 0, -50]}],
                       E_mpa=2100, yield_mpa=50, z_strength_ratio=0.5, case="test-50n")
    assert r["ok"], r
    print(f"\ntop-plate: disp {r['max_displacement_mm']} mm at {r['max_displacement_at']}, "
          f"vM peak {r['max_von_mises_mpa']} / away {r.get('max_von_mises_away_mpa')} MPa, "
          f"SF {r['safety_factor_yield']}, {r['mesh']['unknowns']} unknowns, "
          f"solve {r['solve_time_s']} s, total {r['total_time_s']} s")
    assert r["reaction_force_n"] == pytest.approx([0, 0, 50], abs=1e-3)
    assert r["equilibrium_error_pct"] < 0.01
    assert 0.01 < r["max_displacement_mm"] < 2 and r["max_displacement_vector_mm"][2] < 0
    assert math.hypot(*r["max_displacement_at"][:2]) < 40
    assert r["safety_factor_yield"] > 1
    assert r["interlayer"]["z_strength_mpa"] == 25
    assert r["total_time_s"] < 120
    assert Path(r["result_file"]).stat().st_size > 10000


def test_register_exposes_fea_and_mechanics_tools():
    names = []

    class Fake:
        def tool(self):
            return lambda fn: names.append(fn.__name__)

    fea.register(Fake())
    assert {"fea_static", "fea_faces", "beam_check", "bolt_check", "buckling_check", "mass_properties"} <= set(names)
