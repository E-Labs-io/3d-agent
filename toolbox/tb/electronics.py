"""Electronics tools: circuits as code (SKiDL), KiCad CLI, ngspice, wiring harnesses, power budget.

A project keeps its circuit in projects/<slug>/circuit.py. KiCad symbol libraries are not needed:
circuit.py builds its parts with the helpers in this module (resistor, capacitor, led, diode,
connector, ic, mosfet, regulator, part) which define the pins inline with SKiDL's own SKIDL tool.

Invoked as a runner by circuit_build: python -m tb.electronics <project_dir>
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import struct
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from .common import DATA, TOOLBOX, inside, load_json, project_dir, save_json, which

KICAD_INSTALL = "brew install --cask kicad  (asks for the Mac password; or https://www.kicad.org/download/macos/)"
NGSPICE_INSTALL = "brew install ngspice"
WIREVIZ_INSTALL = "brew install graphviz && uv tool install wireviz  (WireViz is GPL-3: keep it outside the toolbox venv)"

CIRCUIT_TEMPLATE = '''"""{title} - circuit as code (SKiDL). Rebuild with the circuit_build tool after every edit.

Do not call ERC() or generate_netlist() here; circuit_build does both.
"""
from skidl import Net
from tb.electronics import capacitor, connector, led, power_net, regulator, resistor

vin, v5, gnd = power_net("VIN"), power_net("+5V"), power_net("GND")

j1 = connector(3, names=["VIN", "GND", "5V_OUT"], footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")
u1 = regulator("LM7805", footprint="Package_TO_SOT_THT:TO-220-3_Vertical", mpn="L7805CV", manufacturer="STMicroelectronics")
c1 = capacitor("330n", footprint="Capacitor_SMD:C_0805_2012Metric")
c2 = capacitor("100n", footprint="Capacitor_SMD:C_0805_2012Metric")
r1 = resistor("330", footprint="Resistor_SMD:R_0805_2012Metric")
d1 = led("RED", footprint="LED_SMD:LED_0805_2012Metric")

vin += j1["VIN"], u1["IN"], c1[1]
gnd += j1["GND"], u1["GND"], c1[2], c2[2], d1["K"]
v5 += u1["OUT"], c2[1], r1[1], j1["5V_OUT"]
led_a = Net("LED_A")
led_a += r1[2], d1["A"]
'''


# --------------------------------------------------------------------------------------
# Part helpers for circuit.py (SKiDL is imported lazily so the toolbox loads without it)
# --------------------------------------------------------------------------------------

_PIN_FUNCS = {
    "passive": "PASSIVE", "in": "INPUT", "out": "OUTPUT", "bidir": "BIDIR", "tristate": "TRISTATE",
    "power_in": "PWRIN", "power_out": "PWROUT", "open_collector": "OPENCOLL",
    "open_emitter": "OPENEMIT", "nc": "NOCONNECT", "unspecified": "UNSPEC",
}


def _pin_specs(pins) -> list[tuple[str, str, str]]:
    """Normalise a pin description to [(number, name, function)]."""
    specs = []
    items = pins.items() if isinstance(pins, dict) else enumerate(pins, start=1)
    for num, spec in items:
        if isinstance(spec, (tuple, list)):
            if len(spec) == 3:
                num, name, func = spec
            else:
                name, func = spec
        else:
            name, func = spec, "passive"
        if func not in _PIN_FUNCS:
            raise ValueError(f"Unknown pin function {func!r}; use one of {sorted(_PIN_FUNCS)}")
        specs.append((str(num), str(name), func))
    return specs


def part(name: str, pins, ref_prefix: str = "U", value: str = "", footprint: str = "",
         description: str = "", **fields):
    """Create a part with inline pins and add it to the circuit. No KiCad library needed.

    pins: ["IN", "GND", "OUT"] (numbered from 1), {"1": "IN", "2": ("GND", "power_in")}, or
    [(number, name, function)]. Functions: passive, in, out, bidir, tristate, power_in, power_out,
    open_collector, open_emitter, nc, unspecified. Extra keyword arguments (mpn="...",
    manufacturer="...") become netlist fields.
    """
    from skidl import SKIDL, Part, Pin

    p = Part(
        tool=SKIDL, name=name, ref_prefix=ref_prefix, footprint=footprint, description=description,
        pins=[Pin(num=n, name=nm, func=getattr(Pin.types, _PIN_FUNCS[f])) for n, nm, f in _pin_specs(pins)],
    )
    p.value = value or name
    for k, v in fields.items():
        p.fields[k] = str(v)
    return p


def resistor(value: str, footprint: str = "", **fields):
    """Two-pin resistor (pins 1, 2). value is free text such as "330" or "4k7"."""
    return part("R", ["1", "2"], "R", value, footprint, "Resistor", **fields)


def capacitor(value: str, footprint: str = "", polarised: bool = False, **fields):
    """Two-pin capacitor. Pins 1, 2 (polarised: 1 is "+", 2 is "-")."""
    return part("CP" if polarised else "C", ["+", "-"] if polarised else ["1", "2"], "C", value, footprint,
                "Polarised capacitor" if polarised else "Capacitor", **fields)


def led(value: str = "LED", footprint: str = "", **fields):
    """LED. Pin 1 is K (cathode), pin 2 is A (anode), as in KiCad's Device:LED."""
    return part("LED", ["K", "A"], "D", value, footprint, "LED", **fields)


def diode(value: str = "D", footprint: str = "", **fields):
    """Diode. Pin 1 is K (cathode), pin 2 is A (anode), as in KiCad's Device:D."""
    return part("D", ["K", "A"], "D", value, footprint, "Diode", **fields)


def connector(n: int, names: list[str] | None = None, value: str = "", footprint: str = "", **fields):
    """Connector with n pins numbered 1..n. names gives each pin a signal name (default P1..Pn)."""
    if names and len(names) != n:
        raise ValueError(f"connector({n}) got {len(names)} names")
    return part(f"Conn_01x{n:02d}", names or [f"P{i}" for i in range(1, n + 1)], "J",
                value or f"Conn_01x{n:02d}", footprint, f"{n}-pin connector", **fields)


def ic(name: str, pins, value: str = "", footprint: str = "", **fields):
    """Generic IC with named pins. pins as for part(); give power pins the power_in function."""
    return part(name, pins, "U", value or name, footprint, **fields)


def mosfet(value: str, channel: str = "n", pinout: str = "GDS", footprint: str = "", **fields):
    """MOSFET with pins G, D, S. pinout sets which pin number each gets, e.g. "GSD" for SOT-23."""
    if sorted(pinout.upper()) != ["D", "G", "S"]:
        raise ValueError('pinout must be a permutation of "GDS"')
    pins = [(c, "in" if c == "G" else "passive") for c in pinout.upper()]
    return part(f"Q_{'N' if channel.lower().startswith('n') else 'P'}MOS", pins, "Q", value, footprint,
                f"{channel.upper()}-channel MOSFET", **fields)


def regulator(value: str, pinout: tuple[str, str, str] = ("IN", "GND", "OUT"), footprint: str = "", **fields):
    """Three-terminal linear regulator with pins IN, GND, OUT (78xx order by default)."""
    funcs = {"IN": "power_in", "GND": "power_in", "OUT": "power_out"}
    return part(value, [(n, funcs.get(n, "passive")) for n in pinout], "U", value, footprint,
                "Voltage regulator", **fields)


def power_net(name: str):
    """A net marked as a power source, so ERC accepts power-input pins fed from a connector."""
    from skidl import POWER, Net

    n = Net(name)
    n.drive = POWER
    return n


# --------------------------------------------------------------------------------------
# Circuit runner (subprocess side)
# --------------------------------------------------------------------------------------

def _natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


def _runner(project: Path) -> dict:
    import logging
    import runpy
    import warnings

    src = project / "circuit.py"
    if not src.exists():
        raise FileNotFoundError(f"No circuit.py in {project}. Write one with circuit_write.")
    out = project / "out" / "electronics"
    out.mkdir(parents=True, exist_ok=True)
    os.chdir(out)  # SKiDL drops its .log/.erc files in the working directory
    warnings.simplefilter("ignore")
    import skidl

    messages: list[tuple[str, str]] = []

    class _Grab(logging.Handler):
        def emit(self, record):
            messages.append((record.levelname, record.getMessage()))

    skidl.erc_logger.addHandler(_Grab())
    missing_fp: list[str] = []
    skidl.empty_footprint_handler = lambda p: missing_fp.append(p.ref)

    runpy.run_path(str(src), run_name="__circuit__")
    import builtins

    circuit = builtins.default_circuit  # SKiDL keeps its default circuit in builtins
    if not circuit.parts:
        raise ValueError("circuit.py created no parts. Use the helpers in tb.electronics (resistor, ic, ...).")
    for p in circuit.parts:
        if not getattr(p, "tag", None):
            p.tag = p.ref  # stable tag instead of SKiDL's random one, so rebuilds diff cleanly

    messages.clear()
    skidl.ERC()
    netlist_path = out / f"{project.name}.net"
    skidl.generate_netlist(file_=str(netlist_path), do_backup=False)

    parts = []
    for p in sorted(circuit.parts, key=lambda p: _natural(p.ref)):
        parts.append({
            "ref": p.ref, "value": str(p.value), "name": p.name,
            "footprint": getattr(p, "footprint", "") or "",
            "description": getattr(p, "description", "") or "",
            "fields": {k: str(v) for k, v in dict(p.fields).items()},
            "pins": [{"num": str(pin.num), "name": pin.name,
                      "net": pin.net.name if pin.is_connected() and pin.net is not None else None}
                     for pin in p.pins],
        })
    nets = []
    for n in circuit.get_nets():
        pins = sorted(((pin.part.ref, str(pin.num), pin.name) for pin in n.pins),
                      key=lambda t: (_natural(t[0]), _natural(t[1])))
        if pins:
            nets.append({"name": n.name, "pins": [{"ref": r, "pin": num, "name": nm} for r, num, nm in pins]})
    nets.sort(key=lambda n: _natural(n["name"]))
    erc_warnings = [m for lvl, m in messages if lvl == "WARNING"]
    erc_errors = [m for lvl, m in messages if lvl in ("ERROR", "CRITICAL")]
    files = {"netlist": str(netlist_path), "json": str(out / "circuit.json")}
    erc_files = sorted(out.glob("*.erc"))
    if erc_files:
        files["erc_log"] = str(erc_files[-1])
    result = {
        "ok": True, "project": project.name, "netlist_format": skidl.get_default_tool(),
        "part_count": len(parts), "net_count": len(nets),
        "parts": parts, "nets": nets,
        "unconnected_pins": [f"{p['ref']}.{pin['num']}" for p in parts for pin in p["pins"] if pin["net"] is None],
        "missing_footprints": sorted(missing_fp, key=_natural),
        "erc": {"ok": not erc_errors, "errors": erc_errors, "warnings": erc_warnings},
        "files": files,
    }
    save_json(out / "circuit.json", result)
    return result


# --------------------------------------------------------------------------------------
# Circuit tools
# --------------------------------------------------------------------------------------

def circuit_write(project: str, content: str = "", path: str = "circuit.py") -> dict:
    """Write the project's SKiDL circuit (default circuit.py). Empty content writes a working starter.

    Build parts with tb.electronics helpers (resistor, capacitor, led, diode, connector, ic, mosfet,
    regulator, part, power_net); no KiCad libraries are needed. Does not build.
    """
    try:
        d = project_dir(project, create=True)
        f = inside(d, path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    f.parent.mkdir(parents=True, exist_ok=True)
    text = content or CIRCUIT_TEMPLATE.format(title=project)
    f.write_text(text)
    return {"ok": True, "path": str(f), "bytes": len(text), "starter": not content}


def circuit_read(project: str, path: str = "circuit.py") -> dict:
    """Read a text file from the project folder (default circuit.py)."""
    try:
        f = inside(project_dir(project), path)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}
    if not f.is_file():
        return {"ok": False, "error": f"No {path} in project '{project}'. circuit_write(project) writes a starter."}
    return {"ok": True, "path": str(f), "content": f.read_text()}


def circuit_build(project: str) -> dict:
    """Run the project's circuit.py, write a KiCad netlist and run SKiDL's ERC.

    Returns parts (ref, value, footprint, fields such as mpn), nets with their pins, unconnected
    pins, parts missing a footprint, ERC errors/warnings and file paths under out/electronics/.
    On a circuit error returns ok=False with the Python traceback.
    """
    try:
        d = project_dir(project)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}
    import importlib.util

    if importlib.util.find_spec("skidl") is None:  # not imported here: importing SKiDL drops log files in cwd
        return {"ok": False, "error": "SKiDL is not installed in the toolbox environment",
                "install": "uv sync --extra extras"}
    try:
        proc = subprocess.run([sys.executable, "-m", "tb.electronics", str(d)],
                              cwd=TOOLBOX, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "circuit.py did not finish within 180 s"}
    last = proc.stdout.strip().splitlines()[-1:] or [""]
    try:
        return json.loads(last[0])
    except json.JSONDecodeError:
        return {"ok": False, "error": "Circuit process produced no result", "stderr": proc.stderr[-1800:]}


# --------------------------------------------------------------------------------------
# KiCad command line. Subcommands and flags follow https://docs.kicad.org/10.0/en/cli/cli.html
# --------------------------------------------------------------------------------------

# action -> (input suffix, kicad-cli arguments, output name ("" = directory), output is a directory)
_KICAD_ACTIONS: dict[str, tuple[str, list[str], str, bool]] = {
    "erc": (".kicad_sch", ["sch", "erc", "--format", "json", "--severity-all"], "erc.json", False),
    "drc": (".kicad_pcb", ["pcb", "drc", "--format", "json", "--severity-all"], "drc.json", False),
    "pdf": (".kicad_sch", ["sch", "export", "pdf"], "schematic.pdf", False),
    "svg": (".kicad_sch", ["sch", "export", "svg"], "schematic_svg", True),
    "bom": (".kicad_sch", ["sch", "export", "bom"], "bom.csv", False),
    "netlist": (".kicad_sch", ["sch", "export", "netlist", "--format", "kicadsexpr"], "schematic.net", False),
    "spice": (".kicad_sch", ["sch", "export", "netlist", "--format", "spice"], "schematic.cir", False),
    "gerbers": (".kicad_pcb", ["pcb", "export", "gerbers"], "gerbers", True),
    "drill": (".kicad_pcb", ["pcb", "export", "drill"], "gerbers", True),
    "step": (".kicad_pcb", ["pcb", "export", "step", "--force", "--subst-models"], "board.step", False),
}


def _kicad_argv(exe: str, action: str, src: Path, out_dir: Path) -> tuple[list[str], Path]:
    suffix, args, name, is_dir = _KICAD_ACTIONS[action]
    if src.suffix != suffix:
        raise ValueError(f"'{action}' needs a {suffix} file, got {src.name}")
    target = out_dir / name
    return [exe, *args, "--output", str(target) + ("/" if is_dir else ""), str(src)], target


def _kicad_run(project: str, file: str, action: str) -> dict:
    if action not in _KICAD_ACTIONS:
        return {"ok": False, "error": f"Unknown action {action!r}. Options: {sorted(_KICAD_ACTIONS)}"}
    exe = which("kicad-cli")
    if not exe:
        return {"ok": False, "error": "KiCad is not installed (kicad-cli not found)", "install": KICAD_INSTALL}
    try:
        d = project_dir(project)
        src = inside(d, file)
        if not src.is_file():
            return {"ok": False, "error": f"No such file in project: {file}"}
        out_dir = d / "out" / "electronics" / "kicad"
        argv, target = _kicad_argv(exe, action, src, out_dir)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}
    (target if _KICAD_ACTIONS[action][3] else target.parent).mkdir(parents=True, exist_ok=True)
    if target.is_file():
        target.unlink()  # so a file left by an earlier run cannot pass for this one
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"kicad-cli {action} did not finish within 600 s"}
    files = sorted(str(p) for p in target.glob("*")) if target.is_dir() else ([str(target)] if target.exists() else [])
    if not files or (proc.returncode != 0 and target.is_dir()):
        return {"ok": False, "error": f"kicad-cli {action} failed (exit {proc.returncode})",
                "stderr": (proc.stderr or proc.stdout)[-1500:], "command": argv}
    res = {"ok": True, "action": action, "files": files, "command": argv, "_target": target}
    if proc.returncode != 0:
        # kicad-cli writes the file and still exits non-zero when it had to skip something,
        # e.g. a STEP export where a part has no 3D model.
        lines = [ln for ln in (proc.stderr or proc.stdout).splitlines() if ln.strip() and "NSCocoaErrorDomain" not in ln]
        res.update(exit_code=proc.returncode, warnings=sorted(set(lines))[:20])
    return res


def _violations(node) -> list[dict]:
    """Collect every violation entry from a kicad-cli ERC/DRC JSON report."""
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("violations", "unconnected_items", "schematic_parity") and isinstance(v, list):
                found += [x for x in v if isinstance(x, dict)]
            else:
                found += _violations(v)
    elif isinstance(node, list):
        for v in node:
            found += _violations(v)
    return found


def kicad_check(project: str, file: str) -> dict:
    """Run KiCad ERC on a .kicad_sch or DRC on a .kicad_pcb in the project (needs KiCad installed).

    Returns error and warning counts, the violations (type, severity, description) and the JSON report path.
    """
    action = {".kicad_sch": "erc", ".kicad_pcb": "drc"}.get(Path(file).suffix)
    if not action:
        return {"ok": False, "error": "file must be a .kicad_sch (ERC) or .kicad_pcb (DRC)"}
    res = _kicad_run(project, file, action)
    if not res["ok"]:
        return res
    report = load_json(res.pop("_target"), {}) or {}
    items = _violations(report)
    rows = [{"type": v.get("type"), "severity": v.get("severity"), "description": v.get("description")} for v in items]
    return {**res, "check": action,
            "error_count": sum(1 for r in rows if r["severity"] == "error"),
            "warning_count": sum(1 for r in rows if r["severity"] == "warning"),
            "violations": rows[:200], "report": res["files"][0]}


def kicad_export(project: str, file: str, what: str) -> dict:
    """Export from a KiCad file in the project with kicad-cli (needs KiCad installed).

    what for a .kicad_sch: pdf, svg, bom (CSV), netlist, spice. For a .kicad_pcb: gerbers, drill, step.
    Returns the written file paths under out/electronics/kicad/.
    """
    if what in ("erc", "drc"):
        return {"ok": False, "error": "Use kicad_check for ERC/DRC"}
    res = _kicad_run(project, file, what)
    res.pop("_target", None)
    return res


# --------------------------------------------------------------------------------------
# Simulation (ngspice, batch mode)
# --------------------------------------------------------------------------------------

_ANALYSES = ("op", "tran", "ac", "dc", "noise", "tf", "sens")


def _spice_deck(netlist: str, analysis: str) -> str:
    """Add the analysis card to a netlist unless it already has one, and make sure it ends with .end."""
    lines = [ln.rstrip() for ln in netlist.strip().splitlines()]
    lines = [ln for ln in lines if ln.strip().lower() != ".end"]
    # SPICE reads line one as the title, so a netlist that opens with a part would silently lose it.
    if lines and re.match(r"(\.|\*|[a-z]+\d\S*\s+\S+\s+\S+)", lines[0].strip().lower()):
        lines.insert(0, "* circuit")
    has = any(re.match(rf"\.({'|'.join(_ANALYSES)})\b", ln.strip().lower()) for ln in lines)
    if not has:
        card = analysis.strip()
        lines.append(card if card.startswith(".") else "." + card)
    return "\n".join(lines + [".end"]) + "\n"


def _parse_raw(data: bytes) -> list[dict]:
    """Parse an ngspice rawfile (ASCII or binary, one or more plots) into {plot, variables, values}."""
    plots = []
    pos = 0
    while pos < len(data):
        m = re.compile(rb"^(Values|Binary):[ \t]*\r?\n", re.M).search(data, pos)
        if not m:
            break
        header = data[pos:m.start()].decode("utf-8", "replace")
        info = dict(re.findall(r"^(Title|Plotname|Flags|No\. Variables|No\. Points):[ \t]*(.*)$", header, re.M))
        nvar, npts = int(info["No. Variables"]), int(info["No. Points"])
        is_complex = "complex" in info.get("Flags", "")
        names = [ln.split()[1] for ln in re.split(r"^Variables:", header, maxsplit=1, flags=re.M)[1].strip().splitlines()[:nvar]]
        cols: list[list] = [[] for _ in range(nvar)]
        pos = m.end()
        if m.group(1) == b"Binary":
            width = 16 if is_complex else 8
            for _ in range(npts):
                for i in range(nvar):
                    chunk = data[pos:pos + width]
                    pos += width
                    v = struct.unpack("<dd" if is_complex else "<d", chunk)
                    cols[i].append(complex(*v) if is_complex else v[0])
        else:
            end = re.compile(rb"^Title:", re.M).search(data, pos)
            block = data[pos:end.start() if end else len(data)].decode("utf-8", "replace")
            pos = end.start() if end else len(data)
            tokens = block.split()
            t = 0
            for _ in range(npts):
                t += 1  # point index
                for i in range(nvar):
                    tok = tokens[t]
                    t += 1
                    if is_complex:
                        re_, im_ = tok.split(",")
                        cols[i].append(complex(float(re_), float(im_)))
                    else:
                        cols[i].append(float(tok))
        plots.append({"plot": info.get("Plotname", ""), "complex": is_complex, "points": npts,
                      "variables": names, "values": dict(zip(names, cols))})
    return plots


def _summarise_plot(plot: dict) -> dict:
    """Numbers for one analysis: single values for one-point plots, min/max/final for sweeps."""
    def num(v):
        return {"mag": abs(v), "phase_deg": math.degrees(math.atan2(v.imag, v.real))} if isinstance(v, complex) else v

    if plot["points"] == 1:
        return {"plot": plot["plot"], "points": 1, "values": {k: num(v[0]) for k, v in plot["values"].items()}}
    sweep = plot["variables"][0]
    out = {"plot": plot["plot"], "points": plot["points"], "sweep": sweep, "signals": {}}
    for k, v in plot["values"].items():
        mags = [abs(x) if isinstance(x, complex) else x for x in v]
        out["signals"][k] = {"min": min(mags), "max": max(mags), "first": mags[0], "final": mags[-1]}
    return out


def circuit_simulate(project: str, netlist: str, analysis: str = "op", route: str = "auto") -> dict:
    """Simulate a SPICE netlist with ngspice in batch mode and return the results as numbers.

    netlist: SPICE text, or a path to a netlist file inside the project. analysis: an ngspice
    analysis card without the dot, e.g. "op", "tran 10u 20m", "dc V1 0 5 0.1", "ac dec 20 10 1meg"
    (ignored if the netlist already has one). Volts, amps, seconds, hertz. One-point analyses return
    each node value; sweeps return min/max/first/final per signal and the full data in a JSON file.
    """
    if route not in ("auto", "ngspice"):
        return {"ok": False, "error": f"Unknown route {route!r}. Options: auto, ngspice"}
    exe = which("ngspice")
    if not exe:
        return {"ok": False, "error": "ngspice is not installed", "install": NGSPICE_INSTALL}
    if analysis.strip().lstrip(".").split(" ")[0].lower() not in _ANALYSES:
        return {"ok": False, "error": f"analysis must start with one of {_ANALYSES}"}
    try:
        d = project_dir(project, create=True)
        text = netlist
        if "\n" not in netlist.strip():
            f = inside(d, netlist.strip())
            if not f.is_file():
                return {"ok": False, "error": f"No such netlist in project: {netlist}"}
            text = f.read_text()
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    out = d / "out" / "electronics" / "sim"
    out.mkdir(parents=True, exist_ok=True)
    deck, raw, log = out / "deck.cir", out / "result.raw", out / "ngspice.log"
    deck.write_text(_spice_deck(text, analysis))
    raw.unlink(missing_ok=True)
    try:
        proc = subprocess.run([exe, "-b", "-r", str(raw), "-o", str(log), str(deck)], cwd=out,
                              capture_output=True, text=True, timeout=300,
                              env={**os.environ, "SPICE_ASCIIRAWFILE": "1"})
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ngspice did not finish within 300 s"}
    log_text = log.read_text(errors="replace") if log.exists() else ""
    if not raw.exists():
        return {"ok": False, "error": f"ngspice produced no results (exit {proc.returncode})",
                "log": (log_text or proc.stderr)[-1800:], "deck": str(deck)}
    plots = _parse_raw(raw.read_bytes())
    data_file = out / "result.json"
    save_json(data_file, [{**p, "values": {k: [[x.real, x.imag] if isinstance(x, complex) else x for x in v]
                                           for k, v in p["values"].items()}} for p in plots])
    warnings = sorted({ln.strip() for ln in log_text.splitlines() if re.match(r"\s*(warning|error)\b", ln, re.I)})
    return {"ok": True, "route": "ngspice", "analyses": [_summarise_plot(p) for p in plots], "warnings": warnings,
            "files": {"deck": str(deck), "raw": str(raw), "log": str(log), "data": str(data_file)}}


# --------------------------------------------------------------------------------------
# Wire data
# --------------------------------------------------------------------------------------

def _ampacity_table() -> list[dict]:
    return (load_json(DATA / "electronics" / "wire_ampacity.json", {}) or {}).get("records", [])


def _colour_data() -> dict:
    return load_json(DATA / "electronics" / "wire_colours.json", {}) or {}


def _parse_gauge(gauge, unit: str | None = None) -> dict | None:
    """'0.25 mm2', '22 AWG', 'AWG22' or a number (mm2 unless unit says AWG) -> {label, awg, area_mm2}."""
    if gauge in (None, ""):
        return None
    text = f"{gauge} {unit or ''}".strip().lower().replace("²", "2")
    m = re.search(r"[-+]?\d*\.?\d+", text)
    if not m:
        return None
    value = float(m.group())
    if "awg" in text:
        awg = int(value)
        row = next((r for r in _ampacity_table() if r["awg"] == awg), None)
        return {"label": f"{awg} AWG", "awg": awg, "area_mm2": row["area_mm2"] if row else None}
    return {"label": f"{value:g} mm²", "awg": None, "area_mm2": value}


def _wire_rating(gauge: dict | None) -> dict | None:
    """Ampacity row for a gauge. A metric size takes the largest AWG row that is not bigger than it."""
    if not gauge:
        return None
    table = _ampacity_table()
    if gauge["awg"] is not None:
        return next((r for r in table if r["awg"] == gauge["awg"]), None)
    fits = [r for r in table if r["area_mm2"] <= gauge["area_mm2"] * 1.02]
    return max(fits, key=lambda r: r["area_mm2"]) if fits else None


def _parse_length_mm(length, unit: str | None = None) -> float | None:
    if length in (None, ""):
        return None
    m = re.match(r"\s*([-+]?\d*\.?\d+)\s*([a-zA-Z\"']*)", str(length))
    if not m:
        return None
    u = (m.group(2) or unit or "m").lower()
    factor = {"mm": 1, "cm": 10, "m": 1000, "in": 25.4, '"': 25.4, "ft": 304.8, "'": 304.8}.get(u)
    return round(float(m.group(1)) * factor, 3) if factor else None


# --------------------------------------------------------------------------------------
# Wiring harness: model, checks, outputs
# --------------------------------------------------------------------------------------

_EXTENSION_KEYS = {"splice", "current_a"}  # ours, stripped before a file is handed to WireViz
_ARROW = re.compile(r"^[<=\-]+>?$|^<?[=\-]+$")


def _expand_pins(spec) -> list:
    """WireViz pin lists: 3, 'GND', '1-4', [1, 2, '5-7'] -> flat list."""
    out = []
    for item in spec if isinstance(spec, list) else [spec]:
        m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", item) if isinstance(item, str) else None
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out += list(range(a, b + 1)) if b >= a else list(range(a, b - 1, -1))
        else:
            out.append(item)
    return out


def _connector_model(name: str, spec: dict) -> dict:
    spec = spec or {}
    labels = list(spec.get("pinlabels") or [])
    pins = list(spec.get("pins") or [])
    count = int(spec.get("pincount") or len(pins) or len(labels) or 1)
    pins = pins or list(range(1, count + 1))
    labels += [""] * (len(pins) - len(labels))
    kind = " ".join(str(spec.get(k, "")) for k in ("type", "subtype")).strip()
    splice = bool(spec.get("splice")) or spec.get("style") == "simple" or "splice" in kind.lower()
    return {"name": name, "type": kind, "pins": pins, "labels": [str(x) for x in labels[:len(pins)]], "splice": splice}


def _cable_model(name: str, spec: dict, colours: dict) -> dict:
    spec = spec or {}
    cols = list(spec.get("colors") or [])
    count = int(spec.get("wirecount") or len(cols) or 1)
    if not cols and spec.get("color_code"):
        cols = list((colours.get("sequences", {}).get(str(spec["color_code"]).upper(), {}) or {}).get("colours", []))
    if not cols and spec.get("color"):
        cols = [spec["color"]] * count
    cols = [str(c) for c in cols[:count]] + [""] * (count - len(cols))
    current = spec.get("current_a")
    currents = ([float(x) for x in current] + [None] * count)[:count] if isinstance(current, list) \
        else [float(current) if current is not None else None] * count
    return {"name": name, "type": str(spec.get("type", "")), "wirecount": count, "colours": cols,
            "gauge": _parse_gauge(spec.get("gauge"), spec.get("gauge_unit")),
            "length_mm": _parse_length_mm(spec.get("length"), spec.get("length_unit")),
            "shield": bool(spec.get("shield")), "currents": currents}


def _resolve_pin(conn: dict, ref):
    """Match a pin reference (number or unique label) to the connector's pin id, or None."""
    for p in conn["pins"]:
        if p == ref or str(p) == str(ref):
            return p
    hits = [p for p, lab in zip(conn["pins"], conn["labels"]) if lab and lab == str(ref)]
    return hits[0] if len(hits) == 1 else None


def _harness_model(harness: dict) -> dict:
    """Turn a WireViz-style dict into connectors, cables, a flat wire list and a list of check results."""
    colours = _colour_data()
    issues: list[dict] = []

    def issue(severity: str, code: str, message: str) -> None:
        issues.append({"severity": severity, "code": code, "message": message})

    templates_c = harness.get("connectors") or {}
    templates_w = harness.get("cables") or {}
    connectors: dict[str, dict] = {}
    cables: dict[str, dict] = {}
    auto = {"n": 0}

    def instance(designator: str):
        """Return ('connector'|'cable', model), creating instances of 'Template.name' on demand."""
        template, _, inst = designator.partition(".")
        if "." in designator and not inst:
            auto["n"] += 1
            inst_name = f"{template}_{auto['n']}"
        else:
            inst_name = designator if "." not in designator else inst
        if designator in templates_c or (template in templates_c and "." in designator):
            key = designator if designator in templates_c else inst_name
            src = templates_c.get(designator, templates_c.get(template))
            return "connector", connectors.setdefault(key, _connector_model(key, src))
        if designator in templates_w or (template in templates_w and "." in designator):
            key = designator if designator in templates_w else inst_name
            src = templates_w.get(designator, templates_w.get(template))
            return "cable", cables.setdefault(key, _cable_model(key, src, colours))
        return None, None

    wires: list[dict] = []
    for idx, cset in enumerate(harness.get("connections") or [], start=1):
        items = []
        for entry in cset if isinstance(cset, list) else [cset]:
            if isinstance(entry, str) and _ARROW.match(entry.strip()):
                continue
            name, pins = (next(iter(entry.items())) if isinstance(entry, dict) else (entry, None))
            kind, model = instance(str(name))
            if not model:
                issue("error", "unknown_designator", f"Connection set {idx}: '{name}' is not a defined connector or cable")
                items = []
                break
            items.append([kind, model, _expand_pins(pins) if pins is not None else None])
        if not items:
            continue
        width = max((len(p) for _, _, p in items if p), default=1)
        for it in items:
            if it[2] is None:
                it[2] = [it[1]["pins"][0]] * width if it[0] == "connector" else list(range(1, width + 1))
            elif len(it[2]) == 1 and width > 1 and it[0] == "connector":
                it[2] = it[2] * width
        if any(len(p) != width for _, _, p in items):
            issue("error", "length_mismatch",
                  f"Connection set {idx}: pin lists differ in length ({[len(p) for _, _, p in items]})")
            continue
        for i, (kind, cable, wire_ids) in enumerate(items):
            if kind != "cable":
                continue
            left = items[i - 1] if i > 0 and items[i - 1][0] == "connector" else None
            right = items[i + 1] if i + 1 < len(items) and items[i + 1][0] == "connector" else None
            for k, wid in enumerate(wire_ids):
                shield = str(wid).lower() == "s"
                if shield and not cable["shield"]:
                    issue("error", "no_shield", f"{cable['name']} has no shield but connection set {idx} uses 's'")
                    continue
                if not shield and not (isinstance(wid, int) and 1 <= wid <= cable["wirecount"]):
                    issue("error", "bad_wire", f"{cable['name']} has {cable['wirecount']} wire(s); "
                                               f"connection set {idx} uses wire {wid!r}")
                    continue
                ends = []
                for side in (left, right):
                    if side is None:
                        ends.append(None)
                        continue
                    conn = side[1]
                    pin = _resolve_pin(conn, side[2][k])
                    if pin is None:
                        issue("error", "bad_pin", f"{cable['name']}:{wid} lands on {conn['name']} pin "
                                                  f"{side[2][k]!r}, which does not exist")
                        ends.append(False)
                        continue
                    ends.append({"connector": conn["name"], "pin": pin,
                                 "label": conn["labels"][conn["pins"].index(pin)]})
                if False in ends:
                    continue
                wi = None if shield else wid - 1
                wires.append({"cable": cable["name"], "wire": "s" if shield else wid,
                              "colour": "" if shield else cable["colours"][wi],
                              "gauge": cable["gauge"], "length_mm": cable["length_mm"],
                              "current_a": None if shield else cable["currents"][wi],
                              "from": ends[0], "to": ends[1]})

    _check_harness(connectors, cables, wires, issue, colours)
    return {"connectors": connectors, "cables": cables, "wires": wires, "issues": issues}


def _check_harness(connectors: dict, cables: dict, wires: list[dict], issue, colours: dict) -> None:
    names = colours.get("codes", {}).get("names", {})
    used_pins: dict[tuple, list[str]] = {}
    used_wires: dict[tuple, int] = {}
    for w in wires:
        tag = f"{w['cable']}:{w['wire']}"
        used_wires[(w["cable"], w["wire"])] = used_wires.get((w["cable"], w["wire"]), 0) + 1
        for end in (w["from"], w["to"]):
            if end:
                used_pins.setdefault((end["connector"], end["pin"]), []).append(tag)
        if w["from"] is None or w["to"] is None:
            issue("warning", "open_end", f"{tag} is connected at one end only")
        w["colour_name"] = "/".join(names.get(w["colour"][i:i + 2], w["colour"][i:i + 2])
                                    for i in range(0, len(w["colour"]), 2))
        rating = _wire_rating(w["gauge"])
        w["awg_equivalent"] = rating["awg"] if rating else None
        w["max_current_chassis_a"] = rating["max_current_chassis_a"] if rating else None
        w["max_current_bundled_a"] = rating["max_current_power_transmission_a"] if rating else None
        w["voltage_drop_v"] = None
        if w["current_a"] is None:
            continue
        if not rating:
            issue("warning", "no_gauge", f"{tag} carries {w['current_a']:g} A but has no gauge (or one outside "
                                         "the ampacity table), so it cannot be checked")
            continue
        if w["length_mm"]:
            w["voltage_drop_v"] = round(w["current_a"] * rating["resistance_ohm_per_km"] * w["length_mm"] / 1e6, 4)
        if w["current_a"] > rating["max_current_chassis_a"]:
            issue("error", "ampacity", f"{tag} ({w['gauge']['label']}) carries {w['current_a']:g} A, above the "
                                       f"{rating['max_current_chassis_a']:g} A free-air limit for {rating['awg']} AWG")
        elif w["current_a"] > rating["max_current_power_transmission_a"]:
            issue("warning", "ampacity", f"{tag} ({w['gauge']['label']}) carries {w['current_a']:g} A, above the "
                                         f"conservative {rating['max_current_power_transmission_a']:g} A limit for "
                                         f"bundled or long runs of {rating['awg']} AWG (free-air limit "
                                         f"{rating['max_current_chassis_a']:g} A)")
    for (cname, pin), tags in used_pins.items():
        if len(tags) > 1 and not connectors[cname]["splice"]:
            issue("error", "double_booked", f"{cname} pin {pin} takes {len(tags)} wires ({', '.join(tags)}); "
                                            "mark the connector 'splice: true' if that is intended")
    for (cname, wid), n in used_wires.items():
        if n > 1:
            issue("error", "wire_reused", f"{cname}:{wid} is used {n} times")
    for c in cables.values():
        spare = [i for i in range(1, c["wirecount"] + 1) if (c["name"], i) not in used_wires]
        if spare:
            issue("info", "spare_wires", f"{c['name']} has unused wire(s): {spare}")
    for c in connectors.values():
        c["unused_pins"] = [p for p in c["pins"] if (c["name"], p) not in used_pins]


_WIRE_COLUMNS = ["cable", "wire", "colour", "colour_name", "gauge", "awg_equivalent", "length_mm",
                 "from", "from_pin", "from_label", "to", "to_pin", "to_label",
                 "current_a", "max_current_chassis_a", "max_current_bundled_a", "voltage_drop_v"]


def _wire_rows(wires: list[dict]) -> list[dict]:
    rows = []
    for w in wires:
        f, t = w["from"] or {}, w["to"] or {}
        rows.append({
            "cable": w["cable"], "wire": w["wire"], "colour": w["colour"], "colour_name": w.get("colour_name", ""),
            "gauge": w["gauge"]["label"] if w["gauge"] else "", "awg_equivalent": w.get("awg_equivalent"),
            "length_mm": w["length_mm"],
            "from": f.get("connector", ""), "from_pin": f.get("pin", ""), "from_label": f.get("label", ""),
            "to": t.get("connector", ""), "to_pin": t.get("pin", ""), "to_label": t.get("label", ""),
            "current_a": w["current_a"], "max_current_chassis_a": w.get("max_current_chassis_a"),
            "max_current_bundled_a": w.get("max_current_bundled_a"), "voltage_drop_v": w.get("voltage_drop_v"),
        })
    return rows


def _cut_totals(rows: list[dict]) -> list[dict]:
    """Total wire length to buy per gauge and colour (mm)."""
    totals: dict[tuple, dict] = {}
    for r in rows:
        t = totals.setdefault((r["gauge"], r["colour"]), {"gauge": r["gauge"], "colour": r["colour"],
                                                          "pieces": 0, "total_length_mm": 0.0})
        t["pieces"] += 1
        t["total_length_mm"] = round(t["total_length_mm"] + (r["length_mm"] or 0), 3)
    return list(totals.values())


# ---- SVG rendering -------------------------------------------------------------------

_PAPER, _INK, _HAIR, _PANEL, _MUTED = "#F6F4EF", "#17161A", "#E8E4DA", "#FDFCF9", "#6f6d75"
_MONO = "'JetBrains Mono', ui-monospace, Menlo, monospace"
_SANS = "'Space Grotesk', system-ui, sans-serif"
_BOX_W, _GAP_X, _ROW, _HEAD, _GAP_Y, _MARGIN = 170, 330, 22, 40, 30, 36


def _text(x, y, s, size=10, font=_MONO, fill=_INK, anchor="start", weight="400", halo=False) -> str:
    extra = f' stroke="{_PAPER}" stroke-width="4" paint-order="stroke" stroke-linejoin="round"' if halo else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}"{extra}>{escape(str(s))}</text>')


def _columns(connectors: dict, wires: list[dict]) -> dict[str, int]:
    """Left-to-right column per connector: a connector sits right of everything that feeds it."""
    col = {name: 0 for name in connectors}
    for _ in range(len(connectors)):
        changed = False
        for w in wires:
            if w["from"] and w["to"] and w["from"]["connector"] != w["to"]["connector"]:
                a, b = w["from"]["connector"], w["to"]["connector"]
                if col[b] < col[a] + 1 and col[a] + 1 < len(connectors):
                    col[b] = col[a] + 1
                    changed = True
        if not changed:
            break
    return col


def _harness_svg(model: dict, title: str) -> str:
    connectors, wires = model["connectors"], model["wires"]
    hexes = _colour_data().get("codes", {}).get("render_hex", {})
    col = _columns(connectors, wires)
    ncols = max(col.values(), default=0) + 1
    top = _MARGIN + 34
    y_next = [top] * ncols
    box: dict[str, tuple[float, float, float]] = {}
    for name, c in connectors.items():
        h = _HEAD + _ROW * len(c["pins"]) + 6
        x = _MARGIN + col[name] * (_BOX_W + _GAP_X)
        box[name] = (x, y_next[col[name]], h)
        y_next[col[name]] += h + _GAP_Y
    diagram_bottom = max(y_next + [top + 60])
    rows = _wire_rows(wires)
    issues = [i for i in model["issues"] if i["severity"] != "info"]
    table_cols = [("CABLE", 0), ("WIRE", 80), ("COLOUR", 130), ("GAUGE", 250), ("LENGTH", 340),
                  ("FROM", 430), ("TO", 600), ("LOAD / LIMIT", 770)]
    width = max(_MARGIN * 2 + ncols * _BOX_W + (ncols - 1) * _GAP_X, _MARGIN * 2 + 900)
    table_top = diagram_bottom + 26
    issues_top = table_top + 30 + 18 * len(rows) + 22
    height = issues_top + (24 + 16 * len(issues) if issues else 0) + _MARGIN

    def pin_xy(end: dict, side: str) -> tuple[float, float]:
        x, y, _ = box[end["connector"]]
        i = connectors[end["connector"]]["pins"].index(end["pin"])
        return (x + _BOX_W if side == "right" else x), y + _HEAD + _ROW * i + _ROW / 2

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
         f'width="{width:.0f}" height="{height:.0f}">',
         f'<rect width="100%" height="100%" fill="{_PAPER}"/>',
         _text(_MARGIN, _MARGIN + 6, title, 16, _SANS, weight="600"),
         _text(width - _MARGIN, _MARGIN + 6, f"{len(connectors)} CONNECTORS · {len(wires)} WIRES", 9, fill=_MUTED,
               anchor="end")]

    labels: list[str] = []  # drawn after every wire so no wire runs over a label
    per_pin: dict[tuple, int] = {}
    for w in wires:
        tag = f"{w['cable']}:{w['wire']}"
        a, b = w["from"], w["to"]
        if a and b:
            flip = col[a["connector"]] > col[b["connector"]]
            (x1, y1), (x2, y2) = pin_xy(a, "left" if flip else "right"), pin_xy(b, "right" if flip else "left")
            if a["connector"] == b["connector"] or col[a["connector"]] == col[b["connector"]]:
                x1, y1 = pin_xy(a, "right")
                x2, y2 = pin_xy(b, "right")
                bend = 70 + 0.25 * abs(y2 - y1)
                d = f"M{x1:.1f},{y1:.1f} C{x1 + bend:.1f},{y1:.1f} {x2 + bend:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
                lx, ly, anchor = x1 + 10, y1, "start"
            else:
                dx = (x2 - x1) * 0.45
                d = f"M{x1:.1f},{y1:.1f} C{x1 + dx:.1f},{y1:.1f} {x2 - dx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
                # Label near the source pin, where wires are still a full row apart and cannot overlap.
                # A second wire on the same pin is labelled at its far end instead.
                shared = per_pin.get((a["connector"], a["pin"]), 0) % 2 == 1
                t = 0.9 if shared else 0.1
                u = 1 - t
                lx = u**3 * x1 + 3 * u * u * t * (x1 + dx) + 3 * u * t * t * (x2 - dx) + t**3 * x2
                ly = u**3 * y1 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y2
                anchor = "end" if flip != shared else "start"
        else:
            end = a or b
            x1, y1 = pin_xy(end, "right" if a else "left")
            x2 = x1 + (90 if a else -90)
            d = f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y1:.1f}"
            o.append(f'<circle cx="{x2:.1f}" cy="{y1:.1f}" r="3.5" fill="{_PAPER}" stroke="{_INK}"/>')
            lx, ly, anchor = (x1 + x2) / 2, y1 - 8, "middle"
        codes = [w["colour"][i:i + 2] for i in range(0, len(w["colour"]), 2)] or [""]
        base = hexes.get(codes[0], "#b9b6ad" if w["wire"] != "s" else "#8d8d93")
        o.append(f'<path d="{d}" fill="none" stroke="{_INK}" stroke-width="4.4" stroke-linecap="round"/>')
        o.append(f'<path d="{d}" fill="none" stroke="{base}" stroke-width="2.8" stroke-linecap="round"'
                 + (' stroke-dasharray="2 3"' if w["wire"] == "s" else "") + "/>")
        if len(codes) > 1 and codes[1] in hexes:
            o.append(f'<path d="{d}" fill="none" stroke="{hexes[codes[1]]}" stroke-width="2.8" '
                     'stroke-dasharray="7 7"/>')
        bits = [tag, w["colour"] or ("shield" if w["wire"] == "s" else ""),
                w["gauge"]["label"] if w["gauge"] else "",
                f"{w['length_mm']:g} mm" if w["length_mm"] else ""]
        origin = a or b
        nth = per_pin.get((origin["connector"], origin["pin"]), 0)  # wires sharing a pin get staggered labels
        per_pin[(origin["connector"], origin["pin"])] = nth + 1
        labels.append(_text(lx, ly + (11 if nth >= 2 else -5), " · ".join(b for b in bits if b), 8.5,
                            anchor=anchor, halo=True))
    o += labels

    for name, c in connectors.items():
        x, y, h = box[name]
        o.append(f'<rect x="{x}" y="{y}" width="{_BOX_W}" height="{h}" rx="3" fill="{_PANEL}" stroke="{_INK}" '
                 'stroke-width="1.2"/>')
        o.append(_text(x + 10, y + 17, name, 12, weight="700"))
        sub = (c["type"] or "") + ("  SPLICE" if c["splice"] and "splice" not in c["type"].lower() else "")
        o.append(_text(x + 10, y + 31, sub.strip().upper()[:26], 7.5, fill=_MUTED))
        o.append(f'<line x1="{x}" y1="{y + _HEAD - 2}" x2="{x + _BOX_W}" y2="{y + _HEAD - 2}" stroke="{_INK}" '
                 'stroke-width="0.8"/>')
        for i, (pin, label) in enumerate(zip(c["pins"], c["labels"])):
            py = y + _HEAD + _ROW * i
            if i:
                o.append(f'<line x1="{x}" y1="{py}" x2="{x + _BOX_W}" y2="{py}" stroke="{_HAIR}"/>')
            o.append(_text(x + 10, py + 15, pin, 10, weight="700"))
            o.append(_text(x + 40, py + 15, label[:19], 10, _SANS))

    ty = table_top
    o.append(f'<line x1="{_MARGIN}" y1="{ty}" x2="{width - _MARGIN}" y2="{ty}" stroke="{_INK}" stroke-width="1"/>')
    o.append(_text(_MARGIN, ty + 16, "WIRE LIST", 9, weight="700"))
    for head, dx in table_cols:
        o.append(_text(_MARGIN + dx, ty + 34, head, 8, fill=_MUTED))
    for n, r in enumerate(rows):
        ry = ty + 52 + 18 * n
        o.append(f'<line x1="{_MARGIN}" y1="{ry - 13}" x2="{width - _MARGIN}" y2="{ry - 13}" stroke="{_HAIR}"/>')
        load = "—" if r["current_a"] is None else f"{r['current_a']:g} A"
        limit = "—" if r["max_current_chassis_a"] is None else f"{r['max_current_chassis_a']:g} A"
        cells = [r["cable"], r["wire"], f"{r['colour']} {r['colour_name']}".strip(), r["gauge"],
                 f"{r['length_mm']:g} mm" if r["length_mm"] else "",
                 f"{r['from']}:{r['from_pin']} {r['from_label']}".strip(": ") if r["from"] else "—",
                 f"{r['to']}:{r['to_pin']} {r['to_label']}".strip(": ") if r["to"] else "—",
                 f"{load} / {limit}"]
        for (_, dx), cell in zip(table_cols, cells):
            o.append(_text(_MARGIN + dx, ry, cell, 9.5, _SANS))
    if issues:
        o.append(_text(_MARGIN, issues_top, "CHECKS", 9, weight="700"))
        for n, i in enumerate(issues):
            o.append(_text(_MARGIN, issues_top + 18 + 16 * n, f"{i['severity'].upper()}  {i['message']}", 9, _SANS))
    o.append("</svg>")
    return "\n".join(o)


def _load_harness(harness) -> dict:
    if isinstance(harness, str):
        import yaml

        harness = yaml.safe_load(harness)
    if not isinstance(harness, dict) or not harness.get("connectors"):
        raise ValueError("harness needs 'connectors', 'cables' and 'connections' (WireViz YAML structure)")
    return harness


def _strip_extensions(node):
    if isinstance(node, dict):
        return {k: _strip_extensions(v) for k, v in node.items() if k not in _EXTENSION_KEYS}
    return [_strip_extensions(v) for v in node] if isinstance(node, list) else node


def _run_wireviz(harness: dict, out: Path, name: str) -> dict:
    """Render with WireViz as a subprocess (GPL-3, never imported). Flags per wireviz --help (v0.4)."""
    import yaml

    src = out / f"{name}.wireviz.yml"
    src.write_text(yaml.safe_dump(_strip_extensions(harness), sort_keys=False, allow_unicode=True))
    try:
        proc = subprocess.run([which("wireviz"), str(src), "-f", "hpst", "-o", str(out), "-O", f"{name}_wireviz"],
                              capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "wireviz did not finish within 120 s"}
    files = sorted(str(p) for p in out.glob(f"{name}_wireviz.*"))
    if proc.returncode != 0 or not files:
        return {"ok": False, "error": f"wireviz failed (exit {proc.returncode})", "stderr": proc.stderr[-1200:]}
    return {"ok": True, "files": files}


def wiring_diagram(project: str, harness: dict | str, name: str = "harness", route: str = "auto") -> dict:
    """Check a wiring harness and draw it. Returns the wire list, check results and file paths.

    harness: WireViz-compatible YAML text or dict with connectors (pinlabels / pincount / pins),
    cables (wirecount, gauge "0.25 mm2" or "22 AWG", length in m unless length_unit, colors or
    color_code DIN/IEC) and connections. Extras: connector "splice: true" allows several wires on a
    pin; cable "current_a" (number or list per wire, amps) turns on the ampacity check and voltage
    drop. Checks: every wire lands on a real pin, no pin double-booked, wire gauge ampacity.
    route: "builtin" draws the SVG here; "wireviz" uses WireViz + Graphviz; "auto" prefers WireViz
    when installed. Always writes <name>.svg, <name>_wires.csv and <name>_connections.json under
    out/electronics/. Lengths in mm, currents in A.
    """
    if route not in ("auto", "builtin", "wireviz"):
        return {"ok": False, "error": f"Unknown route {route!r}. Options: auto, builtin, wireviz"}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        return {"ok": False, "error": "name: use letters, digits, '-' and '_' only"}
    have_wireviz = bool(which("wireviz") and which("dot"))
    if route == "wireviz" and not have_wireviz:
        missing = [n for n in ("wireviz", "dot") if not which(n)]
        return {"ok": False, "error": f"WireViz route needs {' and '.join(missing)} on PATH; "
                                      "use route='builtin' for the built-in renderer", "install": WIREVIZ_INSTALL}
    try:
        d = project_dir(project, create=True)
        spec = _load_harness(harness)
        model = _harness_model(spec)
    except Exception as e:  # noqa: BLE001 - YAML and structure errors go back to the caller
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = d / "out" / "electronics"
    out.mkdir(parents=True, exist_ok=True)
    rows = _wire_rows(model["wires"])
    title = str((spec.get("metadata") or {}).get("title") or name)

    svg = out / f"{name}.svg"
    svg.write_text(_harness_svg(model, title))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_WIRE_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    wires_csv = out / f"{name}_wires.csv"
    wires_csv.write_text(buf.getvalue())
    errors = [i for i in model["issues"] if i["severity"] == "error"]
    warnings_ = [i for i in model["issues"] if i["severity"] == "warning"]
    ampacity = load_json(DATA / "electronics" / "wire_ampacity.json", {}) or {}
    result = {
        "ok": True, "route": "builtin", "checks_passed": not errors,
        "error_count": len(errors), "warning_count": len(warnings_), "issues": model["issues"],
        "connectors": [{"name": c["name"], "type": c["type"], "pin_count": len(c["pins"]), "splice": c["splice"],
                        "unused_pins": c.get("unused_pins", [])} for c in model["connectors"].values()],
        "wire_count": len(rows), "wires": rows, "cut_totals": _cut_totals(rows),
        "total_length_mm": round(sum(r["length_mm"] or 0 for r in rows), 3),
        "ampacity_source": ampacity.get("source"),
        "files": {"svg": str(svg), "wires_csv": str(wires_csv), "connections_json": str(out / f"{name}_connections.json")},
    }
    if have_wireviz and route in ("auto", "wireviz"):
        wv = _run_wireviz(spec, out, name)
        if wv["ok"]:
            result["route"] = "wireviz"
            result["files"]["wireviz"] = wv["files"]
        elif route == "wireviz":
            return wv
        else:
            result["wireviz_error"] = wv["error"]
    elif route == "auto":
        result["note"] = "Drawn with the built-in renderer. For WireViz output: " + WIREVIZ_INSTALL
    save_json(out / f"{name}_connections.json", result)
    return result


# --------------------------------------------------------------------------------------
# Power budget
# --------------------------------------------------------------------------------------

def _suggest_awg(current_a: float, voltage_v: float, length_m: float, max_drop_pct: float) -> dict:
    """Thinnest wire that meets the conservative ampacity limit and, if a length is given, the drop limit."""
    table = sorted(_ampacity_table(), key=lambda r: -r["awg"])  # thinnest first
    by_amp = next((r for r in table if r["max_current_power_transmission_a"] >= current_a), None)
    by_free = next((r for r in table if r["max_current_chassis_a"] >= current_a), None)
    by_drop = None
    if length_m > 0 and current_a > 0:
        limit_v = voltage_v * max_drop_pct / 100
        by_drop = next((r for r in table if 2 * length_m * r["resistance_ohm_per_km"] / 1000 * current_a <= limit_v), None)
    picks = [r for r in (by_amp, by_drop) if r]
    complete = by_amp is not None and (length_m <= 0 or current_a <= 0 or by_drop is not None)
    pick = min(picks, key=lambda r: r["awg"]) if picks and complete else None
    out = {
        "suggested_awg": pick["awg"] if pick else None,
        "suggested_area_mm2": pick["area_mm2"] if pick else None,
        "by_ampacity_bundled_awg": by_amp["awg"] if by_amp else None,
        "by_ampacity_free_air_awg": by_free["awg"] if by_free else None,
        "by_voltage_drop_awg": by_drop["awg"] if by_drop else None,
    }
    if pick and length_m > 0:
        out["voltage_drop_v"] = round(2 * length_m * pick["resistance_ohm_per_km"] / 1000 * current_a, 4)
    if not pick:
        out["note"] = "No gauge in the table (AWG 4 to 32) meets this; split the load or use a busbar."
    return out


def power_budget(loads: list[dict], battery_capacity_mah: float = 0, battery_voltage_v: float = 0,
                 efficiency: float = 1.0, usable_fraction: float = 1.0,
                 wire_length_m: float = 0, max_drop_pct: float = 3.0) -> dict:
    """Total a list of loads per supply rail, estimate battery runtime and suggest a wire gauge.

    loads: [{name, voltage_v, current_a, duty (0..1, default 1), rail (optional name)}].
    Returns per rail: peak and average current (A) and power (W), plus a wire gauge sized for the
    peak current (conservative bundled-wire limit; and for max_drop_pct over a there-and-back run
    of wire_length_m if given). With battery_capacity_mah and battery_voltage_v, returns
    runtime_h = capacity x voltage x usable_fraction x efficiency / average power. efficiency is
    the converter efficiency between battery and loads (1.0 = none); it is your input, not measured.
    """
    if not loads:
        return {"ok": False, "error": "loads is empty"}
    if not (0 < efficiency <= 1 and 0 < usable_fraction <= 1):
        return {"ok": False, "error": "efficiency and usable_fraction must be in (0, 1]"}
    rails: dict[str, dict] = {}
    rows = []
    for i, ld in enumerate(loads):
        try:
            v, a = float(ld["voltage_v"]), float(ld["current_a"])
            duty = float(ld.get("duty", 1.0))
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": f"loads[{i}] needs numeric voltage_v and current_a (and optional duty)"}
        if not 0 <= duty <= 1 or v <= 0 or a < 0:
            return {"ok": False, "error": f"loads[{i}]: duty must be 0..1, voltage_v > 0, current_a >= 0"}
        key = str(ld.get("rail") or f"{v:g}V")
        r = rails.setdefault(key, {"rail": key, "voltage_v": v, "peak_current_a": 0.0, "avg_current_a": 0.0, "loads": 0})
        if abs(r["voltage_v"] - v) > 1e-9:
            return {"ok": False, "error": f"Rail '{key}' has loads at both {r['voltage_v']:g} V and {v:g} V"}
        r["peak_current_a"] += a
        r["avg_current_a"] += a * duty
        r["loads"] += 1
        rows.append({"name": ld.get("name", f"load{i + 1}"), "rail": key, "voltage_v": v, "current_a": a,
                     "duty": duty, "peak_power_w": round(v * a, 6), "avg_power_w": round(v * a * duty, 6)})
    for r in rails.values():
        r["peak_current_a"] = round(r["peak_current_a"], 6)
        r["avg_current_a"] = round(r["avg_current_a"], 6)
        r["peak_power_w"] = round(r["voltage_v"] * r["peak_current_a"], 6)
        r["avg_power_w"] = round(r["voltage_v"] * r["avg_current_a"], 6)
        r["wire"] = _suggest_awg(r["peak_current_a"], r["voltage_v"], wire_length_m, max_drop_pct)
    peak_w = round(sum(r["peak_power_w"] for r in rails.values()), 6)
    avg_w = round(sum(r["avg_power_w"] for r in rails.values()), 6)
    ampacity = load_json(DATA / "electronics" / "wire_ampacity.json", {}) or {}
    result = {"ok": True, "rails": list(rails.values()), "loads": rows,
              "total_peak_power_w": peak_w, "total_avg_power_w": avg_w,
              "wire_basis": "estimate", "wire_source": ampacity.get("source")}
    if battery_capacity_mah > 0:
        if battery_voltage_v <= 0:
            return {"ok": False, "error": "battery_voltage_v is needed with battery_capacity_mah"}
        energy_wh = battery_capacity_mah / 1000 * battery_voltage_v
        usable_wh = energy_wh * usable_fraction * efficiency
        result["battery"] = {
            "capacity_mah": battery_capacity_mah, "voltage_v": battery_voltage_v,
            "energy_wh": round(energy_wh, 4), "usable_energy_wh": round(usable_wh, 4),
            "efficiency": efficiency, "usable_fraction": usable_fraction,
            "avg_battery_current_a": round(avg_w / efficiency / battery_voltage_v, 6),
            "peak_battery_current_a": round(peak_w / efficiency / battery_voltage_v, 6),
            "runtime_h": round(usable_wh / avg_w, 4) if avg_w > 0 else None,
            "runtime_at_peak_h": round(usable_wh / peak_w, 4) if peak_w > 0 else None,
        }
    return result


def register(mcp) -> None:
    for fn in (circuit_write, circuit_read, circuit_build, circuit_simulate, kicad_check, kicad_export,
               wiring_diagram, power_budget):
        mcp.tool()(fn)


if __name__ == "__main__":
    import traceback

    try:
        _result = _runner(Path(sys.argv[1]).resolve())
    except Exception as _e:  # noqa: BLE001 - reported to the caller as JSON
        _result = {"ok": False, "error": f"{type(_e).__name__}: {_e}", "traceback": traceback.format_exc()[-2500:]}
    print(json.dumps(_result))
