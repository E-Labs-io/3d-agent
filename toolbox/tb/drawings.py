"""2D drawings projected from the solid model, so they can never drift from it.

Output is SVG (for reading and printing) and DXF (for CAD and laser/CNC), in millimetres.
"""
from __future__ import annotations

import datetime as dt
from html import escape
from pathlib import Path

from .common import load_json, project_dir

SHEETS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420)}
SCALES = [10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05]
# name: (camera position unit vector, up vector, model axes shown as (horizontal, vertical))
VIEWS = {
    "FRONT": ((0, -1, 0), (0, 0, 1), ("X", "Z")),
    "PLAN": ((0, 0, 1), (0, 1, 0), ("X", "Y")),
    "SIDE (from left)": ((-1, 0, 0), (0, 0, 1), ("Y", "Z")),
    "ISOMETRIC": ((1, -1, 0.8), (0, 0, 1), None),
}


def _polyline(edge) -> list[tuple[float, float]]:
    from build123d import GeomType

    n = 2 if edge.geom_type == GeomType.LINE else 25
    return [(p.X, p.Y) for p in (edge.position_at(i / (n - 1)) for i in range(n))]


def _project(shape, view: str):
    cam, up, _ = VIEWS[view]
    bb = shape.bounding_box()
    c = bb.center()
    reach = max(bb.size.X, bb.size.Y, bb.size.Z) * 4 + 100
    origin = (c.X + cam[0] * reach, c.Y + cam[1] * reach, c.Z + cam[2] * reach)
    visible, hidden = shape.project_to_viewport(origin, viewport_up=up, look_at=(c.X, c.Y, c.Z))
    vis = [_polyline(e) for e in visible]
    hid = [_polyline(e) for e in hidden]
    pts = [p for line in vis + hid for p in line]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return vis, hid, (min(xs), min(ys), max(xs), max(ys))


def _path(lines, ox, oy, s) -> str:
    return " ".join("M" + " L".join(f"{ox + x * s:.2f},{oy - y * s:.2f}" for x, y in line) for line in lines)


def _dim_h(x0, x1, y, text) -> str:
    return (f'<path class="dim" d="M{x0:.2f},{y - 6:.2f} V{y + 2:.2f} M{x1:.2f},{y - 6:.2f} V{y + 2:.2f} '
            f'M{x0:.2f},{y:.2f} H{x1:.2f}"/>'
            f'<path class="arrow" d="M{x0:.2f},{y:.2f} l3,-1 v2 z M{x1:.2f},{y:.2f} l-3,-1 v2 z"/>'
            f'<text class="dimtext" x="{(x0 + x1) / 2:.2f}" y="{y - 1.5:.2f}" text-anchor="middle">{text}</text>')


def _dim_v(y0, y1, x, text) -> str:
    ym = (y0 + y1) / 2
    return (f'<path class="dim" d="M{x - 2:.2f},{y0:.2f} H{x + 6:.2f} M{x - 2:.2f},{y1:.2f} H{x + 6:.2f} '
            f'M{x:.2f},{y0:.2f} V{y1:.2f}"/>'
            f'<path class="arrow" d="M{x:.2f},{y0:.2f} l-1,3 h2 z M{x:.2f},{y1:.2f} l-1,-3 h2 z"/>'
            f'<text class="dimtext" x="{x - 1.5:.2f}" y="{ym:.2f}" text-anchor="middle" '
            f'transform="rotate(-90 {x - 1.5:.2f} {ym:.2f})">{text}</text>')


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _sheet(shape, title: str, subtitle: str, sheet: str, drawing_no: str, notes: list[str]) -> tuple[str, dict]:
    W, H = SHEETS[sheet]
    margin, block_h, gap = 10, 28, 26
    views = {name: _project(shape, name) for name in VIEWS}
    size = {n: (v[2][2] - v[2][0], v[2][3] - v[2][1]) for n, v in views.items()}
    need_w = size["FRONT"][0] + size["SIDE (from left)"][0] + size["ISOMETRIC"][0]
    need_h = size["FRONT"][1] + size["PLAN"][1]
    avail_w, avail_h = W - 2 * margin - 3 * gap - 20, H - 2 * margin - block_h - 2 * gap - 16
    scale = next((s for s in SCALES if need_w * s <= avail_w and need_h * s <= avail_h), SCALES[-1])
    label = f"{int(scale)}:1" if scale >= 1 else f"1:{int(round(1 / scale))}"

    fw, fh = size["FRONT"][0] * scale, size["FRONT"][1] * scale
    pw, ph = size["PLAN"][0] * scale, size["PLAN"][1] * scale
    sw, sh = size["SIDE (from left)"][0] * scale, size["SIDE (from left)"][1] * scale
    x_front, y_front = margin + 24, margin + 22
    # First-angle layout: plan below the front view, view-from-left to its right.
    place = {
        "FRONT": (x_front, y_front, fw, fh),
        "PLAN": (x_front, y_front + fh + gap, pw, ph),
        "SIDE (from left)": (x_front + fw + gap + 8, y_front, sw, sh),
        "ISOMETRIC": (x_front + fw + sw + 2 * gap + 12, y_front, size["ISOMETRIC"][0] * scale, size["ISOMETRIC"][1] * scale),
    }
    bb = shape.bounding_box()
    dims = {"X": bb.size.X, "Y": bb.size.Y, "Z": bb.size.Z}
    body = []
    for name, (x, y, w, h) in place.items():
        vis, hid, (x0, y0, x1, y1) = views[name]
        ox, oy = x - x0 * scale, y + y1 * scale
        body.append(f'<path class="hidden" d="{_path(hid, ox, oy, scale)}"/>')
        body.append(f'<path class="visible" d="{_path(vis, ox, oy, scale)}"/>')
        body.append(f'<text class="label" x="{x:.2f}" y="{y - 5:.2f}">{escape(name)}</text>')
        axes = VIEWS[name][2]
        if axes:
            body.append(_dim_h(x, x + w, y + h + 9, _fmt(dims[axes[0]])))
            body.append(_dim_v(y, y + h, x - 9, _fmt(dims[axes[1]])))
    by = H - margin - block_h
    bx = W - margin - 150
    today = dt.date.today().isoformat()
    block = (f'<rect class="frame" x="{bx}" y="{by}" width="150" height="{block_h}"/>'
             f'<path class="frame" d="M{bx},{by + 12} H{bx + 150} M{bx + 75},{by + 12} V{by + block_h} M{bx},{by + 20} H{bx + 150}"/>'
             f'<text class="title" x="{bx + 4}" y="{by + 8}">{escape(title)}</text>'
             f'<text class="cell" x="{bx + 4}" y="{by + 17.5}">{escape(subtitle)}</text>'
             f'<text class="cell" x="{bx + 79}" y="{by + 17.5}">DRG {escape(drawing_no)}</text>'
             f'<text class="cell" x="{bx + 4}" y="{by + 25.5}">SCALE {label} · {sheet} · mm</text>'
             f'<text class="cell" x="{bx + 79}" y="{by + 25.5}">{today} · FIRST ANGLE</text>')
    note_svg = "".join(f'<text class="cell" x="{margin + 4}" y="{by + 6 + i * 4.5:.1f}">{escape(n)}</text>'
                       for i, n in enumerate(["NOTES"] + notes))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">'
           '<style>.visible{fill:none;stroke:#111;stroke-width:.35;stroke-linecap:round;stroke-linejoin:round}'
           '.hidden{fill:none;stroke:#777;stroke-width:.18;stroke-dasharray:1.6 .9}'
           '.dim,.frame{fill:none;stroke:#333;stroke-width:.18}.arrow{fill:#333;stroke:none}'
           'text{font-family:ui-monospace,Menlo,monospace;fill:#111}.dimtext{font-size:3.2px}'
           '.label{font-size:3.4px;font-weight:600}.title{font-size:5px;font-weight:700}.cell{font-size:3px}</style>'
           f'<rect width="{W}" height="{H}" fill="#fff"/>'
           f'<rect class="frame" x="{margin}" y="{margin}" width="{W - 2 * margin}" height="{H - 2 * margin}"/>'
           + "".join(body) + block + note_svg + "</svg>")
    return svg, {"scale": label, "sheet": sheet, "overall_mm": [round(dims[a], 2) for a in "XYZ"]}


def _load_shapes(project: str) -> tuple[Path, dict, dict]:
    """Rebuild the model in-process to get exact solids (drawings need B-rep, not meshes)."""
    import os
    import runpy
    import sys

    d = project_dir(project)
    build = load_json(d / "out" / "build.json")
    if not build:
        raise FileNotFoundError(f"Project '{project}' has not been built. Run cad_build first.")
    toolbox = str(Path(__file__).resolve().parent.parent)
    if toolbox not in sys.path:
        sys.path.insert(0, toolbox)
    cwd = os.getcwd()
    os.chdir(d)
    try:
        specs = runpy.run_path(str(d / "model.py"), run_name="__model__")["PARTS"]
    finally:
        os.chdir(cwd)
    return d, build, specs


def drawing_make(project: str, part: str = "", sheet: str = "A3", dxf: bool = True) -> dict:
    """Make dimensioned orthographic drawings (front, plan, side, isometric) for each part and the assembly.

    Views are projected from the solid with hidden lines dashed, first-angle layout, overall
    dimensions in mm. Writes SVG (and DXF of each part's three views) to out/drawings/.
    """
    if sheet not in SHEETS:
        return {"ok": False, "error": f"sheet must be one of {sorted(SHEETS)}"}
    try:
        d, build, specs = _load_shapes(project)
    except Exception as e:  # noqa: BLE001 - reported to the agent
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    from build123d import Compound, ExportDXF, LineType

    title = (load_json(d / "project.json", {}) or {}).get("title", project)
    out = d / "out" / "drawings"
    out.mkdir(parents=True, exist_ok=True)
    targets = {n: s for n, s in specs.items() if not s.reference and (not part or n == part)}
    if part and not targets:
        return {"ok": False, "error": f"No manufactured part '{part}'. Parts: {sorted(n for n, s in specs.items() if not s.reference)}"}
    made = []
    for i, (name, spec) in enumerate(targets.items(), start=1):
        info = build["parts"].get(name, {})
        notes = [f"MATERIAL: {spec.material.upper()}   PROCESS: {spec.process.upper()}   QTY: {spec.qty}",
                 f"VOLUME: {info.get('volume_mm3', 0) / 1000:.1f} cm3",
                 "PRINT FLIPPED (pockets up)" if spec.print_flip else "PRINT AS DRAWN",
                 "DIMENSIONS ARE OVERALL. TAKE FEATURE SIZES FROM THE STEP FILE."] + ([spec.note] if spec.note else [])
        svg, meta = _sheet(spec.shape, title, name, sheet, f"{i:02d}", notes)
        (out / f"{i:02d}-{name}.svg").write_text(svg)
        files = {"svg": f"out/drawings/{i:02d}-{name}.svg"}
        if dxf:
            exp = ExportDXF(line_type=LineType.CONTINUOUS)
            exp.add_layer("visible")
            exp.add_layer("hidden", line_type=LineType.ISO_DASH)
            x_off = 0.0
            for view in ("FRONT", "PLAN", "SIDE (from left)"):
                cam, up, _ = VIEWS[view]
                bb = spec.shape.bounding_box()
                c = bb.center()
                reach = max(bb.size.X, bb.size.Y, bb.size.Z) * 4 + 100
                vis, hid = spec.shape.project_to_viewport(
                    (c.X + cam[0] * reach, c.Y + cam[1] * reach, c.Z + cam[2] * reach), viewport_up=up, look_at=(c.X, c.Y, c.Z))
                from build123d import Pos
                shift = Pos(x_off, 0, 0)
                exp.add_shape([shift * e for e in vis], layer="visible")
                if hid:
                    exp.add_shape([shift * e for e in hid], layer="hidden")
                x_off += max(bb.size.X, bb.size.Y) + 40
            exp.write(str(out / f"{i:02d}-{name}.dxf"))
            files["dxf"] = f"out/drawings/{i:02d}-{name}.dxf"
        made.append({"part": name, **meta, "files": files})
    if not part and len(targets) > 1:
        asm = Compound(children=[s.shape for s in targets.values()])
        notes = [f"{n}: {s.material.upper()}, QTY {s.qty}" for n, s in targets.items()]
        svg, meta = _sheet(asm, title, "GENERAL ASSEMBLY", sheet, "00", notes)
        (out / "00-assembly.svg").write_text(svg)
        made.insert(0, {"part": "assembly", **meta, "files": {"svg": "out/drawings/00-assembly.svg"}})
    return {"ok": True, "project_dir": str(d), "drawings": made}


def register(mcp) -> None:
    mcp.tool()(drawing_make)
