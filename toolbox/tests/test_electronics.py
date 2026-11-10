"""Electronics tests: a real SKiDL build with asserted connectivity, harness checks and hand calculations.

KiCad, ngspice and WireViz are optional programs: their live tests skip when the program is absent,
and the not-installed path (ok False + install guidance) is tested instead.
"""
import csv
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # no conftest: make `tb` importable

from tb import common  # noqa: E402
from tb import electronics as e  # noqa: E402

HAVE_KICAD = bool(common.which("kicad-cli"))
HAVE_NGSPICE = bool(common.which("ngspice"))
HAVE_WIREVIZ = bool(common.which("wireviz") and common.which("dot"))


@pytest.fixture(scope="module")
def projects(tmp_path_factory):
    """Throwaway projects folder so tests never touch real projects."""
    root = tmp_path_factory.mktemp("projects")
    old, common.PROJECTS = common.PROJECTS, root
    yield root
    common.PROJECTS = old


@pytest.fixture(scope="module")
def regulator_build(projects):
    """The starter circuit: 3-pin connector -> 7805 -> 330R -> LED, with two decoupling caps."""
    assert e.circuit_write("reg5v")["starter"] is True
    return e.circuit_build("reg5v")


def net_pins(build: dict, name: str) -> set[str]:
    net = next(n for n in build["nets"] if n["name"] == name)
    return {f"{p['ref']}.{p['pin']}" for p in net["pins"]}


# ---- circuits as code ----------------------------------------------------------------

def test_regulator_circuit_builds_without_kicad_libraries(regulator_build):
    b = regulator_build
    assert b["ok"], b
    assert [p["ref"] for p in b["parts"]] == ["C1", "C2", "D1", "J1", "R1", "U1"]
    assert b["part_count"] == 6 and b["net_count"] == 4


def test_regulator_net_connectivity(regulator_build):
    b = regulator_build
    assert net_pins(b, "VIN") == {"J1.1", "U1.1", "C1.1"}
    assert net_pins(b, "GND") == {"J1.2", "U1.2", "C1.2", "C2.2", "D1.1"}
    assert net_pins(b, "+5V") == {"U1.3", "C2.1", "R1.1", "J1.3"}
    assert net_pins(b, "LED_A") == {"R1.2", "D1.2"}  # resistor in series with the LED anode
    assert b["unconnected_pins"] == []


def test_parts_carry_value_footprint_and_fields(regulator_build):
    parts = {p["ref"]: p for p in regulator_build["parts"]}
    assert parts["R1"]["value"] == "330" and parts["R1"]["footprint"] == "Resistor_SMD:R_0805_2012Metric"
    assert parts["U1"]["value"] == "LM7805"
    assert parts["U1"]["fields"] == {"mpn": "L7805CV", "manufacturer": "STMicroelectronics"}
    assert [(p["num"], p["name"], p["net"]) for p in parts["U1"]["pins"]] == [
        ("1", "IN", "VIN"), ("2", "GND", "GND"), ("3", "OUT", "+5V")]
    assert [(p["num"], p["name"]) for p in parts["D1"]["pins"]] == [("1", "K"), ("2", "A")]


def test_regulator_erc_clean_and_files_written(regulator_build, projects):
    b = regulator_build
    assert b["erc"] == {"ok": True, "errors": [], "warnings": []}
    assert b["missing_footprints"] == []
    out = projects / "reg5v" / "out" / "electronics"
    netlist = Path(b["files"]["netlist"])
    assert netlist.parent == out and netlist.name == "reg5v.net"
    text = netlist.read_text()
    assert text.lstrip().startswith("(export") and '"L7805CV"' in text and '(ref "U1")' in text
    assert json.loads((out / "circuit.json").read_text())["net_count"] == 4


def test_build_leaves_no_log_files_in_the_toolbox(regulator_build):
    assert regulator_build["ok"]
    assert not list(common.TOOLBOX.glob("electronics.*")) and not list(common.TOOLBOX.glob("reg5v*"))


FAULTY = '''
from skidl import Net
from tb.electronics import connector, ic, mosfet, resistor

vcc, gnd = Net("VCC"), Net("GND")     # plain nets: nothing drives the power pins
u1 = ic("ATTINY85", {"8": ("VCC", "power_in"), "4": ("GND", "power_in"), "5": ("PB0", "bidir"), "6": "PB1"},
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
q1 = mosfet("AO3400", pinout="GSD")   # SOT-23: 1=G 2=S 3=D, no footprint given
r1 = resistor("10k", footprint="Resistor_SMD:R_0603_1608Metric")
j1 = connector(2)
vcc += u1["VCC"], j1[1]
gnd += u1["GND"], q1["S"], r1[2], j1[2]
Net("GATE").connect(u1["PB0"], q1["G"], r1[1])
'''


def test_erc_reports_real_problems(projects):
    e.circuit_write("faulty", FAULTY)
    b = e.circuit_build("faulty")
    assert b["ok"], b
    warnings = " | ".join(b["erc"]["warnings"])
    assert "Insufficient drive current on net VCC" in warnings      # power pin fed from an undriven net
    assert "Unconnected pin" in warnings and "Q_NMOS/Q1" in warnings  # the MOSFET drain is floating
    assert set(b["unconnected_pins"]) == {"Q1.3", "U1.6"}
    assert b["missing_footprints"] == ["J1", "Q1"]
    q1 = next(p for p in b["parts"] if p["ref"] == "Q1")
    assert [(p["num"], p["name"]) for p in q1["pins"]] == [("1", "G"), ("2", "S"), ("3", "D")]
    assert net_pins(b, "GATE") == {"U1.5", "Q1.1", "R1.1"}


def test_circuit_error_returns_traceback(projects):
    e.circuit_write("broken", "from tb.electronics import resistor\nr = resistor('1k')\nr[3]\nraise RuntimeError('boom')\n")
    b = e.circuit_build("broken")
    assert b["ok"] is False and "traceback" in b and "circuit.py" in b["traceback"]


def test_circuit_read_write_and_guards(projects):
    assert e.circuit_read("reg5v")["content"].startswith('"""reg5v')
    assert e.circuit_read("reg5v", "nope.py")["ok"] is False
    assert e.circuit_write("reg5v", "x", "../escape.py")["ok"] is False
    assert e.circuit_build("no-such-project")["ok"] is False


# ---- KiCad route ---------------------------------------------------------------------

def test_kicad_commands_match_the_cli_reference(tmp_path):
    sch, pcb, out = tmp_path / "a.kicad_sch", tmp_path / "a.kicad_pcb", tmp_path / "out"
    argv = lambda action, src: e._kicad_argv("kicad-cli", action, src, out)[0]  # noqa: E731
    assert argv("erc", sch) == ["kicad-cli", "sch", "erc", "--format", "json", "--severity-all",
                                "--output", str(out / "erc.json"), str(sch)]
    assert argv("drc", pcb)[:6] == ["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all"]
    assert argv("pdf", sch) == ["kicad-cli", "sch", "export", "pdf", "--output", str(out / "schematic.pdf"), str(sch)]
    assert argv("svg", sch)[1:4] == ["sch", "export", "svg"] and argv("svg", sch)[5].endswith("/")
    assert argv("bom", sch)[1:4] == ["sch", "export", "bom"]
    assert argv("gerbers", pcb)[1:4] == ["pcb", "export", "gerbers"] and argv("gerbers", pcb)[5].endswith("gerbers/")
    assert argv("step", pcb)[1:4] == ["pcb", "export", "step"] and argv("step", pcb)[-2].endswith("board.step")
    with pytest.raises(ValueError):
        argv("gerbers", sch)


def test_kicad_report_violations_are_counted():
    report = {"sheets": [{"path": "/", "violations": [{"type": "pin_not_connected", "severity": "error"},
                                                      {"type": "lib_symbol_issues", "severity": "warning"}]}]}
    assert [v["severity"] for v in e._violations(report)] == ["error", "warning"]
    drc = {"violations": [{"severity": "error"}], "unconnected_items": [{"severity": "error"}], "schematic_parity": []}
    assert len(e._violations(drc)) == 2


@pytest.mark.skipif(HAVE_KICAD, reason="KiCad is installed; the not-installed path cannot be exercised")
def test_kicad_missing_gives_install_guidance(projects):
    for r in (e.kicad_check("reg5v", "board.kicad_pcb"), e.kicad_export("reg5v", "sch.kicad_sch", "pdf")):
        assert r["ok"] is False and "kicad" in r["install"]


@pytest.mark.skipif(not HAVE_KICAD, reason="KiCad (kicad-cli) is not installed")
def test_kicad_cli_runs(projects):
    r = e.kicad_check("reg5v", "missing.kicad_sch")
    assert r["ok"] is False and "No such file" in r["error"]


def test_kicad_rejects_unknown_actions(projects):
    assert e.kicad_check("reg5v", "notes.txt")["ok"] is False
    assert e.kicad_export("reg5v", "a.kicad_sch", "erc")["ok"] is False


# ---- simulation ----------------------------------------------------------------------

DIVIDER = "divider\nV1 in 0 5\nR1 in out 1k\nR2 out 0 1k\n"

RAW_ASCII = b"""Title: divider
Date: Tue Nov 10 12:00:00  2026
Plotname: Operating Point
Flags: real
No. Variables: 3
No. Points: 1
Variables:
\t0\tv(in)\tvoltage
\t1\tv(out)\tvoltage
\t2\ti(v1)\tcurrent
Values:
 0\t5.000000000000000e+00
\t2.500000000000000e+00
\t-2.500000000000000e-03
"""


def test_spice_deck_adds_the_analysis_once():
    deck = e._spice_deck(DIVIDER + ".end\n", "op")
    assert deck.splitlines()[-2:] == [".op", ".end"] and deck.count(".end") == 1
    assert e._spice_deck(DIVIDER + ".tran 1u 1m\n", "op").count(".op") == 0


def test_raw_parser_ascii_operating_point():
    (plot,) = e._parse_raw(RAW_ASCII)
    summary = e._summarise_plot(plot)
    assert summary["values"] == {"v(in)": 5.0, "v(out)": 2.5, "i(v1)": -0.0025}


def test_raw_parser_binary_sweep():
    header = (b"Title: rc\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 3\n"
              b"Variables:\n\t0\ttime\ttime\n\t1\tv(out)\tvoltage\nBinary:\n")
    (plot,) = e._parse_raw(header + struct.pack("<6d", 0.0, 0.0, 1e-3, 3.16, 2e-3, 4.32))
    s = e._summarise_plot(plot)
    assert s["points"] == 3 and s["sweep"] == "time"
    assert s["signals"]["v(out)"] == {"min": 0.0, "max": 4.32, "first": 0.0, "final": 4.32}


@pytest.mark.skipif(HAVE_NGSPICE, reason="ngspice is installed; the not-installed path cannot be exercised")
def test_ngspice_missing_gives_install_guidance(projects):
    r = e.circuit_simulate("reg5v", DIVIDER)
    assert r["ok"] is False and r["install"] == "brew install ngspice"


@pytest.mark.skipif(not HAVE_NGSPICE, reason="ngspice is not installed")
def test_ngspice_voltage_divider(projects):
    r = e.circuit_simulate("reg5v", DIVIDER, "op")
    assert r["ok"], r
    values = r["analyses"][0]["values"]
    assert values["v(out)"] == pytest.approx(2.5) and values["i(v1)"] == pytest.approx(-0.0025)  # 5 V / 2k


def test_spice_deck_keeps_a_first_line_part():
    assert e._spice_deck("V1 in 0 5\nR1 in 0 1k\n", "op").splitlines()[:2] == ["* circuit", "V1 in 0 5"]
    assert e._spice_deck(DIVIDER, "op").splitlines()[0] == "divider"  # a real title is left alone


@pytest.mark.skipif(not HAVE_NGSPICE, reason="ngspice is not installed")
def test_ngspice_untitled_netlist_and_rc_step(projects):
    r = e.circuit_simulate("reg5v", "V1 in 0 9\nR1 in mid 2k\nR2 mid 0 1k\n", "op")
    assert r["ok"] and r["analyses"][0]["values"]["v(mid)"] == pytest.approx(3.0) and r["warnings"] == []
    # RC step: 1k and 1u give 1 ms, so 5 ms is five time constants: 5 * (1 - e^-5) = 4.966 V
    r = e.circuit_simulate("reg5v", "V1 in 0 PULSE(0 5 0 1n 1n 1 2)\nR1 in out 1k\nC1 out 0 1u\n", "tran 10u 5m")
    assert r["analyses"][0]["signals"]["v(out)"]["final"] == pytest.approx(4.966, abs=0.01)
    # same RC as a low-pass: -3 dB at 159 Hz, so about 1 at 1 Hz and 1/628 at 100 kHz
    r = e.circuit_simulate("reg5v", "V1 in 0 AC 1\nR1 in out 1k\nC1 out 0 1u\n", "ac dec 10 1 100k")
    sig = r["analyses"][0]["signals"]["v(out)"]
    assert sig["first"] == pytest.approx(1.0, abs=1e-3) and sig["final"] == pytest.approx(1 / 628.3, rel=0.01)


# ---- wiring harness ------------------------------------------------------------------

HARNESS = """
metadata: {title: Test harness}
connectors:
  X1: {type: Molex KK 254, subtype: female, pinlabels: [GND, VCC, RX, TX]}
  X2: {type: JST XH, pinlabels: [GND, VCC, TX, RX]}
  PSU: {type: Screw terminal, pinlabels: [V+, V-]}
cables:
  W1: {gauge: 0.25 mm2, length: 0.2, color_code: DIN, wirecount: 4}
  W2: {gauge: 22 AWG, length: 300 mm, colors: [RD, BK], current_a: 0.5}
connections:
  - - X1: [3-4]
    - W1: [3-4]
    - X2: [4, 3]
  - - PSU: [V+, V-]
    - W2: [1, 2]
    - X1: [VCC, GND]
"""


def test_harness_good_case_writes_svg_csv_json(projects):
    r = e.wiring_diagram("loom", HARNESS, route="builtin")
    assert r["ok"] and r["checks_passed"] and r["error_count"] == 0, r["issues"]
    assert r["wire_count"] == 4 and r["total_length_mm"] == 1000.0  # 2 x 200 + 2 x 300
    w = {(x["cable"], x["wire"]): x for x in r["wires"]}
    assert (w[("W1", 3)]["colour"], w[("W1", 4)]["colour"]) == ("GN", "YE")  # DIN 47100 cores 3 and 4
    assert (w[("W1", 3)]["from"], w[("W1", 3)]["from_label"], w[("W1", 3)]["to_pin"], w[("W1", 3)]["to_label"]) == \
        ("X1", "RX", 4, "RX")  # RX to RX: the crossover is in the pin list
    assert (w[("W2", 1)]["from_pin"], w[("W2", 1)]["to_pin"], w[("W2", 1)]["colour_name"]) == (1, 2, "red")

    root = ET.fromstring(Path(r["files"]["svg"]).read_text())  # well-formed XML
    text = " ".join(t.text or "" for t in root.iter("{http://www.w3.org/2000/svg}text"))
    for expected in ("X1", "PSU", "V+", "W2:1", "22 AWG", "300 mm", "WIRE LIST", "Test harness"):
        assert expected in text
    paths = [p for p in root.iter("{http://www.w3.org/2000/svg}path")]
    assert len(paths) >= 8  # outline + colour stroke per wire

    rows = list(csv.DictReader(open(r["files"]["wires_csv"])))
    assert len(rows) == 4 and rows[0]["cable"] == "W1" and rows[2]["length_mm"] == "300.0"
    assert json.loads(Path(r["files"]["connections_json"]).read_text())["wire_count"] == 4
    assert {(t["gauge"], t["colour"]): t["total_length_mm"] for t in r["cut_totals"]}[("22 AWG", "RD")] == 300.0
    assert r["connectors"][1]["unused_pins"] == [1, 2]  # X2 pins 1 and 2 are spare


def test_harness_accepts_a_dict_too(projects):
    import yaml

    a = e.wiring_diagram("loom", HARNESS, name="a", route="builtin")
    b = e.wiring_diagram("loom", yaml.safe_load(HARNESS), name="b", route="builtin")
    assert a["wires"] == b["wires"]


def test_harness_ampacity_and_voltage_drop(projects):
    r = e.wiring_diagram("loom", HARNESS.replace("current_a: 0.5", "current_a: 8"), name="hot", route="builtin")
    assert r["ok"] and not r["checks_passed"]
    amp = [i for i in r["issues"] if i["code"] == "ampacity"]
    assert len(amp) == 2 and all(i["severity"] == "error" for i in amp) and "7 A" in amp[0]["message"]
    w = next(x for x in r["wires"] if x["cable"] == "W2")
    assert (w["max_current_chassis_a"], w["max_current_bundled_a"]) == (7.0, 0.92)  # 22 AWG, sourced table
    # 22 AWG = 52.9392 ohm/km; 0.3 m at 8 A -> 8 x 52.9392 x 0.0003 = 0.12705 V
    assert w["voltage_drop_v"] == pytest.approx(0.12705, abs=1e-4)
    mild = e.wiring_diagram("loom", HARNESS.replace("current_a: 0.5", "current_a: 2"), name="warm", route="builtin")
    assert mild["checks_passed"] and mild["warning_count"] == 2  # above 0.92 A bundled, below 7 A free air


def test_harness_metric_gauge_maps_to_a_safe_awg_row(projects):
    assert e._wire_rating(e._parse_gauge("0.25 mm2"))["awg"] == 24      # 24 AWG is 0.205 mm2 <= 0.25
    assert e._wire_rating(e._parse_gauge("0.5 mm²"))["awg"] == 21       # 20 AWG (0.519) would overstate it
    assert e._parse_gauge("22 AWG") == {"label": "22 AWG", "awg": 22, "area_mm2": 0.327}
    assert e._parse_gauge(20, "AWG")["awg"] == 20 and e._parse_gauge(None) is None
    assert (e._parse_length_mm(0.2), e._parse_length_mm("300 mm"), e._parse_length_mm(2, "cm")) == (200.0, 300.0, 20.0)


def test_harness_catches_wires_on_missing_pins(projects):
    bad = HARNESS.replace("- X2: [4, 3]", "- X2: [4, 9]").replace("- W2: [1, 2]", "- W2: [1, 3]")
    r = e.wiring_diagram("loom", bad, name="bad", route="builtin")
    codes = [i["code"] for i in r["issues"] if i["severity"] == "error"]
    assert r["ok"] and not r["checks_passed"]
    assert "bad_pin" in codes and "bad_wire" in codes
    assert any("X2 pin 9" in i["message"] for i in r["issues"])


def test_harness_double_booked_pin_needs_a_splice(projects):
    extra = HARNESS.replace("cables:", "  J9: {pinlabels: [SIG]}\ncables:\n  W3: {gauge: 24 AWG, length: 0.1, colors: [BU, WH]}") \
        + "  - - X1: [3, 4]\n    - W3: [1, 2]\n    - J9: [1, 1]\n"
    r = e.wiring_diagram("loom", extra, name="dbl", route="builtin")
    booked = [i["message"] for i in r["issues"] if i["code"] == "double_booked"]
    assert len(booked) == 3  # X1 pin 3, X1 pin 4 and J9 pin 1 each take two wires
    spliced = extra.replace("J9: {pinlabels: [SIG]}", "J9: {pinlabels: [SIG], splice: true}") \
        .replace("X1: {type: Molex KK 254,", "X1: {splice: true, type: Molex KK 254,")
    assert e.wiring_diagram("loom", spliced, name="spl", route="builtin")["checks_passed"]


def test_harness_templates_and_structure_errors(projects):
    ferrules = """
connectors:
  X1: {pinlabels: [A, B]}
  F: {style: simple, type: Crimp ferrule}
cables:
  W1: {wirecount: 2, colors: [RD, BK], gauge: 0.5 mm2, length: 1}
connections:
  - - X1: [1, 2]
    - W1: [1, 2]
    - F.
"""
    r = e.wiring_diagram("loom", ferrules, name="fer", route="builtin")
    assert r["checks_passed"] and [c["name"] for c in r["connectors"]] == ["X1", "F_1"]
    assert e.wiring_diagram("loom", "connectors: {}", route="builtin")["ok"] is False
    unknown = e.wiring_diagram("loom", ferrules.replace("- F.", "- Z9"), name="unk", route="builtin")
    assert unknown["issues"][0]["code"] == "unknown_designator"
    assert e.wiring_diagram("loom", ferrules, name="../x")["ok"] is False


@pytest.mark.skipif(HAVE_WIREVIZ, reason="WireViz is installed; the not-installed path cannot be exercised")
def test_wireviz_missing_gives_install_guidance_and_auto_falls_back(projects):
    r = e.wiring_diagram("loom", HARNESS, name="wv", route="wireviz")
    assert r["ok"] is False and "graphviz" in r["install"] and "wireviz" in r["install"]
    auto = e.wiring_diagram("loom", HARNESS, name="auto")
    assert auto["ok"] and auto["route"] == "builtin" and "wireviz" in auto["note"]


@pytest.mark.skipif(not HAVE_WIREVIZ, reason="WireViz and Graphviz are not installed")
def test_wireviz_route(projects):
    r = e.wiring_diagram("loom", HARNESS, name="wv", route="wireviz")
    assert r["ok"] and r["route"] == "wireviz" and r["files"]["wireviz"]


def test_extension_keys_are_stripped_for_wireviz():
    clean = e._strip_extensions({"connectors": {"X": {"splice": True, "pincount": 2}},
                                 "cables": {"W": {"current_a": 3, "gauge": "1 mm2"}}})
    assert clean == {"connectors": {"X": {"pincount": 2}}, "cables": {"W": {"gauge": "1 mm2"}}}


# ---- power budget and data -----------------------------------------------------------

def test_power_budget_hand_calculation():
    r = e.power_budget(
        [{"name": "mcu", "voltage_v": 5, "current_a": 0.2},
         {"name": "leds", "voltage_v": 5, "current_a": 1.0, "duty": 0.5},
         {"name": "motor", "voltage_v": 12, "current_a": 2.0, "duty": 0.25}],
        battery_capacity_mah=5000, battery_voltage_v=11.1, efficiency=0.9)
    assert r["ok"]
    rails = {x["rail"]: x for x in r["rails"]}
    assert (rails["5V"]["peak_current_a"], rails["5V"]["avg_current_a"]) == (1.2, 0.7)
    assert (rails["5V"]["peak_power_w"], rails["5V"]["avg_power_w"]) == (6.0, 3.5)
    assert (rails["12V"]["peak_power_w"], rails["12V"]["avg_power_w"]) == (24.0, 6.0)
    assert (r["total_peak_power_w"], r["total_avg_power_w"]) == (30.0, 9.5)
    # 5 Ah x 11.1 V = 55.5 Wh; x 0.9 = 49.95 Wh; / 9.5 W = 5.2579 h
    assert r["battery"]["energy_wh"] == 55.5 and r["battery"]["runtime_h"] == pytest.approx(49.95 / 9.5, abs=1e-4)
    assert r["battery"]["avg_battery_current_a"] == pytest.approx(9.5 / 0.9 / 11.1, abs=1e-5)


def test_power_budget_wire_gauge():
    r = e.power_budget([{"name": "motor", "voltage_v": 12, "current_a": 2.0}])
    wire = r["rails"][0]["wire"]
    # Table: 19 AWG carries 1.8 A bundled (too little), 18 AWG carries 2.3 A; 26 AWG carries 2.2 A in free air.
    assert (wire["suggested_awg"], wire["by_ampacity_bundled_awg"], wire["by_ampacity_free_air_awg"]) == (18, 18, 26)
    long_run = e.power_budget([{"name": "led strip", "voltage_v": 5, "current_a": 2.0}], wire_length_m=3, max_drop_pct=3)
    w = long_run["rails"][0]["wire"]
    # Limit 0.15 V over 6 m of conductor at 2 A -> at most 12.5 ohm/km -> 15 AWG (10.44); 16 AWG is 13.17.
    assert w["by_voltage_drop_awg"] == 15 and w["suggested_awg"] == 15
    assert w["voltage_drop_v"] == pytest.approx(2 * 3 * 10.444 / 1000 * 2, abs=1e-3)
    huge = e.power_budget([{"name": "welder", "voltage_v": 12, "current_a": 500}])
    assert huge["rails"][0]["wire"]["suggested_awg"] is None


def test_power_budget_input_errors():
    assert e.power_budget([])["ok"] is False
    assert e.power_budget([{"name": "x", "voltage_v": 5}])["ok"] is False
    assert e.power_budget([{"voltage_v": 5, "current_a": 1, "duty": 2}])["ok"] is False
    assert e.power_budget([{"voltage_v": 5, "current_a": 1}], battery_capacity_mah=1000)["ok"] is False
    mixed = [{"rail": "A", "voltage_v": 5, "current_a": 1}, {"rail": "A", "voltage_v": 12, "current_a": 1}]
    assert e.power_budget(mixed)["ok"] is False


def test_data_files_carry_sources():
    amp = json.loads((common.DATA / "electronics" / "wire_ampacity.json").read_text())
    assert amp["source"].startswith("https://") and amp["basis"] == "estimate"
    assert all(r["source"].startswith("https://") for r in amp["records"])
    by = {r["awg"]: r for r in amp["records"]}
    assert by[22]["max_current_chassis_a"] == 7.0 and by[22]["resistance_ohm_per_km"] == pytest.approx(52.939)
    assert by[18]["area_mm2"] == 0.823
    colours = json.loads((common.DATA / "electronics" / "wire_colours.json").read_text())
    assert all(seq["source"] for seq in colours["sequences"].values())
    assert colours["sequences"]["DIN"]["colours"][:4] == ["WH", "BN", "GN", "YE"]


def test_register_exposes_the_tools():
    names = []

    class Fake:
        def tool(self):
            return lambda fn: names.append(fn.__name__)

    e.register(Fake())
    assert names == ["circuit_write", "circuit_read", "circuit_build", "circuit_simulate", "kicad_check",
                     "kicad_export", "wiring_diagram", "power_budget"]
