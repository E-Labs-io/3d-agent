"""Standard parts: bd_warehouse lookups, ISO 286 fits and unified inch threads."""
import csv
import json
from importlib import resources

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import standards as s  # noqa: E402
from tb.common import DATA

UTS = json.loads((DATA / "standards" / "unified_threads.json").read_text())


def _csv(name: str) -> dict:
    import bd_warehouse

    with (resources.files(bd_warehouse) / f"data/{name}").open(encoding="utf-8", newline="") as f:
        return {row["Size"]: row for row in csv.DictReader(f)}


def test_kinds_are_introspected_from_bd_warehouse():
    out = s.standards_kinds()
    assert out["ok"]
    kinds = {k["kind"]: k for k in out["kinds"]}
    for name in ("socket_head_cap_screw", "hex_nut", "plain_washer", "heat_set_nut", "single_row_deep_groove_ball_bearing"):
        assert name in kinds
    assert "iso4762" in kinds["socket_head_cap_screw"]["standards"]
    assert {k["group"] for k in out["kinds"]} == {"screw", "nut", "washer", "bearing"}
    from bd_warehouse.fastener import Screw

    assert sum(k["group"] == "screw" for k in out["kinds"]) == len(list(s._subclasses(Screw)))


def test_sizes():
    out = s.fastener_sizes("socket_head_cap_screw")
    assert "M3-0.5" in out["sizes"]["iso4762"] and "1/4-20" in out["sizes"]["asme_b18.3"]
    assert "1/4-20" not in out["sizes"]["iso4762"]
    assert s.fastener_sizes("hex_nut", "ISO4032")["sizes"]["iso4032"]
    assert s.fastener_sizes("wing_nut")["ok"] is False
    assert s.fastener_sizes("hex_nut", "din999")["ok"] is False


def test_metric_screw_matches_the_installed_table():
    row = _csv("socket_head_cap_parameters.csv")["M3-0.5"]
    out = s.fastener_dims("socket_head_cap_screw", "M3")
    assert out["ok"] and out["standard"] == "iso4762" and out["size"] == "M3-0.5"
    assert out["dims_mm"]["dk_mm"] == float(row["iso4762:dk "]) == 5.68
    assert out["dims_mm"]["k_mm"] == 3.0 and out["dims_mm"]["s_mm"] == 2.5
    assert out["clearance_hole_mm"] == {"close": 3.2, "normal": 3.4, "loose": 3.6}
    assert out["tap_hole_mm"] == {"soft_material": 2.5, "hard_material": 2.7}
    assert "bd_warehouse" in out["source"] and out["legend"]["dk"]


def test_inch_screw_is_converted_to_mm():
    out = s.fastener_dims("socket head cap", "1/4-20")
    assert out["ok"] and out["standard"] == "asme_b18.3"
    assert out["dims_mm"]["dk_mm"] == pytest.approx(0.375 * 25.4)   # 9.525
    assert out["dims_mm"]["s_mm"] == pytest.approx(3 / 16 * 25.4)   # 4.7625 hex key
    assert out["tap_hole_mm"]["soft_material"] == pytest.approx(0.201 * 25.4, abs=1e-3)  # #7 drill


def test_nut_needs_a_standard_when_several_list_the_size():
    out = s.fastener_dims("hex_nut", "M5")
    assert out["ok"] is False and "iso4032" in out["standards"]
    nut = s.fastener_dims("hex_nut", "M5", "iso4032")
    assert nut["dims_mm"] == {"m_mm": 4.7, "s_mm": 8.0}
    assert s.fastener_dims("hex_nut", "M99", "iso4032")["ok"] is False


def test_heat_set_insert():
    listing = s.insert_dims()
    assert listing["ok"] and "CNCKitchen" in listing["sizes"]
    choose = s.insert_dims("M3", "CNCKitchen")
    assert choose["ok"] is False and "M3-0.5-5.7" in choose["similar_sizes"]["CNCKitchen"]
    out = s.insert_dims("M3-0.5-5.7", "CNCKitchen")
    assert out["ok"] and out["dims_mm"]["s_mm"] == 4.6 and out["dims_mm"]["m_mm"] == 5.7
    assert out["other"]["drill"] == "#20"
    assert out["insert_hole_diameter_mm"] == pytest.approx(0.161 * 25.4, abs=1e-3)  # #20 drill = 0.161 in
    assert "clearance_hole_mm" not in out


def test_bearing_by_designation_and_size():
    out = s.bearing_dims("608")
    assert out["ok"]
    b = next(x for x in out["bearings"] if x["kind"] == "single_row_deep_groove_ball_bearing")
    assert (b["dims_mm"]["d_mm"], b["dims_mm"]["D_mm"], b["dims_mm"]["B_mm"]) == (8.0, 22.0, 7.0)
    assert s.bearing_dims("M8-22-7", "single_row_deep_groove_ball_bearing")["bearings"][0]["size"] == "M8-22-7"
    assert s.bearing_dims("99999")["ok"] is False


def test_fit_h7_g6_at_20mm_hand_calculation():
    # ISO 286: 18 < D <= 30, IT7 = 21 um, IT6 = 13 um; H: EI = 0; g: es = -7 um.
    out = s.fit_limits(20, "H7", "g6")
    assert out["ok"] and out["fit_type"] == "clearance"
    assert (out["hole"]["min_mm"], out["hole"]["max_mm"]) == (20.0, 20.021)
    assert (out["shaft"]["min_mm"], out["shaft"]["max_mm"]) == (19.98, 19.993)
    assert out["min_clearance_mm"] == pytest.approx(0.007)   # 20.000 - 19.993
    assert out["max_clearance_mm"] == pytest.approx(0.041)   # 20.021 - 19.980
    assert "isofits" in out["source"]


def test_fit_types_and_errors():
    press = s.fit_limits(20, "H7", "p6")
    assert press["fit_type"] == "interference" and press["max_clearance_mm"] < 0
    assert s.fit_limits(20, "H7", "k6")["fit_type"] == "transition"
    assert s.fit_limits(2, "H7", "g6")["ok"] is False
    bad = s.fit_limits(20, "H77", "g6")
    assert bad["ok"] is False and "H7" in bad["hole_classes"]


def test_unified_thread_table_is_sourced_and_consistent():
    assert len(UTS["threads"]) == 20
    for t in UTS["threads"]:
        assert t["source"].startswith("https://")
        assert t["major_diameter_mm"] == pytest.approx(t["major_diameter_in"] * 25.4, abs=1e-4)
        for ser in t["series"].values():
            assert ser["pitch_mm"] == pytest.approx(25.4 / ser["tpi"], abs=1e-4)
            assert ser["tap_drill_in"] < t["major_diameter_in"]
        if "hex_nut" in t:
            assert t["hex_nut"]["source"].startswith("https://")


def test_quarter_twenty_and_three_eighths_sixteen():
    q = s.unified_thread("1/4-20")
    assert q["ok"] and list(q["series"]) == ["UNC"]
    assert q["major_diameter_mm"] == 6.35 and q["series"]["UNC"]["pitch_mm"] == 1.27  # 25.4 / 20
    assert q["series"]["UNC"]["tap_drill_in"] == 0.201                                 # #7 drill
    assert q["hex_nut"]["across_flats_max_in"] == 0.438 and q["hex_nut"]["thickness_max_in"] == 0.226
    assert q["hex_nut"]["across_flats_max_mm"] == pytest.approx(0.438 * 25.4, abs=1e-3)
    assert q["clearance_hole_mm"]["close"] == pytest.approx(17 / 64 * 25.4, abs=1e-3)
    t = s.unified_thread('3/8"-16 UNC')
    assert t["series"]["UNC"]["tap_drill_in"] == 0.313 and t["hex_nut"]["across_flats_max_in"] == 0.563
    assert set(s.unified_thread("1/4")["series"]) == {"UNC", "UNF", "UNEF"}
    assert s.unified_thread("#10-32")["series"]["UNF"]["tpi"] == 32
    assert s.unified_thread("1/4-21")["ok"] is False and s.unified_thread("M6")["ok"] is False


def test_search_spans_everything():
    hit = s.standards_search("M3 socket")
    assert hit["ok"] and {r["size"] for r in hit["results"]} == {"M3-0.5"}
    assert any(r["type"] == "unified_thread" for r in s.standards_search("1/4-20")["results"])
    assert s.standards_search("608")["results"][0]["type"] == "bearing"
    assert all(r["kind"] == "heat_set_nut" for r in s.standards_search("heat set M4")["results"])
    assert s.standards_search("H7")["results"] == [{"type": "iso_fit", "size": "H7", "body": "hole",
                                                     "lookup": "fit_limits(nominal_mm, hole, shaft)"}]
    assert s.standards_search("h7")["results"][0]["body"] == "shaft"
    assert s.standards_search("flux capacitor")["ok"] is False and s.standards_search(" ")["ok"] is False
