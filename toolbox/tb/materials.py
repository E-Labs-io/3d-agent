"""Material data: sourced properties for printed, machined and moulded materials."""
from __future__ import annotations

import re
from functools import lru_cache

from .common import DATA, load_json

MATERIALS_FILE = DATA / "materials" / "materials.json"

# build.json and callers use short process names; the data uses the rule-file names.
PROCESS_ALIASES = {
    "cnc": "cnc_milling", "milling": "cnc_milling", "machining": "cnc_milling", "cnc_machining": "cnc_milling",
    "sheet": "sheet_metal", "sheetmetal": "sheet_metal",
    "im": "injection_moulding", "injection_molding": "injection_moulding", "moulding": "injection_moulding",
    "molding": "injection_moulding", "fff": "fdm", "msla": "sla", "resin": "sla", "mjf": "sls",
}

# In-plane strength, most conservative definition first. Z / interlayer values are never used here.
STRENGTH_KEYS = ("tensile_yield_mpa", "tensile_yield_xy_mpa", "tensile_strength_mpa", "tensile_strength_xy_mpa")
STRENGTH_Z_KEYS = ("tensile_strength_z_mpa", "interlayer_strength_z_mpa")
MODULUS_KEYS = ("youngs_modulus_mpa", "youngs_modulus_xy_mpa")
HEAT_KEYS = ("heat_deflection_c", "heat_deflection_1_8mpa_c", "glass_transition_c")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def norm_process(process: str) -> str:
    p = re.sub(r"[^a-z0-9]+", "_", str(process or "").lower()).strip("_")
    return PROCESS_ALIASES.get(p, p)


@lru_cache(maxsize=1)
def _table() -> tuple[list[dict], dict[str, str]]:
    doc = load_json(MATERIALS_FILE, {}) or {}
    mats = doc.get("materials", [])
    index: dict[str, str] = {}
    for m in mats:  # ids and names win over aliases, earlier records win over later ones
        index.setdefault(_norm(m["id"]), m["id"])
        index.setdefault(_norm(m["name"]), m["id"])
    for m in mats:
        for a in m.get("aliases", []):
            index.setdefault(_norm(a), m["id"])
    return mats, index


def _flat(m: dict) -> dict:
    """Numbers at the top level (what other modules read), provenance under 'sources'."""
    out = {k: m[k] for k in ("id", "name", "family", "category", "form")}
    out["processes"] = list(m["processes"])
    sources = {}
    for key, rec in m["properties"].items():
        out[key] = rec["value"]
        sources[key] = {k: str(v) for k, v in rec.items() if k != "value"}
    out["sources"] = sources
    return out


def get_material(name: str) -> dict | None:
    """Look up a material by id, name or alias (case-insensitive). Returns a flat dict or None.

    Property keys carry their unit (density_g_cm3, tensile_yield_xy_mpa, ...). 'sources' maps each
    property key to its source URL and note. density_g_cm3 is always present.
    """
    mats, index = _table()
    mid = index.get(_norm(name))
    if mid is None:
        return None
    return _flat(next(m for m in mats if m["id"] == mid))


def _first(rec: dict, keys: tuple[str, ...]) -> tuple[float | None, str | None]:
    for k in keys:
        if isinstance(rec.get(k), (int, float)):
            return float(rec[k]), k
    return None, None


def _derived(rec: dict) -> dict:
    """Comparison figures computed from a flat record. Specific values are strength or modulus / density."""
    rho = rec["density_g_cm3"]
    s, sk = _first(rec, STRENGTH_KEYS)
    sz, szk = _first(rec, STRENGTH_Z_KEYS)
    e, ek = _first(rec, MODULUS_KEYS)
    t, tk = _first(rec, HEAT_KEYS)
    d = {"strength_mpa": s, "strength_basis": sk, "strength_z_mpa": sz, "strength_z_basis": szk,
         "modulus_mpa": e, "modulus_basis": ek, "heat_limit_c": t, "heat_limit_basis": tk,
         "specific_strength_kn_m_kg": round(s / rho, 1) if s else None,
         "specific_modulus_mn_m_kg": round(e / rho / 1000, 2) if e else None,
         "z_to_xy_strength_ratio": round(sz / s, 2) if s and sz else None}
    return d


def material_list(process: str = "") -> dict:
    """List materials in the table, optionally only those for one process.

    process: fdm, sla, sls, cnc_milling, sheet_metal or injection_moulding ("" = all).
    Returns id, name, family, processes, density (g/cm3) and aliases per material.
    """
    mats, _ = _table()
    p = norm_process(process)
    rows = [{"id": m["id"], "name": m["name"], "family": m["family"], "processes": m["processes"],
             "density_g_cm3": m["properties"]["density_g_cm3"]["value"], "aliases": m.get("aliases", [])}
            for m in mats if not p or p in m["processes"]]
    if not rows:
        known = sorted({x for m in mats for x in m["processes"]})
        return {"ok": False, "error": f"No materials for process '{process}'. Known processes: {known}"}
    return {"ok": True, "count": len(rows), "materials": rows}


def material_get(name: str) -> dict:
    """Properties of one material with the source URL of every value. Accepts aliases ("petg", "6061").

    Units are in the key names (g/cm3, MPa, %, C). _xy is in the layer plane, _z or interlayer is
    through the layers, _xz is an on-edge printed specimen. Missing keys were not sourced.
    """
    rec = get_material(name)
    if rec is None:
        _, index = _table()
        hint = sorted(k for k in index if _norm(name) and (_norm(name) in k or k in _norm(name)))[:8]
        return {"ok": False, "error": f"No material '{name}'. Use material_list to see the table.", "similar": hint}
    return {"ok": True, "material": rec, "derived": _derived(rec)}


def material_compare(names: list[str]) -> dict:
    """Compare materials side by side: density, in-plane strength, modulus, heat limit, specific strength.

    specific_strength_kn_m_kg = strength_mpa / density_g_cm3. Each figure names the property it came
    from (yield or ultimate, xy or bulk), because those are not like-for-like. Sorted by specific strength.
    """
    rows, missing = [], []
    for n in names:
        rec = get_material(n)
        if rec is None:
            missing.append(n)
            continue
        rows.append({"id": rec["id"], "name": rec["name"], "processes": rec["processes"],
                     "density_g_cm3": rec["density_g_cm3"], **_derived(rec),
                     "sources": sorted({s["source"] for s in rec["sources"].values()})})
    if not rows:
        return {"ok": False, "error": f"None of {names} are in the materials table. Use material_list."}
    rows.sort(key=lambda r: -(r["specific_strength_kn_m_kg"] or 0))
    out = {"ok": True, "materials": rows,
           "note": "Strength basis differs between records (yield vs ultimate, printed vs bulk); check strength_basis."}
    if missing:
        out["not_found"] = missing
    return out


_RANK = {"specific_strength": "specific_strength_kn_m_kg", "strength": "strength_mpa", "stiffness": "modulus_mpa",
         "heat": "heat_limit_c", "density": "density_g_cm3"}


def material_select(requirements: dict) -> dict:
    """Filter and rank materials against requirements. Returns candidates with reason and limiting property.

    requirements keys (all optional): process, min_strength_mpa (in-plane yield, or ultimate where no yield
    is on record), min_strength_z_mpa (through-layer, printed parts), min_modulus_mpa, max_density_g_cm3,
    min_heat_deflection_c, rank_by (specific_strength | strength | stiffness | heat | density).
    A material with no data for a required property is rejected, not assumed to pass.
    """
    req = dict(requirements or {})
    unknown = set(req) - {"process", "min_strength_mpa", "min_strength_z_mpa", "min_modulus_mpa",
                          "max_density_g_cm3", "min_heat_deflection_c", "rank_by"}
    if unknown:
        return {"ok": False, "error": f"Unknown requirement keys {sorted(unknown)}. See the tool description."}
    rank_by = req.get("rank_by", "specific_strength")
    if rank_by not in _RANK:
        return {"ok": False, "error": f"rank_by must be one of {sorted(_RANK)}"}
    process = norm_process(req.get("process", ""))
    # (requirement key, derived/flat key, basis key, +1 for a minimum / -1 for a maximum)
    tests = [("min_strength_mpa", "strength_mpa", "strength_basis", 1),
             ("min_strength_z_mpa", "strength_z_mpa", "strength_z_basis", 1),
             ("min_modulus_mpa", "modulus_mpa", "modulus_basis", 1),
             ("min_heat_deflection_c", "heat_limit_c", "heat_limit_basis", 1),
             ("max_density_g_cm3", "density_g_cm3", None, -1)]
    mats, _ = _table()
    candidates, rejected = [], []
    for m in mats:
        if process and process not in m["processes"]:
            continue
        rec = _flat(m)
        d = {**_derived(rec), "density_g_cm3": rec["density_g_cm3"]}
        fails, margins = [], []
        for rkey, dkey, bkey, sign in tests:
            if req.get(rkey) is None:
                continue
            limit, val = float(req[rkey]), d[dkey]
            if val is None:
                fails.append(f"no sourced value for {dkey}")
                continue
            margin = (val / limit if sign > 0 else limit / val) if limit > 0 and val > 0 else float("inf")
            basis = d.get(bkey) if bkey else dkey
            if margin < 1:
                fails.append(f"{basis} {val} {'<' if sign > 0 else '>'} required {limit}")
            margins.append((margin, basis, val, limit))
        row = {"id": rec["id"], "name": rec["name"], "processes": rec["processes"]}
        if fails:
            rejected.append({**row, "reason": "; ".join(fails)})
            continue
        row.update({k: d[k] for k in ("density_g_cm3", "strength_mpa", "strength_basis", "strength_z_mpa",
                                      "modulus_mpa", "heat_limit_c", "heat_limit_basis",
                                      "specific_strength_kn_m_kg")})
        if margins:
            mg, basis, val, limit = min(margins, key=lambda x: x[0])
            row["limiting_property"] = basis
            row["limiting_margin"] = round(mg, 2)
            row["reason"] = (f"Meets all {len(margins)} requirement(s); tightest is {basis} = {val} "
                             f"against {limit} (margin x{mg:.2f}).")
        else:
            row["limiting_property"] = None
            row["reason"] = "No numeric requirements given; ranked only."
        row["sources"] = sorted({s["source"] for s in rec["sources"].values()})
        candidates.append(row)
    key = _RANK[rank_by]
    low_is_better = rank_by == "density"
    candidates.sort(key=lambda r: (r[key] is None, (r[key] or 0) * (1 if low_is_better else -1)))
    for i, c in enumerate(candidates, 1):
        c["rank"] = i
    return {"ok": True, "requirements": req, "ranked_by": key, "candidates": candidates, "rejected": rejected,
            "note": "Printed-material strengths are data-sheet specimens at 100% infill; apply your own safety factor."}


def register(mcp) -> None:
    for fn in (material_list, material_get, material_compare, material_select):
        mcp.tool()(fn)
