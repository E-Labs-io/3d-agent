"""Materials table: structure, values against the fetched data sheets, and one hand calculation."""
import json

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import materials as m  # noqa: E402
from tb.common import DATA

DOC = json.loads((DATA / "materials" / "materials.json").read_text())
REQUIRED = ["pla", "petg", "abs", "asa", "pc", "pa12", "pa-cf", "tpu 95a", "resin", "6061-T6", "7075-T6", "304", "316",
            "mild steel", "brass", "pom", "peek", "hdpe", "acrylic", "polycarbonate"]


def test_every_property_has_a_fetchable_source():
    assert len(DOC["materials"]) >= 20
    for mat in DOC["materials"]:
        assert mat["processes"], mat["id"]
        for key, rec in mat["properties"].items():
            assert isinstance(rec["value"], (int, float)), (mat["id"], key)
            assert rec["source"].startswith("https://"), (mat["id"], key)
            assert "matweb" not in rec["source"].lower(), (mat["id"], key)


def test_ids_and_aliases_are_unambiguous():
    ids = [mat["id"] for mat in DOC["materials"]]
    assert len(ids) == len(set(ids))
    for mat in DOC["materials"]:
        assert m.get_material(mat["id"])["id"] == mat["id"]


@pytest.mark.parametrize("name", REQUIRED)
def test_brief_materials_resolve_with_density(name):
    rec = m.get_material(name)
    assert rec is not None, name
    assert 0.8 < rec["density_g_cm3"] < 9.0
    assert rec["sources"]["density_g_cm3"]["source"].startswith("https://")


def test_lookup_is_case_insensitive_and_none_when_unknown():
    assert m.get_material("PETG")["id"] == m.get_material("petg")["id"] == "petg_prusament"
    assert m.get_material("Aluminium 6061-T6")["id"] == "al_6061_t6"
    assert m.get_material("unobtainium") is None
    assert m.material_get("unobtainium")["ok"] is False


def test_values_match_the_data_sheets():
    petg = m.get_material("petg")  # Prusament PETG TDS v1.1
    assert (petg["density_g_cm3"], petg["tensile_yield_xy_mpa"], petg["interlayer_strength_z_mpa"]) == (1.27, 47, 18)
    assert petg["heat_deflection_c"] == 68
    abs_ = m.get_material("abs")  # Bambu ABS TDS V3
    assert (abs_["tensile_strength_xy_mpa"], abs_["tensile_strength_z_mpa"], abs_["youngs_modulus_z_mpa"]) == (33, 28, 1960)
    pacf = m.get_material("pa-cf")  # Bambu PAHT-CF TDS V3
    assert (pacf["tensile_strength_xy_mpa"], pacf["tensile_strength_z_mpa"]) == (92, 47)
    al = m.get_material("6061")  # Wikipedia 6061, T6 typical
    assert (al["density_g_cm3"], al["tensile_yield_mpa"], al["youngs_modulus_mpa"]) == (2.70, 270, 68000)


def test_printed_materials_separate_in_plane_from_through_layer():
    for name in ("pla", "petg", "abs", "asa", "pc", "pa-cf"):
        rec = m.get_material(name)
        d = m._derived(rec)
        assert d["strength_mpa"] and d["strength_z_mpa"], name
        assert "_z" not in d["strength_basis"] and "interlayer" not in d["strength_basis"]
        assert d["strength_z_mpa"] < d["strength_mpa"], name


def test_specific_strength_hand_calculation_and_ordering():
    out = m.material_compare(["petg", "6061", "7075", "mild steel"])
    assert out["ok"]
    by_id = {r["id"]: r for r in out["materials"]}
    # 7075-T6: 434 MPa / 2.81 g/cm3 = 154.4 kN.m/kg; 6061-T6: 270 / 2.70 = 100.0; A36: 250 / 7.8 = 32.1; PETG: 47 / 1.27 = 37.0
    assert by_id["al_7075_t6"]["specific_strength_kn_m_kg"] == pytest.approx(434 / 2.81, abs=0.05)
    assert by_id["al_6061_t6"]["specific_strength_kn_m_kg"] == pytest.approx(100.0, abs=0.05)
    assert by_id["petg_prusament"]["specific_strength_kn_m_kg"] == pytest.approx(37.0, abs=0.05)
    assert [r["id"] for r in out["materials"]] == ["al_7075_t6", "al_6061_t6", "petg_prusament", "mild_steel_a36"]


def test_compare_reports_missing_names():
    out = m.material_compare(["pla", "unobtainium"])
    assert out["ok"] and out["not_found"] == ["unobtainium"]
    assert m.material_compare(["unobtainium"])["ok"] is False


def test_list_filters_by_process():
    fdm = m.material_list("fdm")
    assert fdm["ok"] and all("fdm" in r["processes"] for r in fdm["materials"])
    assert m.material_list("cnc")["count"] == m.material_list("cnc_milling")["count"] > 5
    assert m.material_list("casting")["ok"] is False


def test_select_filters_ranks_and_names_the_limiting_property():
    out = m.material_select({"process": "fdm", "min_strength_mpa": 40, "min_heat_deflection_c": 80})
    assert out["ok"]
    ids = [c["id"] for c in out["candidates"]]
    assert "pahtcf_bambu" in ids and "pla_prusament" not in ids and "petg_prusament" not in ids
    ss = [c["specific_strength_kn_m_kg"] for c in out["candidates"]]
    assert ss == sorted(ss, reverse=True)
    asa = next(c for c in out["candidates"] if c["id"] == "asa_prusament")
    assert asa["limiting_property"] == "tensile_yield_xy_mpa"  # 42/40 = 1.05 is tighter than 93/80 = 1.16
    assert asa["limiting_margin"] == pytest.approx(1.05)
    reasons = {r["id"]: r["reason"] for r in out["rejected"]}
    assert "heat_deflection_c" in reasons["pla_prusament"]


def test_select_rejects_materials_with_no_data_rather_than_assuming():
    out = m.material_select({"min_strength_mpa": 10, "max_density_g_cm3": 9})
    assert "no sourced value" in {r["id"]: r["reason"] for r in out["rejected"]}["brass"]
    light = m.material_select({"max_density_g_cm3": 1.1, "rank_by": "density"})
    dens = [c["density_g_cm3"] for c in light["candidates"]]
    assert dens == sorted(dens) and max(dens) <= 1.1
    assert m.material_select({"min_strenght": 1})["ok"] is False
