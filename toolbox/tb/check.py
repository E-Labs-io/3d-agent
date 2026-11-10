"""Design checks that return measurements: mesh health, printability, wall thickness, interference."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from .common import load_json, project_dir


def _build(project: str) -> tuple[Path, dict]:
    d = project_dir(project)
    build = load_json(d / "out" / "build.json")
    if not build:
        raise FileNotFoundError(f"Project '{project}' has not been built. Run cad_build first.")
    return d, build


def _real_parts(build: dict, part: str = "") -> dict:
    parts = {n: p for n, p in build["parts"].items() if not p["reference"]}
    if part:
        if part not in parts:
            raise KeyError(f"No manufactured part '{part}'. Parts: {sorted(parts)}")
        return {part: parts[part]}
    return parts


def _density(material: str) -> tuple[float | None, str]:
    try:
        from .materials import get_material
        m = get_material(material) or {}
        if m.get("density_g_cm3"):
            return float(m["density_g_cm3"]), "materials table"
    except Exception:  # noqa: BLE001 - materials module is optional
        pass
    return None, f"no density for '{material}'"


def _wall_limit(process: str) -> dict:
    """Minimum wall for the process from the sourced rule tables, if there is one."""
    try:
        from .rules import limits
        lim = limits(process).get("min_wall_mm") or {}
        return {"min_mm": lim.get("min"), "recommended_mm": lim.get("recommended"), "source": lim.get("source")}
    except Exception:  # noqa: BLE001 - rules module is optional
        return {}


def _wall_thickness(mesh, samples: int = 4000) -> dict:
    """Thickness sampled by casting a ray inward from random surface points."""
    import trimesh

    pts, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=1)
    normals = mesh.face_normals[face_idx]
    origins = pts - normals * 1e-3
    hits, ray_idx, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
    if len(hits) == 0:
        return {"sampled": 0}
    dist = np.linalg.norm(hits - origins[ray_idx], axis=1)
    thinnest = int(np.argmin(dist))
    return {
        "sampled": int(len(dist)),
        "min_mm": round(float(dist.min()), 3),
        "p05_mm": round(float(np.percentile(dist, 5)), 3),
        "median_mm": round(float(np.median(dist)), 3),
        "thinnest_at": [round(float(v), 2) for v in origins[ray_idx][thinnest]],
    }


def check_mesh(project: str, part: str = "") -> dict:
    """Mesh health of each manufactured part's print STL: watertight, volume, mass, wall thickness.

    Lengths in mm, volume in mm3, mass in g. Thickness is sampled, so treat min_mm as approximate.
    """
    import trimesh

    try:
        d, build = _build(project)
        parts = _real_parts(build, part)
    except (FileNotFoundError, KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    out = {}
    for name, p in parts.items():
        mesh = trimesh.load_mesh(d / p["files"]["stl"])
        rho, rho_src = _density(p["material"])
        vol = float(mesh.volume)
        row = {
            "watertight": bool(mesh.is_watertight),
            "winding_consistent": bool(mesh.is_winding_consistent),
            "bodies": int(mesh.body_count),
            "triangles": int(len(mesh.faces)),
            "volume_mm3": round(vol, 1),
            "volume_vs_cad_pct": round(100 * (vol - p["volume_mm3"]) / p["volume_mm3"], 2),
            "size_mm": [round(float(v), 2) for v in mesh.extents],
            "material": p["material"],
            "solid_mass_g": round(vol / 1000 * rho, 1) if rho else None,
            "density_source": rho_src,
            "wall_thickness": _wall_thickness(mesh),
        }
        limit = _wall_limit(p["process"])
        thinnest = row["wall_thickness"].get("min_mm")
        row["wall_limit"] = limit
        row["wall_ok"] = not (limit.get("min_mm") and thinnest is not None and thinnest < limit["min_mm"])
        row["pass"] = row["watertight"] and row["winding_consistent"] and row["bodies"] == 1 and row["wall_ok"]
        out[name] = row
    return {"ok": True, "all_pass": all(r["pass"] for r in out.values()), "parts": out,
            "note": "solid_mass_g assumes 100% infill; a sliced print is lighter."}


def check_printability(project: str, part: str = "", build_volume_mm: list[float] | None = None,
                       support_angle_deg: float = 45.0, max_bridge_mm: float = 5.0,
                       nozzle_mm: float = 0.4) -> dict:
    """FDM printability of each part in its print orientation: overhangs, bridges, thin features, bed fit.

    Uses the augura analyser on the exact STEP geometry. Returns findings with severity and location (mm).
    """
    try:
        d, build = _build(project)
        parts = _real_parts(build, part)
    except (FileNotFoundError, KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    vol = build_volume_mm or [256, 256, 256]
    out = {}
    for name, p in parts.items():
        cmd = [str(Path(sys.executable).parent / "augura"), "analyze", str(d / p["files"]["step"]), "--format", "json",
               "--support-angle", str(support_angle_deg), "--max-bridge", str(max_bridge_mm),
               "--nozzle", str(nozzle_mm), "--build-volume", *map(str, vol)]
        if p["print_flip"]:
            cmd += ["--orient", "180", "0", "0"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        try:
            findings = json.loads(proc.stdout)["findings"]
        except (json.JSONDecodeError, KeyError):
            out[name] = {"error": (proc.stderr or proc.stdout)[-600:]}
            continue
        by_kind: dict[str, dict] = {}
        for f in findings:
            k = by_kind.setdefault(f["kind"], {"count": 0, "area_mm2": 0.0, "worst": f["severity"]})
            k["count"] += 1
            k["area_mm2"] = round(k["area_mm2"] + float(f.get("area") or 0), 1)
            if f["severity"] == "error":
                k["worst"] = "error"
        out[name] = {
            "orientation": "flipped (X 180)" if p["print_flip"] else "as modelled",
            "errors": sum(f["severity"] == "error" for f in findings),
            "warnings": sum(f["severity"] == "warning" for f in findings),
            "summary": by_kind,
            "findings": [{"kind": f["kind"], "severity": f["severity"], "message": f["message"],
                          "at_mm": [round(float(v), 2) for v in (f.get("location") or [])]} for f in findings[:40]],
        }
    clean = all("error" not in r and r["errors"] == 0 and r["warnings"] == 0 for r in out.values())
    return {"ok": True, "clean": clean, "build_volume_mm": vol, "parts": out}


def check_interference(project: str, clearance_report: bool = True) -> dict:
    """Overlap volume between every pair of parts in assembled position, including reference parts.

    Any overlap above 1 mm3 means two solids occupy the same space. Volumes in mm3.
    """
    import manifold3d as m3
    import trimesh

    try:
        d, build = _build(project)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    solids = {}
    for name, p in build["parts"].items():
        mesh = trimesh.load_mesh(d / p["files"]["view"].split("?")[0])
        solids[name] = m3.Manifold(m3.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                                           tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))
    names = sorted(solids)
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            overlap = float((solids[a] ^ solids[b]).volume())
            if overlap > 1.0 or clearance_report:
                pairs.append({"a": a, "b": b, "overlap_mm3": round(overlap, 2), "clash": overlap > 1.0})
    clashes = [p for p in pairs if p["clash"]]
    return {"ok": True, "clear": not clashes, "clashes": clashes, "pairs": pairs}


def check_all(project: str, build_volume_mm: list[float] | None = None) -> dict:
    """Run every check and give one pass/fail verdict with the reasons. The design loop's gate."""
    mesh = check_mesh(project)
    if not mesh["ok"]:
        return mesh
    printable = check_printability(project, build_volume_mm=build_volume_mm)
    clash = check_interference(project, clearance_report=False)
    problems = []
    for name, r in mesh["parts"].items():
        if not (r["watertight"] and r["winding_consistent"] and r["bodies"] == 1):
            problems.append(f"{name}: mesh not a single watertight body")
        if not r["wall_ok"]:
            problems.append(f"{name}: wall {r['wall_thickness']['min_mm']} mm at {r['wall_thickness']['thinnest_at']} "
                            f"is under the {r['wall_limit']['min_mm']} mm minimum for {r['material']}")
    for name, r in printable.get("parts", {}).items():
        if "error" in r:
            problems.append(f"{name}: printability analysis failed")
        elif r["errors"] or r["warnings"]:
            problems.append(f"{name}: {r['errors']} printability errors, {r['warnings']} warnings "
                            f"({', '.join(r['summary'])})")
    for c in clash.get("clashes", []):
        problems.append(f"{c['a']} overlaps {c['b']} by {c['overlap_mm3']} mm3")
    return {"ok": True, "pass": not problems, "problems": problems,
            "mesh": mesh, "printability": printable, "interference": clash}


def register(mcp) -> None:
    for fn in (check_mesh, check_printability, check_interference, check_all):
        mcp.tool()(fn)
