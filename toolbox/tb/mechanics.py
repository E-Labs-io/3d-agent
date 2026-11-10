"""Hand-calculation tools: beams, bolts, columns, press fits, thermal growth, mass and CoG.

No meshing. Every tool echoes its inputs and the formula used so the agent can show its working.
Units: mm, N, MPa, g, degrees C.
"""
from __future__ import annotations

import math
import re

from .common import load_json, project_dir

G_MM_S2 = 9806.65

# --- material lookup ----------------------------------------------------------------------


def _num(v):
    """A property may be a bare number or a record like {"value": 2100, "source": ...}."""
    if isinstance(v, dict):
        for k in ("value", "typical", "nominal", "mean", "min"):
            if isinstance(v.get(k), (int, float)):
                return float(v[k])
        return None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _flatten(d: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in d.items():
        key = f"{prefix}{k}".lower()
        n = _num(v)
        if n is not None:
            flat[key] = n
        elif isinstance(v, dict):
            flat.update(_flatten(v, f"{key}_"))
        elif isinstance(v, str):
            flat[key] = v
    return flat


def _pick(flat: dict, *patterns: str):
    """First numeric value whose key matches one of the regex patterns, in pattern order."""
    for pat in patterns:
        for k, v in flat.items():
            if isinstance(v, float) and re.search(pat, k):
                return v, k
    return None, None


def material_props(name: str = "", E_mpa: float = 0, nu: float = 0, yield_mpa: float = 0,
                   density_g_cm3: float = 0) -> dict:
    """Merge tb.materials data (if that module is present) with explicit overrides.

    Returns the values found, where each came from, and the assumptions made. Missing values
    stay None: nothing is invented here.
    """
    flat, notes, src = {}, [], {}
    if name:
        try:
            from . import materials  # written by another builder; optional

            rec = materials.get_material(name)
            if isinstance(rec, dict) and rec.get("ok", True) and isinstance(rec.get("material", rec), dict):
                flat = _flatten(rec.get("material", rec))
            else:
                notes.append(f"tb.materials has no record for '{name}'")
        except ImportError:
            notes.append("tb.materials is not available; using explicit overrides only")
        except Exception as e:  # noqa: BLE001 - lookup failure must not stop a calculation
            notes.append(f"tb.materials lookup for '{name}' failed: {type(e).__name__}: {e}")

    not_z = r"^(?!.*(_z_|_z$|zz|interlayer))"
    out = {"name": name or None}
    picks = {
        "E_mpa": (E_mpa, [not_z + r".*youngs_modulus.*xy", not_z + r".*youngs_modulus", not_z + r".*(tensile|elastic)_modulus"]),
        "nu": (nu, [r"poisson"]),
        "density_g_cm3": (density_g_cm3, [r"density_g_cm3"]),
        "E_z_mpa": (0, [r"(youngs|tensile|elastic)_modulus.*(_z_|_z$|interlayer)", r"(_z_|^z_).*modulus"]),
        "strength_z_mpa": (0, [r"tensile_(yield|strength).*(_z_|_z$|interlayer)", r"(_z_|^z_|interlayer).*(yield|strength)"]),
    }
    for key, (override, pats) in picks.items():
        if override and override > 0:
            out[key], src[key] = float(override), "explicit override"
        else:
            v, k = _pick(flat, *pats)
            out[key] = v
            if v is not None:
                src[key] = f"tb.materials:{k}"

    if yield_mpa and yield_mpa > 0:
        out["yield_mpa"], src["yield_mpa"] = float(yield_mpa), "explicit override"
    else:
        v, k = _pick(flat, not_z + r".*tensile_yield.*xy", not_z + r".*tensile_yield", not_z + r".*yield")
        if v is None:
            v, k = _pick(flat, not_z + r".*tensile_strength.*xy", not_z + r".*tensile_strength")
            if v is not None:
                notes.append("No yield strength on record: the safety factor uses tensile strength instead")
        out["yield_mpa"] = v
        if v is not None:
            src["yield_mpa"] = f"tb.materials:{k}"

    if out["nu"] is None and out["E_mpa"]:
        family = " ".join(str(flat.get(k, "")) for k in ("category", "family", "class", "type")).lower()
        metal = "metal" in family or (not family.strip() and out["E_mpa"] >= 40000)
        out["nu"] = 0.3 if metal else 0.35
        src["nu"] = "assumed"
        notes.append(f"Poisson's ratio assumed {out['nu']} ({'metal' if metal else 'plastic'} default), not measured")
    out["sources"] = src
    out["notes"] = notes
    return out


# --- sections -----------------------------------------------------------------------------


def _section(section: str, width_mm: float, height_mm: float, diameter_mm: float, inner_diameter_mm: float) -> dict:
    """Area, second moment about the bending axis, extreme fibre distance, peak shear factor."""
    s = section.lower()
    if s in ("rect", "rectangular", "rectangle"):
        if width_mm <= 0 or height_mm <= 0:
            raise ValueError("rect section needs width_mm and height_mm (height is in the load direction)")
        return {"type": "rect", "area_mm2": width_mm * height_mm, "I_mm4": width_mm * height_mm ** 3 / 12,
                "c_mm": height_mm / 2, "shear_factor": 1.5, "formula": "I = b*h^3/12, A = b*h"}
    if s in ("round", "circle", "solid"):
        if diameter_mm <= 0:
            raise ValueError("round section needs diameter_mm")
        return {"type": "round", "area_mm2": math.pi * diameter_mm ** 2 / 4, "I_mm4": math.pi * diameter_mm ** 4 / 64,
                "c_mm": diameter_mm / 2, "shear_factor": 4 / 3, "formula": "I = pi*d^4/64, A = pi*d^2/4"}
    if s in ("tube", "pipe"):
        if not 0 < inner_diameter_mm < diameter_mm:
            raise ValueError("tube section needs diameter_mm > inner_diameter_mm > 0")
        return {"type": "tube", "area_mm2": math.pi * (diameter_mm ** 2 - inner_diameter_mm ** 2) / 4,
                "I_mm4": math.pi * (diameter_mm ** 4 - inner_diameter_mm ** 4) / 64, "c_mm": diameter_mm / 2,
                "shear_factor": 2.0, "formula": "I = pi*(D^4-d^4)/64, A = pi*(D^2-d^2)/4"}
    raise ValueError(f"Unknown section '{section}': use rect, round or tube")


def _r(x, n=4):
    return None if x is None else float(f"{x:.{n + 2}g}") if abs(x) < 1 else round(x, n)


def _fail(e: Exception) -> dict:
    return {"ok": False, "error": str(e)}


# --- beams --------------------------------------------------------------------------------

_BEAM = {
    ("cantilever", "point"): (1 / 3, 1.0, 1.0, "tip load: delta = F*L^3/(3*E*I), M_max = F*L at the root, V = F"),
    ("cantilever", "distributed"): (1 / 8, 0.5, 1.0, "uniform load W total: delta = W*L^3/(8*E*I), M_max = W*L/2 at the root, V = W"),
    ("simply_supported", "point"): (1 / 48, 0.25, 0.5, "centre load: delta = F*L^3/(48*E*I), M_max = F*L/4 at midspan, V = F/2"),
    ("simply_supported", "distributed"): (5 / 384, 0.125, 0.5, "uniform load W total: delta = 5*W*L^3/(384*E*I), M_max = W*L/8 at midspan, V = W/2"),
}


def beam_check(support: str, load_type: str, load_n: float, length_mm: float, section: str = "rect",
               width_mm: float = 0, height_mm: float = 0, diameter_mm: float = 0, inner_diameter_mm: float = 0,
               material: str = "", E_mpa: float = 0, yield_mpa: float = 0) -> dict:
    """Euler-Bernoulli beam: max deflection (mm), bending and shear stress (MPa), safety factor.

    support: cantilever | simply_supported. load_type: point (tip / midspan) | distributed
    (load_n is then the TOTAL load spread evenly). section: rect (height_mm along the load) |
    round | tube. Give material or E_mpa / yield_mpa. Slender beams only (length > 10x depth).
    """
    try:
        key = (support.lower().replace("-", "_").replace(" ", "_"), load_type.lower())
        if key not in _BEAM:
            raise ValueError("support must be cantilever or simply_supported; load_type point or distributed")
        if length_mm <= 0:
            raise ValueError("length_mm must be positive")
        sec = _section(section, width_mm, height_mm, diameter_mm, inner_diameter_mm)
        mat = material_props(material, E_mpa=E_mpa, yield_mpa=yield_mpa)
        if not mat["E_mpa"]:
            raise ValueError("No Young's modulus: pass E_mpa or a material known to tb.materials")
    except (ValueError, FileNotFoundError) as e:
        return _fail(e)
    kd, km, kv, text = _BEAM[key]
    F, L, E, I = abs(load_n), length_mm, mat["E_mpa"], sec["I_mm4"]
    moment = km * F * L
    sigma = moment * sec["c_mm"] / I
    tau = sec["shear_factor"] * kv * F / sec["area_mm2"]
    depth = 2 * sec["c_mm"]
    warnings = []
    if L / depth < 10:
        warnings.append(f"Span/depth is {L / depth:.1f}: shear deflection is ignored, real deflection is larger")
    sy = mat["yield_mpa"]
    return {
        "ok": True,
        "max_deflection_mm": _r(kd * F * L ** 3 / (E * I)),
        "max_moment_nmm": _r(moment, 2),
        "max_bending_stress_mpa": _r(sigma),
        "max_shear_stress_mpa": _r(tau),
        "safety_factor_yield": _r(sy / sigma, 3) if sy and sigma else None,
        "section": {k: (_r(v) if isinstance(v, float) else v) for k, v in sec.items()},
        "formula": f"{text}; sigma = M*c/I; tau_max = {sec['shear_factor']:.3g}*V/A; {sec['formula']}",
        "inputs": {"support": key[0], "load_type": key[1], "load_n": load_n, "length_mm": L, "section": sec["type"],
                   "width_mm": width_mm, "height_mm": height_mm, "diameter_mm": diameter_mm,
                   "inner_diameter_mm": inner_diameter_mm, "E_mpa": E, "yield_mpa": sy},
        "material": mat, "warnings": warnings,
    }


# --- bolts --------------------------------------------------------------------------------

# Coarse pitch series, ISO 261 / ISO 262.
_ISO_COARSE_PITCH = {1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5, 4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25, 10: 1.5, 12: 1.75,
                     14: 2.0, 16: 2.0, 20: 2.5, 24: 3.0, 30: 3.5}
# ISO 898-1:2013 Table 3, MPa: (proof stress Sp, minimum tensile Rm, yield / 0.2 % proof).
# Classes 8.8 change above M16.
_ISO_CLASS = {"4.6": (225, 400, 240), "4.8": (310, 420, 340), "5.8": (380, 520, 420),
              "8.8": (580, 800, 640), "8.8>16": (600, 830, 660), "9.8": (650, 900, 720),
              "10.9": (830, 1040, 940), "12.9": (970, 1220, 1100)}
# SAE J429 Table 1, ksi: grade -> list of (max diameter in, proof, tensile, yield).
_SAE_GRADE = {"2": [(0.75, 55, 74, 57), (1.5, 33, 60, 36)], "5": [(1.0, 85, 120, 92), (1.5, 74, 105, 81)],
              "8": [(1.5, 120, 150, 130)]}
_KSI = 6.894757


def _parse_thread(size: str, pitch_mm: float):
    s = size.strip().lower().replace(" ", "")
    m = re.fullmatch(r"m(\d+(?:\.\d+)?)(?:x(\d+(?:\.\d+)?))?", s)
    if m:
        d = float(m.group(1))
        p = pitch_mm or (float(m.group(2)) if m.group(2) else _ISO_COARSE_PITCH.get(d))
        if not p:
            raise ValueError(f"No coarse pitch on file for {size}: pass pitch_mm")
        return "metric", d, p
    m = re.fullmatch(r"(?:(\d+)/(\d+)|#(\d+)|(\d*\.\d+))-(\d+)(?:unc|unf)?", s)
    if m:
        if m.group(1):
            d_in = int(m.group(1)) / int(m.group(2))
        elif m.group(3):
            d_in = 0.060 + 0.013 * int(m.group(3))  # ASME B1.1 numbered sizes
        else:
            d_in = float(m.group(4))
        return "unified", d_in * 25.4, 25.4 / int(m.group(5))
    raise ValueError(f"Cannot read thread '{size}': use M6, M8x1 or unified with TPI such as 1/4-20, 3/8-16, #10-24")


def bolt_check(size: str, strength: str = "8.8", tensile_load_n: float = 0, shear_load_n: float = 0,
               pitch_mm: float = 0, threads_in_shear_plane: bool = True, engagement_mm: float = 0,
               tapped_yield_mpa: float = 0) -> dict:
    """Bolt capacity: tensile stress area (mm2), proof / yield / ultimate loads (N), shear, thread stripping.

    size: M6, M8x1, 1/4-20, 3/8-16, #10-24. strength: ISO property class (4.6, 4.8, 5.8, 8.8, 9.8,
    10.9, 12.9) or SAE grade (2, 5, 8). With engagement_mm and tapped_yield_mpa (the nut or tapped
    part's yield) it also checks the internal thread stripping before the bolt breaks.
    """
    try:
        system, d, p = _parse_thread(size, pitch_mm)
        key = strength.strip().lower().replace("grade", "").replace("class", "").strip()
        if key in _SAE_GRADE:
            row = next((r for r in _SAE_GRADE[key] if d / 25.4 <= r[0] + 1e-9), None)
            if row is None:
                raise ValueError(f"SAE grade {key} is not tabulated above {_SAE_GRADE[key][-1][0]} in")
            sp, rm, sy = (v * _KSI for v in row[1:])
            strength_src = f"SAE J429 grade {key} ({row[1]}/{row[2]}/{row[3]} ksi proof/tensile/yield)"
        elif key in _ISO_CLASS and ">" not in key:
            sp, rm, sy = _ISO_CLASS["8.8>16" if key == "8.8" and d > 16 else key]
            strength_src = f"ISO 898-1:2013 Table 3, property class {key}"
        else:
            raise ValueError(f"Unknown strength '{strength}': ISO classes {[k for k in _ISO_CLASS if '>' not in k]} or SAE grades {list(_SAE_GRADE)}")
    except ValueError as e:
        return _fail(e)

    if system == "metric":
        a_s = math.pi / 4 * (d - 0.9382 * p) ** 2
        area_formula = "As = pi/4 * (d - 0.9382*P)^2  (ISO 898-1, mean of pitch and minor diameters)"
    else:
        n = 25.4 / p
        a_s = 0.7854 * (d / 25.4 - 0.9743 / n) ** 2 * 25.4 ** 2
        area_formula = "At = 0.7854 * (D - 0.9743/n)^2 in^2  (ASME B1.1)"
    a_nom = math.pi / 4 * d ** 2
    a_shear = a_s if threads_in_shear_plane else a_nom
    proof, ult, yld = sp * a_s, rm * a_s, sy * a_s
    shear_cap = 0.6 * rm * a_shear
    out = {
        "ok": True,
        "nominal_diameter_mm": _r(d), "pitch_mm": _r(p),
        "tensile_stress_area_mm2": _r(a_s, 3),
        "proof_load_n": round(proof), "yield_load_n": round(yld), "ultimate_tensile_load_n": round(ult),
        "shear_capacity_n": round(shear_cap),
        "proof_stress_mpa": _r(sp, 1), "tensile_strength_mpa": _r(rm, 1), "yield_mpa": _r(sy, 1),
        "formula": f"{area_formula}; proof load = Sp*As; shear capacity = 0.6*Rm*A_shear "
                   f"(A_shear = {'As, threads in the shear plane' if threads_in_shear_plane else 'pi/4*d^2, plain shank in the shear plane'})",
        "sources": {"strength": strength_src, "stress_area": "ISO 898-1 / ASME B1.1",
                    "shear_factor_0.6": "estimate: ultimate shear ~ 0.6 x tensile for steel fasteners"},
        "inputs": {"size": size, "strength": strength, "tensile_load_n": tensile_load_n, "shear_load_n": shear_load_n,
                   "threads_in_shear_plane": threads_in_shear_plane, "engagement_mm": engagement_mm,
                   "tapped_yield_mpa": tapped_yield_mpa},
        "assumptions": ["Static load, no preload, fatigue or prying considered"],
        "warnings": [],
    }
    ft, fs = abs(tensile_load_n), abs(shear_load_n)
    if ft:
        out["tensile_stress_mpa"] = _r(ft / a_s, 2)
        out["safety_factor_proof"] = _r(proof / ft, 3)
    if fs:
        out["shear_stress_mpa"] = _r(fs / a_shear, 2)
        out["safety_factor_shear"] = _r(shear_cap / fs, 3)
    if ft and fs:
        util = (ft / proof) ** 2 + (fs / shear_cap) ** 2
        out["combined_utilisation"] = _r(util, 4)
        out["formula"] += "; combined: (Ft/proof)^2 + (Fs/shear capacity)^2 <= 1"
        if util > 1:
            out["warnings"].append("Combined tension and shear exceeds capacity")
    if engagement_mm > 0 and tapped_yield_mpa > 0:
        tau = 0.577 * tapped_yield_mpa
        strip = tau * math.pi * d * 0.875 * engagement_mm
        need = ult / (tau * math.pi * d * 0.875)
        out["thread_engagement"] = {
            "internal_thread_shear_area_mm2": _r(math.pi * d * 0.875 * engagement_mm, 2),
            "strip_load_n": round(strip),
            "engagement_for_bolt_to_break_first_mm": _r(need, 2),
            "strips_before_bolt_breaks": strip < ult,
            "safety_factor_strip": _r(strip / ft, 3) if ft else None,
            "formula": "A_strip = pi*d*0.875*Le (internal thread sheared at the bolt major diameter, ISO 68-1 "
                       "basic profile is 7/8 P wide there); strip load = 0.577*Sy_tapped*A_strip",
            "basis": "estimate: ideal profile with no tolerance allowance and von Mises shear yield; "
                     "plastics creep, so use inserts or captive nuts for repeated assembly",
        }
        if strip < ult:
            out["warnings"].append(f"Tapped thread strips at {round(strip)} N, before the bolt breaks at {round(ult)} N; "
                                   f"need {need:.1f} mm engagement")
    elif engagement_mm > 0 or tapped_yield_mpa > 0:
        out["warnings"].append("Thread engagement check needs both engagement_mm and tapped_yield_mpa")
    return out


# --- columns ------------------------------------------------------------------------------

_END_K = {"pinned-pinned": 1.0, "fixed-free": 2.0, "fixed-fixed": 0.5, "fixed-pinned": 0.699}


def buckling_check(length_mm: float, ends: str = "pinned-pinned", section: str = "rect", width_mm: float = 0,
                   height_mm: float = 0, diameter_mm: float = 0, inner_diameter_mm: float = 0,
                   load_n: float = 0, material: str = "", E_mpa: float = 0, yield_mpa: float = 0) -> dict:
    """Column buckling: Euler critical load (N), slenderness, and the Johnson value for short columns.

    ends: pinned-pinned | fixed-free | fixed-fixed | fixed-pinned. A rect section buckles about its
    thinner side automatically. Give load_n for a safety factor.
    """
    try:
        k = _END_K.get(ends.lower().replace("_", "-"))
        if k is None:
            raise ValueError(f"ends must be one of {list(_END_K)}")
        if length_mm <= 0:
            raise ValueError("length_mm must be positive")
        if section.lower().startswith("rect"):
            width_mm, height_mm = max(width_mm, height_mm), min(width_mm, height_mm)
        sec = _section(section, width_mm, height_mm, diameter_mm, inner_diameter_mm)
        mat = material_props(material, E_mpa=E_mpa, yield_mpa=yield_mpa)
        if not mat["E_mpa"]:
            raise ValueError("No Young's modulus: pass E_mpa or a material known to tb.materials")
    except (ValueError, FileNotFoundError) as e:
        return _fail(e)
    E, I, A, sy = mat["E_mpa"], sec["I_mm4"], sec["area_mm2"], mat["yield_mpa"]
    le = k * length_mm
    rg = math.sqrt(I / A)
    slender = le / rg
    euler = math.pi ** 2 * E * I / le ** 2
    out = {
        "ok": True, "euler_critical_load_n": _r(euler, 1), "effective_length_mm": _r(le, 2),
        "radius_of_gyration_mm": _r(rg), "slenderness_ratio": _r(slender, 2),
        "formula": "P_cr = pi^2*E*I/(K*L)^2; slenderness = K*L/r, r = sqrt(I/A); "
                   "Johnson (short column): P_cr = A*(Sy - (Sy*K*L/r)^2/(4*pi^2*E))",
        "inputs": {"length_mm": length_mm, "ends": ends, "K": k, "section": sec["type"], "width_mm": width_mm,
                   "height_mm": height_mm, "diameter_mm": diameter_mm, "inner_diameter_mm": inner_diameter_mm,
                   "load_n": load_n, "E_mpa": E, "yield_mpa": sy},
        "section": {kk: (_r(v) if isinstance(v, float) else v) for kk, v in sec.items()},
        "material": mat, "warnings": [],
        "assumptions": ["Perfectly straight column, centred load; real columns need a generous safety factor (3 or more)"],
    }
    governing = euler
    if sy:
        transition = math.sqrt(2 * math.pi ** 2 * E / sy)
        out["transition_slenderness"] = _r(transition, 2)
        out["squash_load_n"] = _r(sy * A, 1)
        if slender < transition:
            governing = A * (sy - (sy * slender) ** 2 / (4 * math.pi ** 2 * E))
            out["johnson_critical_load_n"] = _r(governing, 1)
            out["warnings"].append("Short column: Euler overestimates, the Johnson value governs")
    else:
        out["warnings"].append("No yield strength given: cannot tell whether the column yields before it buckles")
    out["governing_critical_load_n"] = _r(governing, 1)
    if load_n:
        out["safety_factor_buckling"] = _r(governing / abs(load_n), 3)
    return out


# --- press fit and thermal ----------------------------------------------------------------


def press_fit(shaft_diameter_mm: float, interference_mm: float, hub_outer_diameter_mm: float, length_mm: float,
              hub_E_mpa: float, shaft_E_mpa: float, hub_nu: float = 0.3, shaft_nu: float = 0.3,
              shaft_inner_diameter_mm: float = 0, friction: float = 0.15, hub_yield_mpa: float = 0) -> dict:
    """Press fit by Lame thick-cylinder theory: contact pressure (MPa), hub hoop stress, holding force (N) and torque (Nmm).

    interference_mm is diametral (shaft diameter minus hole diameter). friction is the coefficient
    you choose; 0.15 is only a placeholder for dry steel on steel.
    """
    d, do, di = shaft_diameter_mm, hub_outer_diameter_mm, shaft_inner_diameter_mm
    if not (0 <= di < d < do) or interference_mm <= 0 or length_mm <= 0 or hub_E_mpa <= 0 or shaft_E_mpa <= 0:
        return {"ok": False, "error": "Need shaft_inner < shaft_diameter < hub_outer, and positive interference, length and moduli"}
    hub_term = (do ** 2 + d ** 2) / (do ** 2 - d ** 2) + hub_nu
    shaft_term = (d ** 2 + di ** 2) / (d ** 2 - di ** 2) - shaft_nu
    p = interference_mm / (d * (hub_term / hub_E_mpa + shaft_term / shaft_E_mpa))
    hoop = p * (do ** 2 + d ** 2) / (do ** 2 - d ** 2)
    vm = p * math.sqrt(3 * do ** 4 + d ** 4) / (do ** 2 - d ** 2)
    force = friction * p * math.pi * d * length_mm
    return {
        "ok": True, "contact_pressure_mpa": _r(p, 3), "hub_hoop_stress_mpa": _r(hoop, 3),
        "hub_von_mises_mpa": _r(vm, 3),
        "safety_factor_hub_yield": _r(hub_yield_mpa / vm, 3) if hub_yield_mpa else None,
        "holding_force_n": _r(force, 1), "holding_torque_nmm": _r(force * d / 2, 1),
        "formula": "p = delta / ( d * [ ((do^2+d^2)/(do^2-d^2) + nu_h)/E_h + ((d^2+di^2)/(d^2-di^2) - nu_s)/E_s ] ); "
                   "hoop at bore = p*(do^2+d^2)/(do^2-d^2); von Mises at bore = p*sqrt(3*do^4+d^4)/(do^2-d^2); "
                   "F = mu*p*pi*d*L; T = F*d/2",
        "inputs": {"shaft_diameter_mm": d, "interference_mm": interference_mm, "hub_outer_diameter_mm": do,
                   "length_mm": length_mm, "hub_E_mpa": hub_E_mpa, "shaft_E_mpa": shaft_E_mpa, "hub_nu": hub_nu,
                   "shaft_nu": shaft_nu, "shaft_inner_diameter_mm": di, "friction": friction, "hub_yield_mpa": hub_yield_mpa},
        "assumptions": ["Elastic, smooth surfaces, equal lengths, no creep (plastic hubs relax over time)",
                        "friction coefficient is the caller's input, not a measured value"],
    }


def thermal_expansion(length_mm: float, delta_t_c: float, cte_um_m_c: float, E_mpa: float = 0,
                      other_cte_um_m_c: float = 0) -> dict:
    """Thermal growth (mm) of a length for a temperature change, and the stress (MPa) if it is fully restrained.

    cte_um_m_c is the linear expansion coefficient in um/(m.C) (= 1e-6 /C). Give other_cte_um_m_c
    to get the differential growth against a mating part of the same length.
    """
    if length_mm <= 0 or cte_um_m_c <= 0:
        return {"ok": False, "error": "length_mm and cte_um_m_c must be positive; the coefficient is not looked up for you"}
    a = cte_um_m_c * 1e-6
    out = {
        "ok": True, "growth_mm": _r(a * length_mm * delta_t_c, 5), "strain": _r(a * delta_t_c, 6),
        "formula": "dL = alpha*L*dT; restrained stress = E*alpha*dT; differential = (alpha1-alpha2)*L*dT",
        "inputs": {"length_mm": length_mm, "delta_t_c": delta_t_c, "cte_um_m_c": cte_um_m_c, "E_mpa": E_mpa,
                   "other_cte_um_m_c": other_cte_um_m_c},
    }
    if E_mpa > 0:
        out["restrained_stress_mpa"] = _r(E_mpa * a * delta_t_c, 3)
    if other_cte_um_m_c > 0:
        out["differential_growth_mm"] = _r((cte_um_m_c - other_cte_um_m_c) * 1e-6 * length_mm * delta_t_c, 5)
    return out


# --- mass and centre of gravity -----------------------------------------------------------


def mass_properties(project: str, densities_g_cm3: dict[str, float] | None = None, infill_fraction: float = 1.0) -> dict:
    """Combined mass (g) and centre of gravity (mm, model coordinates) of a project's non-reference parts.

    Reads out/build.json. Density comes from tb.materials per part material, or from
    densities_g_cm3, e.g. {"petg": 1.27}. infill_fraction scales printed parts crudely (1.0 = solid).
    Returns a per-part breakdown.
    """
    try:
        d = project_dir(project)
    except (ValueError, FileNotFoundError) as e:
        return _fail(e)
    build = load_json(d / "out" / "build.json")
    if not build or not build.get("parts"):
        return {"ok": False, "error": f"No out/build.json for '{project}': run cad_build first"}
    if not 0 < infill_fraction <= 1:
        return {"ok": False, "error": "infill_fraction must be in (0, 1]"}
    overrides = {k.lower(): v for k, v in (densities_g_cm3 or {}).items()}
    rows, missing, notes, skipped = [], [], [], []
    for name, p in build["parts"].items():
        if p.get("reference"):
            skipped.append(name)
            continue
        mat = (p.get("material") or "").lower()
        props = material_props(mat, density_g_cm3=overrides.get(mat, 0))
        rho = props["density_g_cm3"]
        if not rho:
            missing.append(f"{name} ({mat or 'no material'})")
            continue
        qty = int(p.get("qty", 1))
        mass = p["volume_mm3"] / 1000 * rho * infill_fraction
        rows.append({"part": name, "material": mat, "density_g_cm3": rho, "density_source": props["sources"]["density_g_cm3"],
                     "volume_mm3": p["volume_mm3"], "qty": qty, "mass_each_g": round(mass, 2),
                     "mass_total_g": round(mass * qty, 2), "centre_of_mass_mm": p["centre_of_mass"]})
        if qty > 1:
            notes.append(f"{name}: qty {qty} counted at the single modelled position")
    if missing:
        return {"ok": False, "error": f"No density for: {', '.join(missing)}. Pass densities_g_cm3={{'<material>': <g/cm3>}} "
                                      "or add the material to tb.materials", "parts_with_density": rows}
    total = sum(r["mass_total_g"] for r in rows)
    cog = [round(sum(r["mass_total_g"] * r["centre_of_mass_mm"][i] for r in rows) / total, 3) for i in range(3)]
    return {
        "ok": True, "mass_g": round(total, 2), "weight_n": round(total / 1000 * G_MM_S2 / 1000, 4),
        "centre_of_gravity_mm": cog, "parts": rows, "reference_parts_excluded": skipped,
        "formula": "mass = volume * density * infill_fraction; CoG = sum(m_i * r_i) / sum(m_i); weight = m * 9.80665",
        "inputs": {"project": project, "densities_g_cm3": densities_g_cm3, "infill_fraction": infill_fraction},
        "assumptions": ["Homogeneous parts; fasteners, inserts and reference (bought) parts are not included"]
                       + (["infill_fraction applied uniformly, walls and skins ignored"] if infill_fraction < 1 else []) + notes,
    }


TOOLS = (beam_check, bolt_check, buckling_check, press_fit, thermal_expansion, mass_properties)


def register(mcp) -> None:
    for fn in TOOLS:
        mcp.tool()(fn)
