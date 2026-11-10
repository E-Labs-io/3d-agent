"""Hand-calculation tools checked against worked textbook numbers."""
import math

import pytest

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import mechanics as m


def test_cantilever_point_rect():
    r = m.beam_check("cantilever", "point", 10, 100, "rect", width_mm=10, height_mm=10, E_mpa=2000, yield_mpa=50)
    assert r["ok"]
    # I = 10*10^3/12 = 833.33; delta = 10*100^3/(3*2000*833.33) = 2.0; sigma = 1000*5/833.33 = 6.0
    assert r["max_deflection_mm"] == pytest.approx(2.0, rel=1e-4)
    assert r["max_bending_stress_mpa"] == pytest.approx(6.0, rel=1e-4)
    assert r["safety_factor_yield"] == pytest.approx(50 / 6, rel=1e-3)
    assert "F*L^3/(3*E*I)" in r["formula"] and r["inputs"]["length_mm"] == 100


def test_simply_supported_cases():
    I = math.pi * (20 ** 4 - 16 ** 4) / 64
    r = m.beam_check("simply_supported", "distributed", 500, 1000, "tube", diameter_mm=20, inner_diameter_mm=16, E_mpa=69000)
    assert r["max_deflection_mm"] == pytest.approx(5 * 500 * 1000 ** 3 / (384 * 69000 * I), rel=1e-4)
    assert r["max_bending_stress_mpa"] == pytest.approx(500 * 1000 / 8 * 10 / I, rel=1e-4)
    assert r["safety_factor_yield"] is None
    r = m.beam_check("simply_supported", "point", 100, 200, "round", diameter_mm=8, E_mpa=200000)
    assert r["max_deflection_mm"] == pytest.approx(100 * 200 ** 3 / (48 * 200000 * math.pi * 8 ** 4 / 64), rel=1e-4)


def test_beam_errors():
    assert not m.beam_check("cantilever", "point", 10, 100, "rect", width_mm=10, height_mm=10)["ok"]  # no modulus
    assert not m.beam_check("propped", "point", 10, 100, "rect", width_mm=10, height_mm=10, E_mpa=1)["ok"]
    assert not m.beam_check("cantilever", "point", 10, 100, "tube", diameter_mm=10, inner_diameter_mm=12, E_mpa=1)["ok"]


def test_bolt_metric_stress_area_and_proof():
    r = m.bolt_check("M8", "8.8", tensile_load_n=5000, shear_load_n=3000)
    assert r["ok"]
    assert r["tensile_stress_area_mm2"] == pytest.approx(36.6, abs=0.05)  # ISO 898-1 nominal As for M8
    assert r["proof_load_n"] == pytest.approx(580 * 36.61, rel=2e-3)      # 21.2 kN tabulated
    assert r["safety_factor_proof"] == pytest.approx(r["proof_load_n"] / 5000, rel=1e-3)
    assert 0 < r["combined_utilisation"] < 1
    assert m.bolt_check("M10", "10.9")["tensile_stress_area_mm2"] == pytest.approx(58.0, abs=0.1)
    assert m.bolt_check("M20", "8.8")["proof_stress_mpa"] == 600


def test_bolt_unified():
    r = m.bolt_check("3/8-16", "grade 5")
    assert r["tensile_stress_area_mm2"] == pytest.approx(0.0775 * 645.16, rel=3e-3)  # ASME B1.1: 0.0775 in2
    assert r["proof_stress_mpa"] == pytest.approx(85 * 6.894757, rel=1e-3)
    assert m.bolt_check("1/4-20", "8")["tensile_stress_area_mm2"] == pytest.approx(0.0318 * 645.16, rel=3e-3)


def test_bolt_thread_engagement_and_errors():
    r = m.bolt_check("M6", "8.8", tensile_load_n=1000, engagement_mm=6, tapped_yield_mpa=40)
    e = r["thread_engagement"]
    assert e["strip_load_n"] == pytest.approx(0.577 * 40 * math.pi * 6 * 0.875 * 6, rel=1e-3)
    assert e["strips_before_bolt_breaks"] and r["warnings"]
    assert not m.bolt_check("M7.3", "8.8")["ok"]
    assert not m.bolt_check("M6", "99")["ok"]
    assert not m.bolt_check("banana")["ok"]


def test_buckling_euler_and_johnson():
    r = m.buckling_check(500, "pinned-pinned", "round", diameter_mm=10, E_mpa=200000, yield_mpa=250, load_n=1000)
    I = math.pi * 10 ** 4 / 64
    assert r["euler_critical_load_n"] == pytest.approx(math.pi ** 2 * 200000 * I / 500 ** 2, rel=1e-4)
    assert r["slenderness_ratio"] == pytest.approx(200, rel=1e-4)
    assert r["safety_factor_buckling"] == pytest.approx(r["euler_critical_load_n"] / 1000, rel=1e-3)
    short = m.buckling_check(100, "fixed-free", "rect", width_mm=20, height_mm=30, E_mpa=200000, yield_mpa=250)
    assert short["inputs"]["K"] == 2.0 and short["section"]["c_mm"] == 10  # buckles about the 20 mm side
    assert short["governing_critical_load_n"] < short["euler_critical_load_n"]
    assert short["governing_critical_load_n"] < short["squash_load_n"]


def test_press_fit_and_thermal():
    r = m.press_fit(20, 0.02, 40, 15, hub_E_mpa=200000, shaft_E_mpa=200000)
    # same material, solid shaft: p = E*delta/(2*d) * (1 - (d/do)^2) = 200000*0.02/40*0.75 = 75 MPa
    assert r["contact_pressure_mpa"] == pytest.approx(75, rel=1e-4)
    assert r["hub_hoop_stress_mpa"] == pytest.approx(75 * (1600 + 400) / (1600 - 400), rel=1e-4)
    assert r["holding_force_n"] == pytest.approx(0.15 * 75 * math.pi * 20 * 15, rel=1e-3)
    t = m.thermal_expansion(200, 40, 23.0, E_mpa=69000, other_cte_um_m_c=12.0)
    assert t["growth_mm"] == pytest.approx(0.184, rel=1e-4)
    assert t["restrained_stress_mpa"] == pytest.approx(69000 * 23e-6 * 40, rel=1e-4)
    assert t["differential_growth_mm"] == pytest.approx(0.088, rel=1e-4)


def test_mass_properties_cradle():
    from tb.common import load_json, project_dir

    parts = load_json(project_dir("mif4-cradle") / "out" / "build.json")["parts"]
    real = {k: v for k, v in parts.items() if not v["reference"]}
    mats = {v["material"] for v in real.values()}
    rho = 1.25  # test input, not material data
    r = m.mass_properties("mif4-cradle", densities_g_cm3={k: rho for k in mats})
    assert r["ok"], r
    expect = sum(v["volume_mm3"] * v.get("qty", 1) for v in real.values()) / 1000 * rho
    assert r["mass_g"] == pytest.approx(expect, rel=1e-4)
    assert {p["part"] for p in r["parts"]} == set(real) and "mif4" in r["reference_parts_excluded"]
    lo = [min(v["bbox_min"][i] for v in real.values()) for i in range(3)]
    hi = [max(v["bbox_min"][i] + v["bbox_mm"][i] for v in real.values()) for i in range(3)]
    assert all(lo[i] <= r["centre_of_gravity_mm"][i] <= hi[i] for i in range(3))
    assert not m.mass_properties("no-such-project")["ok"]


def test_material_overrides_and_poisson_assumption():
    p = m.material_props("", E_mpa=2100, yield_mpa=45)
    assert p["nu"] == 0.35 and p["sources"]["nu"] == "assumed" and any("assumed" in n for n in p["notes"])
    assert m.material_props("", E_mpa=200000)["nu"] == 0.3
    assert m.material_props("", E_mpa=2100, nu=0.4)["nu"] == 0.4
