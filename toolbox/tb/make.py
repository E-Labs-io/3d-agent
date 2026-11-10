"""Print preparation: time/filament estimates, orientation, bed layout, slicing.

Slicers are GPL/AGPL programs and are only ever run as subprocesses.
CLI flags come from the published references, nothing is guessed:
  PrusaSlicer  https://manpages.debian.org/trixie/prusa-slicer/prusa-slicer.1
  OrcaSlicer   https://github.com/OrcaSlicer/OrcaSlicer/wiki/Command-Line-Interface
"""
from __future__ import annotations

import math
import re
import subprocess
import zipfile
from pathlib import Path

import numpy as np

from . import common
from .common import DATA, inside, load_json, which

INSTALL = {
    "prusaslicer": "https://www.prusa3d.com/page/prusaslicer_424/ (or: brew install --cask prusaslicer)",
    "orcaslicer": "https://github.com/OrcaSlicer/OrcaSlicer/releases (or: brew install --cask orcaslicer)",
}
_BIN = {"prusaslicer": ("prusa-slicer", "PrusaSlicer"), "orcaslicer": ("orca-slicer", "OrcaSlicer")}
# PrusaSlicer options listed in its man page; the only profile keys passed on the command line.
_PRUSA_FLAGS = {"layer_height_mm": "--layer-height", "nozzle_diameter_mm": "--nozzle-diameter",
                "filament_diameter_mm": "--filament-diameter", "filament_density_g_cm3": "--filament-density"}
_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


# ---------------------------------------------------------------- helpers

def _defaults() -> dict:
    raw = load_json(DATA / "make" / "estimate_defaults.json", {})
    return {k: v["value"] for k, v in raw.get("profile", {}).items()}


def _build(project: str) -> tuple[Path, dict]:
    d = common.project_dir(project)
    build = load_json(d / "out" / "build.json")
    if not build:
        raise FileNotFoundError(f"Project '{project}' has not been built: run cad_build('{project}') first")
    return d, build


def _printable(build: dict, part: str = "") -> dict:
    parts = {n: p for n, p in build["parts"].items() if not p.get("reference") and p.get("files", {}).get("stl")}
    if part:
        if part not in parts:
            raise KeyError(f"No printable part '{part}'. Printable parts: {sorted(parts)}")
        return {part: parts[part]}
    return parts


def _mesh(d: Path, part: str):
    import trimesh

    f = inside(d, f"out/{part}.stl")
    if not f.exists():
        raise FileNotFoundError(f"Missing {f.name}: run cad_build first")
    return trimesh.load_mesh(f)


def _density(material: str, density_g_cm3: float) -> tuple[float | None, str]:
    """Density in g/cm3 and where it came from. Never invented: None when nothing is known."""
    if density_g_cm3 and density_g_cm3 > 0:
        return float(density_g_cm3), "density_g_cm3 argument"
    if material:
        try:
            from . import materials  # optional sibling module

            rec = materials.get_material(material)
        except Exception:  # noqa: BLE001 - module absent or material unknown
            rec = None
        if isinstance(rec, dict):
            rec = rec.get("material", rec)
            for key, scale in (("density_g_cm3", 1.0), ("density_kg_m3", 1e-3), ("density", None)):
                v = rec.get(key)
                if isinstance(v, dict):
                    v = v.get("value")
                if isinstance(v, (int, float)) and v > 0:
                    if scale is None:  # unit not in the key: values above 50 can only be kg/m3
                        scale = 1e-3 if v > 50 else 1.0
                    return float(v) * scale, f"tb.materials.get_material('{material}')"
    return None, "unknown"


def _orientation_metrics(mesh, down, overhang_angle_deg: float, tol_mm: float = 0.05) -> dict:
    """Bed contact, overhang and height for the mesh printed with unit vector `down` on the bed."""
    down = np.asarray(down, dtype=float)
    heights = -(mesh.vertices @ down)
    zmin = float(heights.min())
    nz = -(mesh.face_normals @ down)
    cz = -(mesh.triangles_center @ down) - zmin
    area = mesh.area_faces
    facing_down = nz < -math.sin(math.radians(overhang_angle_deg))
    on_bed = (nz < -0.999) & (cz < tol_mm)
    over = facing_down & ~on_bed
    return {
        "height_mm": float(heights.max() - zmin),
        "contact_area_mm2": float(area[on_bed].sum()),
        "support_area_mm2": float(area[over].sum()),
        # column from each overhanging face straight down to the bed: an upper bound,
        # because supports that would land on the part itself are counted to the bed.
        "support_volume_mm3": float((area[over] * -nz[over] * cz[over]).sum()),
    }


def _fmt_time(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}h {m % 60:02d}m"


# ---------------------------------------------------------------- estimate route

def _estimate_part(mesh, prof: dict) -> dict:
    wall = prof["perimeters"] * prof["line_width_mm"]
    volume = float(abs(mesh.volume))
    shell = min(volume, float(mesh.area) * wall)
    infill = (volume - shell) * prof["infill_fraction"]
    m = _orientation_metrics(mesh, (0, 0, -1), prof["overhang_angle_deg"])
    support = m["support_volume_mm3"] * prof["support_density"] if prof["support"] in (True, "auto") else 0.0
    extruded = shell + infill + support
    return {
        "solid_volume_mm3": round(volume, 1), "shell_volume_mm3": round(shell, 1),
        "infill_volume_mm3": round(infill, 1), "support_volume_mm3": round(support, 1),
        "support_area_mm2": round(m["support_area_mm2"], 1),
        "extruded_volume_mm3": round(extruded, 1),
        "layers": int(math.ceil(m["height_mm"] / prof["layer_height_mm"])),
        "print_time_s": round(extruded / prof["flow_mm3_s"] * prof["time_overhead_factor"]),
    }


def _totals(volume_mm3: float, time_s: float, filament_d_mm: float, density: float | None,
            price_per_kg: float, grams: float | None = None, length_mm: float | None = None) -> dict:
    if length_mm is None:
        length_mm = volume_mm3 / (math.pi * (filament_d_mm / 2) ** 2)
    if grams is None and density:
        grams = volume_mm3 / 1000 * density
    out = {
        "filament_volume_cm3": round(volume_mm3 / 1000, 2),
        "filament_length_m": round(length_mm / 1000, 2),
        "filament_g": round(grams, 1) if grams is not None else None,
        "print_time_s": int(round(time_s)), "print_time_h": round(time_s / 3600, 2),
        "print_time_text": _fmt_time(time_s),
        "material_cost": round(grams / 1000 * price_per_kg, 2) if grams is not None and price_per_kg > 0 else None,
    }
    return out


def _estimate(d: Path, parts: dict, profile: dict, material: str, density_g_cm3: float, price_per_kg: float) -> dict:
    prof = {**_defaults(), **profile}
    rows, vol, time_s, grams_total, sources = {}, 0.0, 0.0, 0.0, set()
    for name, info in parts.items():
        row = _estimate_part(_mesh(d, name), prof)
        qty = int(info.get("qty", 1) or 1)
        dens, src = _density(material or info.get("material", ""), density_g_cm3)
        sources.add(src)
        row.update(qty=qty, material=material or info.get("material", ""), density_g_cm3=dens,
                   filament_g=round(row["extruded_volume_mm3"] / 1000 * dens, 1) if dens else None)
        rows[name] = row
        vol += row["extruded_volume_mm3"] * qty
        time_s += row["print_time_s"] * qty
        grams_total = None if (dens is None or grams_total is None) else grams_total + row["extruded_volume_mm3"] / 1000 * dens * qty
    err = load_json(DATA / "make" / "estimate_defaults.json", {}).get("likely_error", {})
    out = {"ok": True, "route": "estimate", "basis": "estimate", "parts": rows,
           **_totals(vol, time_s, prof["filament_diameter_mm"], None, price_per_kg, grams=grams_total),
           "density_source": sorted(sources), "price_per_kg": price_per_kg or None,
           "assumptions": prof,
           "method": "shell = surface area x (perimeters x line width), capped at solid volume; "
                     "infill = remaining volume x infill fraction; support = overhanging area projected to the bed x support density "
                     "(upper bound); time = extruded volume / average volumetric flow x overhead factor",
           "likely_error_pct": {"filament": err.get("filament_pct"), "time": err.get("time_pct")},
           "note": "ESTIMATE from mesh geometry, not a slice. Totals include each part's qty. "
                   "Use route 'prusaslicer' or 'orcaslicer' for real numbers."}
    if grams_total is None:
        out["note"] += " Mass and cost are omitted because no density is known: pass density_g_cm3 or a material known to the materials tools."
    return out


# ---------------------------------------------------------------- slicer routes

def _duration_s(text: str) -> int | None:
    """'1d 2h 3m 4s' -> seconds."""
    found = re.findall(r"(\d+)\s*([dhms])", text)
    if not found:
        return None
    return sum(int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u] for n, u in found)


def parse_gcode_stats(text: str) -> dict:
    """Print time and filament use from the comment lines PrusaSlicer and OrcaSlicer write into G-code.

    Multi-extruder values (comma separated) are summed. Missing fields are None.
    """
    def nums(pattern: str) -> float | None:
        m = re.search(pattern, text, re.M | re.I)
        if not m:
            return None
        vals = [float(v) for v in re.findall(r"[-+]?\d*\.?\d+", m.group(1))]
        return sum(vals) if vals else None

    t = re.search(r"^;\s*estimated printing time \(normal mode\)\s*=\s*(.+)$", text, re.M | re.I) \
        or re.search(r"^;.*total estimated time:\s*(.+)$", text, re.M | re.I)
    return {
        "print_time_s": _duration_s(t.group(1)) if t else None,
        "filament_length_mm": nums(r"^;\s*(?:total )?filament used \[mm\]\s*=\s*(.+)$") or nums(r"^;\s*total filament length \[mm\]\s*:\s*(.+)$"),
        "filament_volume_cm3": nums(r"^;\s*(?:total )?filament used \[cm3\]\s*=\s*(.+)$"),
        "filament_g": nums(r"^;\s*total filament used \[g\]\s*=\s*(.+)$") or nums(r"^;\s*filament used \[g\]\s*=\s*(.+)$")
                      or nums(r"^;\s*total filament weight \[g\]\s*:\s*(.+)$"),
    }


def _resolve_route(route: str, profile_path: str) -> tuple[str | None, dict | None]:
    """Pick a slicer route. Returns (route, error dict)."""
    if route == "auto":
        if which(*_BIN["prusaslicer"]):
            return "prusaslicer", None
        if which(*_BIN["orcaslicer"]) and profile_path:
            return "orcaslicer", None
        return None, {"ok": False, "error": "No slicer installed (prusa-slicer or orca-slicer). Install one, or use print_estimate route 'estimate'.",
                      "install": INSTALL["prusaslicer"]}
    if route not in _BIN:
        return None, {"ok": False, "error": f"Unknown route '{route}'. Use auto, prusaslicer or orcaslicer."}
    if not which(*_BIN[route]):
        return None, {"ok": False, "error": f"{route} is not installed", "install": INSTALL[route]}
    return route, None


def _slicer_cmd(route: str, exe: str, src: Path, out: Path, profile_path: str, filament_profile: str, profile: dict) -> list[str]:
    if route == "prusaslicer":
        cmd = [exe, "--export-gcode"]
        for p in filter(None, profile_path.split(";")):
            cmd += ["--load", p]
        for key, flag in _PRUSA_FLAGS.items():
            if key in profile:
                cmd += [flag, str(profile[key])]
        return cmd + ["--output", str(out), str(src)]
    # OrcaSlicer: machine and process JSON in --load-settings, filament JSON in --load-filaments.
    cmd = [exe, "--load-settings", profile_path]
    if filament_profile:
        cmd += ["--load-filaments", filament_profile]
    return cmd + ["--arrange", "1", "--slice", "0", "--outputdir", str(out.parent),
                  "--export-3mf", out.with_suffix(".gcode.3mf").name, str(src)]


def _run_slicer(d: Path, part: str, route: str, profile_path: str, filament_profile: str, profile: dict) -> dict:
    exe = which(*_BIN[route])
    src = next((f for f in (inside(d, f"out/{part}.stl"), inside(d, f"out/{part}.3mf")) if f.exists()), None)
    if src is None:
        return {"ok": False, "error": f"No out/{part}.stl or .3mf: run cad_build first"}
    for p in filter(None, (profile_path + ";" + filament_profile).split(";")):
        if not Path(p).expanduser().is_file():
            return {"ok": False, "error": f"Profile file not found: {p}"}
    if route == "orcaslicer" and not profile_path:
        return {"ok": False, "error": "OrcaSlicer needs profile='<machine.json>;<process.json>' and filament_profile='<filament.json>' "
                                      "(export them from the app: File > Export > Export Preset Bundle)"}
    out = inside(d, f"out/make/{part}.gcode")
    out.parent.mkdir(parents=True, exist_ok=True)
    before = {f: f.stat().st_mtime for f in out.parent.glob("*.gcode")}
    cmd = _slicer_cmd(route, exe, src, out, profile_path, filament_profile, profile)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{route} timed out after 900 s"}
    if route == "orcaslicer":
        _collect_orca_gcode(out, before)
    if proc.returncode != 0 or not out.exists():
        return {"ok": False, "error": f"{route} failed (exit {proc.returncode})", "stderr": (proc.stderr or proc.stdout)[-1500:],
                "command": " ".join(cmd)}
    stats = parse_gcode_stats(out.read_text(errors="replace"))
    return {"ok": True, "route": route, "gcode": f"out/make/{out.name}", "path": str(out), "source": src.name,
            "size_bytes": out.stat().st_size, **stats}


def _collect_orca_gcode(out: Path, before: dict) -> None:
    """OrcaSlicer names its own output: take the new plate G-code, loose or inside the exported 3MF."""
    fresh = [f for f in out.parent.glob("*.gcode") if f != out and before.get(f) != f.stat().st_mtime]
    if fresh:
        fresh[0].replace(out)
        return
    packed = out.with_suffix(".gcode.3mf")
    if packed.exists():
        with zipfile.ZipFile(packed) as z:
            names = [n for n in z.namelist() if n.endswith(".gcode")]
            if names:
                out.write_bytes(z.read(names[0]))


# ---------------------------------------------------------------- tools

def print_estimate(project: str, part: str = "", route: str = "auto", profile: dict = {},
                   material: str = "", density_g_cm3: float = 0.0, price_per_kg: float = 0.0,
                   profile_path: str = "", filament_profile: str = "") -> dict:
    """Filament (g, m), print time (s, h) and material cost for one part, or all printable parts if part is "".

    route: "prusaslicer" / "orcaslicer" slice for real and read the G-code; "estimate" computes from the
    mesh and is labelled basis "estimate" with its assumptions and likely error; "auto" uses PrusaSlicer if
    installed, else OrcaSlicer if installed and profile_path is given, else the estimate.
    profile (estimate route) overrides: layer_height_mm, line_width_mm, perimeters, infill_fraction,
    support (true/false/"auto"), support_density, overhang_angle_deg, flow_mm3_s, time_overhead_factor,
    filament_diameter_mm. profile_path / filament_profile are slicer config files (see the slice tool).
    Density comes from density_g_cm3, else the materials tools for `material` (default: the part's material).
    material_cost is in the currency of price_per_kg.
    """
    try:
        d, build = _build(project)
        parts = _printable(build, part)
        if not parts:
            return {"ok": False, "error": "No printable parts in this project (all are reference parts)"}
        if route == "estimate":
            return _estimate(d, parts, profile, material, density_g_cm3, price_per_kg)
        chosen, err = _resolve_route(route, profile_path)
        if err:
            if route != "auto":
                return err
            out = _estimate(d, parts, profile, material, density_g_cm3, price_per_kg)
            out["note"] += " No slicer is installed, so 'auto' fell back to the estimate."
            out["install"] = INSTALL["prusaslicer"]
            return out
        rows, vol, time_s, grams, length = {}, 0.0, 0.0, 0.0, 0.0
        fil_d = float(profile.get("filament_diameter_mm", _defaults()["filament_diameter_mm"]))
        for name, info in parts.items():
            r = _run_slicer(d, name, chosen, profile_path, filament_profile, profile)
            if not r["ok"]:
                return r
            if r["print_time_s"] is None or r["filament_length_mm"] is None:
                return {"ok": False, "error": f"Sliced {name} but could not read time/filament from the G-code comments", "gcode": r["gcode"]}
            qty = int(info.get("qty", 1) or 1)
            dens, src = _density(material or info.get("material", ""), density_g_cm3)
            v = r["filament_volume_cm3"] * 1000 if r["filament_volume_cm3"] else r["filament_length_mm"] * math.pi * (fil_d / 2) ** 2
            g = r["filament_g"] or (v / 1000 * dens if dens else None)
            rows[name] = {**{k: r[k] for k in ("gcode", "print_time_s", "filament_length_mm")}, "filament_g": g, "qty": qty,
                          "mass_source": "slicer" if r["filament_g"] else src}
            vol, time_s, length = vol + v * qty, time_s + r["print_time_s"] * qty, length + r["filament_length_mm"] * qty
            grams = None if (g is None or grams is None) else grams + g * qty
        return {"ok": True, "route": chosen, "basis": "sliced", "parts": rows,
                **_totals(vol, time_s, fil_d, None, price_per_kg, grams=grams, length_mm=length),
                "price_per_kg": price_per_kg or None,
                "note": "From slicer G-code comments. Each part was sliced alone; totals multiply by qty."}
    except (ValueError, KeyError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e).strip("'\"")}


def _flat_faces(mesh, min_area: float, limit: int = 10) -> list[tuple[np.ndarray, float]]:
    """Planar faces on the convex hull that are big enough to sit on: (outward normal, area)."""
    out = []
    order = np.argsort(mesh.facets_area)[::-1]
    for i in order[:60]:
        area = float(mesh.facets_area[i])
        if area < min_area:
            break
        n = mesh.facets_normal[i]
        level = float(mesh.triangles_center[mesh.facets[i][0]] @ n)
        if float((mesh.vertices @ n).max()) <= level + 0.05:  # nothing sticks out past this face
            out.append((n, area))
        if len(out) >= limit:
            break
    return out


def print_orient(project: str, part: str, load_axis: str = "", overhang_angle_deg: float = 45.0, top: int = 8) -> dict:
    """Rank print orientations for a part: best first, with support area, bed contact, height and reasons.

    Candidates are the 6 axis-aligned orientations plus any flat outer face large enough to sit on.
    `down` is the unit vector, in the frame of out/<part>.stl, that would point at the bed. Layers stack
    along it, so the part is weakest in tension along `weak_axis`. Pass load_axis ("x", "y" or "z", the
    direction of the main service load) for functional parts: orientations that put layers across that
    load are penalised. Areas mm2, height mm. Lower score is better; weights are returned.
    """
    try:
        d, build = _build(project)
        _printable(build, part)
        mesh = _mesh(d, part)
        if load_axis and load_axis.lower() not in _AXES:
            return {"ok": False, "error": "load_axis must be 'x', 'y', 'z' or empty"}
        cands: list[tuple[str, np.ndarray]] = []
        for name, v in _AXES.items():
            cands += [(f"-{name} down", -np.array(v)), (f"+{name} down", np.array(v))]
        for n, area in _flat_faces(mesh, max(25.0, 0.02 * float(mesh.area))):
            if all(float(n @ c[1]) < 0.999 for c in cands):
                cands.append((f"flat face {area:.0f} mm2 down", np.asarray(n)))
        rows = []
        for label, down in cands:
            m = _orientation_metrics(mesh, down, overhang_angle_deg)
            near = max(_AXES, key=lambda a: abs(float(down @ np.array(_AXES[a]))))
            rows.append({"orientation": label, "down": [round(float(x), 4) for x in down],
                         **{k: round(v, 1) for k, v in m.items()},
                         "weak_axis": near if abs(float(down @ np.array(_AXES[near]))) > 0.9 else "oblique"})
        total = float(mesh.area)
        max_contact = max(r["contact_area_mm2"] for r in rows) or 1.0
        max_h = max(r["height_mm"] for r in rows) or 1.0
        weights = {"support": 0.5, "contact": 0.25, "height": 0.15, "weak_axis": 0.5}
        load = np.array(_AXES[load_axis.lower()]) if load_axis else None
        for r in rows:
            across = load is not None and abs(float(np.array(r["down"]) @ load)) > 0.7
            r["load_across_layers"] = bool(across) if load is not None else None
            r["score"] = round(weights["support"] * r["support_area_mm2"] / total
                               + weights["contact"] * (1 - r["contact_area_mm2"] / max_contact)
                               + weights["height"] * r["height_mm"] / max_h
                               + (weights["weak_axis"] if across else 0.0), 4)
            why = [f"support under {r['support_area_mm2']:.0f} mm2 ({100 * r['support_area_mm2'] / total:.0f}% of surface)",
                   f"bed contact {r['contact_area_mm2']:.0f} mm2", f"height {r['height_mm']:.1f} mm",
                   f"layers stack along {r['weak_axis']}: weakest in tension on that axis"]
            if across:
                why.append(f"load axis {load_axis} pulls layers apart: avoid for a functional part")
            if r["contact_area_mm2"] < 1:
                why.append("no flat face on the bed: needs a raft or supports to stand")
            r["reasons"] = why
        rows.sort(key=lambda r: r["score"])
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        flipped = bool(build["parts"][part].get("print_flip"))
        return {"ok": True, "part": part, "frame": f"out/{part}.stl" + (" (already flipped 180 deg about X by print_flip)" if flipped else ""),
                "current": "-z down", "overhang_angle_deg": overhang_angle_deg, "weights": weights,
                "candidates": len(rows), "ranked": rows[:max(1, top)],
                "note": "Geometry only: support volume is an upper bound and warping, surface finish and bridging are not scored."}
    except (ValueError, KeyError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e).strip("'\"")}


def _pack(items: list[dict], bed_x: float, bed_y: float, gap: float) -> list[list[dict]]:
    """First-fit shelf packing, tallest footprint first. Each item may be turned 90 degrees."""
    plates: list[dict] = []
    for it in sorted(items, key=lambda i: -max(i["w"], i["h"])):
        # lie each footprint long side along X where the bed allows, else long side along Y
        w, h = max(it["w"], it["h"]), min(it["w"], it["h"])
        turned = it["w"] < it["h"]
        if w > bed_x:
            w, h, turned = h, w, not turned
        placed = False
        for plate in plates + [None]:
            if plate is None:
                plate = {"shelves": [], "items": []}
                plates.append(plate)
            for shelf in plate["shelves"]:
                if shelf["x"] + w <= bed_x + 1e-9 and h <= shelf["h"] + 1e-9:
                    pos = (shelf["x"], shelf["y"])
                    shelf["x"] += w + gap
                    placed = True
                    break
            else:
                y = sum(s["h"] + gap for s in plate["shelves"])
                if y + h <= bed_y + 1e-9:
                    plate["shelves"].append({"x": w + gap, "y": y, "h": h})
                    pos, placed = (0.0, y), True
            if placed:
                plate["items"].append({"part": it["part"], "copy": it["copy"], "x_mm": round(pos[0], 2), "y_mm": round(pos[1], 2),
                                       "size_mm": [round(w, 2), round(h, 2)], "rotated_90": turned})
                break
    return [p["items"] for p in plates]


def print_bed_layout(project: str, bed_mm: list[float] = [220.0, 220.0], gap_mm: float = 5.0) -> dict:
    """Check whether all printable parts fit on one build plate and lay them out (mm).

    bed_mm is [x, y] or [x, y, z]. Footprints are the XY bounding boxes of out/<part>.stl, each part's
    qty is honoured, parts may be turned 90 degrees, and gap_mm is kept between parts. Positions are the
    footprint's lower-left corner. Returns plates, parts that sit alone on a plate and parts too big for the bed.
    """
    try:
        if len(bed_mm) < 2 or min(bed_mm[:2]) <= 0:
            return {"ok": False, "error": "bed_mm must be [x, y] or [x, y, z] in mm"}
        d, build = _build(project)
        bed_x, bed_y = float(bed_mm[0]), float(bed_mm[1])
        bed_z = float(bed_mm[2]) if len(bed_mm) > 2 else None
        items, too_big, sizes = [], [], {}
        for name, info in _printable(build).items():
            lo, hi = _mesh(d, name).bounds
            w, h, z = (float(hi[i] - lo[i]) for i in range(3))
            sizes[name] = [round(w, 2), round(h, 2), round(z, 2)]
            fits_xy = (w <= bed_x and h <= bed_y) or (h <= bed_x and w <= bed_y)
            if not fits_xy or (bed_z is not None and z > bed_z):
                too_big.append({"part": name, "size_mm": sizes[name],
                                "reason": "footprint larger than the bed" if not fits_xy else f"taller than {bed_z} mm"})
                continue
            items += [{"part": name, "copy": c + 1, "w": w, "h": h} for c in range(int(info.get("qty", 1) or 1))]
        plates = _pack(items, bed_x, bed_y, gap_mm)
        used = [round(100 * sum(i["size_mm"][0] * i["size_mm"][1] for i in p) / (bed_x * bed_y), 1) for p in plates]
        return {"ok": True, "bed_mm": [bed_x, bed_y] + ([bed_z] if bed_z is not None else []), "gap_mm": gap_mm,
                "fits_one_plate": len(plates) <= 1 and not too_big, "plates_needed": len(plates),
                "plates": [{"plate": i + 1, "bed_used_pct": used[i], "parts": p} for i, p in enumerate(plates)],
                "own_plate": [p[0]["part"] for p in plates if len(p) == 1 and len(plates) > 1],
                "too_big": too_big, "part_size_mm": sizes,
                "note": "Bounding-box shelf packing in the as-exported orientation: a slicer's arrange can nest tighter. "
                        "Brims, skirts and printer keep-out zones are not included."}
    except (ValueError, KeyError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e).strip("'\"")}


def slice(project: str, part: str, route: str = "auto", profile: str = "", filament_profile: str = "") -> dict:  # noqa: A001
    """Slice one part to G-code at projects/<slug>/out/make/<part>.gcode and return time and filament from it.

    route: "prusaslicer", "orcaslicer" or "auto" (first one installed). profile is a path to the slicer
    config: for PrusaSlicer a .ini exported from the app (several separated by ';'); for OrcaSlicer
    "<machine.json>;<process.json>" with filament_profile "<filament.json>". Without a profile PrusaSlicer
    uses its built-in defaults, which will not match your printer. Returns ok False with install guidance
    when no slicer is present.
    """
    try:
        d, build = _build(project)
        _printable(build, part)
        chosen, err = _resolve_route(route, profile)
        if err:
            return err
        return _run_slicer(d, part, chosen, profile, filament_profile, {})
    except (ValueError, KeyError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e).strip("'\"")}


def register(mcp) -> None:
    for fn in (print_estimate, print_orient, print_bed_layout, slice):
        mcp.tool()(fn)
    from . import printers

    printers.register(mcp)
