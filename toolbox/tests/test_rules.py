"""Process rules: structure, values against the fetched design guides, and the build.json checks."""
import json

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import rules  # noqa: E402
from tb.common import DATA, PROJECTS, load_json

PROCESSES = ["fdm", "sla", "sls", "cnc_milling", "sheet_metal", "injection_moulding"]
PROJECT = "mif4-cradle"


@pytest.fixture(scope="module")
def build():
    path = PROJECTS / PROJECT / "out" / "build.json"
    if not path.exists():
        from tb.cad import cad_build

        assert cad_build(PROJECT, show=False)["ok"]
    return load_json(path)


def test_one_rule_file_per_process():
    assert rules.processes() == sorted(PROCESSES)


@pytest.mark.parametrize("process", PROCESSES)
def test_every_rule_is_complete_and_sourced(process):
    doc = json.loads((DATA / "rules" / f"{process}.json").read_text())
    ids = [r["id"] for r in doc["rules"]]
    params = [r["parameter"] for r in doc["rules"]]
    assert len(ids) == len(set(ids)) and len(params) == len(set(params))
    for r in doc["rules"]:
        assert r["description"] and r["parameter"], r["id"]
        assert r["limit"].get("unit"), r["id"]
        assert any(k in r["limit"] for k in ("min", "max", "recommended", "typical")), r["id"]
        assert r["source"].startswith("https://"), r["id"]
        assert r["sources"][0]["source"] == r["source"] and all(s["says"] for s in r["sources"])
        if "range" in r["limit"]:  # a disagreement must name both guides
            assert len(r["sources"]) >= 2, r["id"]


def test_values_match_the_guides():
    fdm, sla, sm = rules.limits("fdm"), rules.limits("sla"), rules.limits("sheet_metal")
    assert fdm["max_overhang_angle_deg"]["max"] == 45 and fdm["max_overhang_angle_deg"]["range"] == [45, 60]
    assert fdm["max_bridge_length_mm"]["max"] == 5.0
    assert fdm["min_wall_mm"]["min"] == 0.45 and fdm["min_wall_mm"]["recommended"] == 0.8
    assert fdm["clearance_fit_mm"]["min"] == 0.3
    assert sla["min_drain_hole_diameter_mm"]["range"] == [2.5, 3.5]
    assert sla["min_unsupported_wall_mm"]["range"] == [0.2, 0.6]
    assert rules.limits("sls")["min_hole_diameter_mm"]["min"] == 1.5
    assert rules.limits("cnc_milling")["min_wall_mm"]["recommended"] == 0.8
    assert sm["min_flange_length_x_thickness"]["min"] == 4.0 and sm["min_bend_radius_x_thickness"]["min"] == 1.0
    im = rules.limits("injection_moulding")
    assert im["min_draft_angle_deg"]["range"] == [0.5, 2.0]
    assert im["min_internal_corner_radius_x_wall"]["min"] == 0.5


def test_limits_accepts_build_json_process_names():
    assert rules.limits("cnc") == rules.limits("cnc_milling")
    assert rules.limits("sheet") == rules.limits("sheet_metal")
    assert rules.limits("laser-cutting") == {}
    for v in rules.limits("fdm").values():
        assert v["rule_id"] and v["source"].startswith("https://")


def test_rules_get():
    out = rules.rules_get("FDM")
    assert out["ok"] and out["process"] == "fdm" and out["count"] == len(out["rules"]) >= 8
    assert rules.rules_get("casting")["ok"] is False


def test_check_passes_in_default_volume(build):
    out = rules.rules_check(PROJECT)
    assert out["ok"] and out["passed"] and out["summary"]["fail"] == 0
    made = {n for n, p in build["parts"].items() if not p["reference"]}
    assert set(out["parts"]) == made
    assert [s["part"] for s in out["skipped"]] == [n for n, p in build["parts"].items() if p["reference"]]
    for name, res in out["parts"].items():
        by = {c["rule_id"]: c for c in res["checks"]}
        assert by["build_volume"]["measured"] == build["parts"][name]["bbox_mm"]
        assert by["fdm_min_wall"]["measured"] == pytest.approx(min(build["parts"][name]["bbox_mm"]))
        assert all(c["source"] for c in res["checks"])
    assert "fdm_overhang" in out["not_checked"]["fdm"]
    assert (PROJECTS / PROJECT / "out" / "rules" / "check.json").exists()


def test_build_volume_hand_calculation(build):
    # The largest part dimension decides: a cube one millimetre short of it must fail, one equal to it must pass.
    longest = max(max(p["bbox_mm"]) for p in build["parts"].values() if not p["reference"])
    assert rules.rules_check(PROJECT, build_volume_mm=[longest, longest, longest])["passed"]
    small = rules.rules_check(PROJECT, build_volume_mm=[longest - 1] * 3)
    assert small["ok"] and not small["passed"]
    failed = [c for res in small["parts"].values() for c in res["checks"] if c["status"] == "fail"]
    assert failed and all(c["rule_id"] == "build_volume" for c in failed)


def test_volume_axis_order_does_not_matter(build):
    dims = sorted(max((p["bbox_mm"] for p in build["parts"].values() if not p["reference"]), key=max))
    assert rules.rules_check(PROJECT, build_volume_mm=dims[::-1])["parts"]


def test_thin_part_fails_minimum_wall():
    part = {"bbox_mm": [50.0, 20.0, 0.3], "material": "petg", "valid": True, "mesh": {"watertight": True}}
    by = {c["rule_id"]: c for c in rules._part_checks(part, "fdm", [256, 256, 256])}
    assert by["fdm_min_wall"]["status"] == "fail" and by["fdm_min_wall"]["measured"] == 0.3
    part["bbox_mm"][2] = 0.6  # between the single-perimeter floor (0.45) and the recommended 0.8
    assert {c["rule_id"]: c for c in rules._part_checks(part, "fdm", [256, 256, 256])}["fdm_min_wall"]["status"] == "warn"
    part["material"], part["bbox_mm"][2] = "pom", 1.2  # plastic on the mill: 1.0 feasible, 1.5 recommended
    cnc = {c["rule_id"]: c for c in rules._part_checks(part, "cnc_milling", [256, 256, 256])}
    assert cnc["cnc_min_wall_plastic"]["status"] == "warn"


def test_bad_arguments_return_errors():
    assert rules.rules_check("no-such-project")["ok"] is False
    assert rules.rules_check(PROJECT, build_volume_mm=[256, 256])["ok"] is False
    assert rules.rules_check(PROJECT, process="casting")["ok"] is False
