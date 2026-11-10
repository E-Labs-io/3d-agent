"""Design-for-manufacture rules per process, read from published design guides."""
from __future__ import annotations

from functools import lru_cache

from .common import DATA, load_json, project_dir, save_json
from .materials import get_material, norm_process

RULES_DIR = DATA / "rules"
NOT_MADE = {"bought", "reference", "none", ""}


def processes() -> list[str]:
    return sorted(p.stem for p in RULES_DIR.glob("*.json"))


@lru_cache(maxsize=None)
def _load(process: str) -> dict | None:
    return load_json(RULES_DIR / f"{process}.json")


def limits(process: str) -> dict:
    """Thresholds for one process, keyed by parameter name, for other modules (tb.check) to import.

    Each value is the rule's limit dict (any of min, max, recommended, typical, range, unit) plus
    rule_id and source. Lengths are mm, angles degrees; '_x_thickness' style parameters are ratios.
    Returns {} for an unknown process.
    """
    doc = _load(norm_process(process))
    if not doc:
        return {}
    return {r["parameter"]: {**r["limit"], "rule_id": r["id"], "source": r["source"]} for r in doc["rules"]}


def rules_get(process: str) -> dict:
    """Design rules for a process with limits, units and source URLs.

    process: fdm, sla, sls, cnc_milling, sheet_metal or injection_moulding (cnc, sheet, im also accepted).
    Where published guides disagree the limit has a 'range' and 'sources' lists what each guide says.
    """
    p = norm_process(process)
    doc = _load(p)
    if not doc:
        return {"ok": False, "error": f"No rules for process '{process}'. Available: {processes()}"}
    return {"ok": True, "process": p, "title": doc["title"], "count": len(doc["rules"]), "rules": doc["rules"]}


def _check(rule_id: str, description: str, status: str, measured, limit, unit: str, source: str, note: str = "") -> dict:
    c = {"rule_id": rule_id, "description": description, "status": status, "measured": measured,
         "limit": limit, "unit": unit, "source": source}
    if note:
        c["note"] = note
    return c


def _wall_parameter(process: str, material: str) -> str:
    if process == "cnc_milling" and (get_material(material) or {}).get("category") == "plastic":
        return "min_wall_plastic_mm"
    return "sheet_thickness_mm" if process == "sheet_metal" else "min_wall_mm"


def _part_checks(part: dict, process: str, volume: list[float]) -> list[dict]:
    bbox = [float(x) for x in part["bbox_mm"]]
    checks = []
    fits = all(b <= v for b, v in zip(sorted(bbox), sorted(volume)))
    checks.append(_check("build_volume", "Part bounding box fits the build volume in an axis-aligned orientation",
                         "pass" if fits else "fail", bbox, volume, "mm", "build_volume_mm argument"))
    lim = limits(process)
    param = _wall_parameter(process, part.get("material", ""))
    wall = lim.get(param)
    if wall and wall.get("min") is not None:
        thinnest = min(bbox)
        status = "fail" if thinnest < wall["min"] else "warn" if thinnest < wall.get("recommended", wall["min"]) else "pass"
        checks.append(_check(wall["rule_id"], f"Smallest bounding-box dimension is not below {param}", status,
                             round(thinnest, 3), {k: wall[k] for k in ("min", "recommended") if k in wall}, "mm",
                             wall["source"], "Whole-part screen only; local wall thickness needs the mesh (tb.check)."))
    checks.append(_check("solid_valid", "CAD solid is valid", "pass" if part.get("valid") else "fail",
                         bool(part.get("valid")), True, "bool", "out/build.json (cad_build)"))
    if "mesh" in part:
        tight = bool(part["mesh"].get("watertight"))
        checks.append(_check("mesh_watertight", "Exported mesh is watertight", "pass" if tight else "fail",
                             tight, True, "bool", "out/build.json (cad_build)"))
    return checks


def rules_check(project: str, process: str = "", build_volume_mm: list[float] = [256, 256, 256]) -> dict:  # noqa: B006
    """Check a built project against the rules that need no mesh. Returns pass/warn/fail per rule per part.

    Reads projects/<slug>/out/build.json. Checks: bounding box fits build_volume_mm (mm, any axis order),
    smallest bounding-box dimension against the process minimum wall, solid validity, mesh watertightness.
    process "" uses each part's own process. Local wall thickness, overhangs and holes are not checked
    here: they are listed under not_checked and belong to the mesh checks in tb.check.
    """
    try:
        d = project_dir(project)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False, "error": str(e)}
    build = load_json(d / "out" / "build.json")
    if not build or not build.get("parts"):
        return {"ok": False, "error": f"No out/build.json for '{project}'. Run cad_build('{project}') first."}
    try:
        volume = [float(v) for v in build_volume_mm]
    except (TypeError, ValueError):
        volume = []
    if len(volume) != 3 or min(volume) <= 0:
        return {"ok": False, "error": "build_volume_mm must be three positive numbers in mm, e.g. [256, 256, 256]"}
    forced = norm_process(process)
    if forced and not _load(forced):
        return {"ok": False, "error": f"No rules for process '{process}'. Available: {processes()}"}

    parts, skipped, counts, not_checked = {}, [], {"pass": 0, "warn": 0, "fail": 0}, {}
    for name, part in build["parts"].items():
        own = norm_process(part.get("process", ""))
        if part.get("reference") or own in NOT_MADE:
            skipped.append({"part": name, "reason": "reference or bought item, not manufactured"})
            continue
        proc = forced or own
        if not _load(proc):
            skipped.append({"part": name, "reason": f"no rule file for process '{proc}'"})
            continue
        checks = _part_checks(part, proc, volume)
        for c in checks:
            counts[c["status"]] += 1
        parts[name] = {"process": proc, "material": part.get("material"), "checks": checks}
        done = {c["rule_id"] for c in checks}
        not_checked.setdefault(proc, [r["id"] for r in _load(proc)["rules"] if r["id"] not in done])
    if not parts:
        return {"ok": False, "error": "No manufactured parts to check.", "skipped": skipped}
    result = {"ok": True, "project": project, "build_volume_mm": volume, "passed": counts["fail"] == 0,
              "summary": counts, "parts": parts, "skipped": skipped, "not_checked": not_checked,
              "note": "not_checked rules need geometry-level measurement (tb.check) or design review."}
    save_json(d / "out" / "rules" / "check.json", result)
    result["report"] = "out/rules/check.json"
    return result


def register(mcp) -> None:
    for fn in (rules_get, rules_check):
        mcp.tool()(fn)
