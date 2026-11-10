"""Standard parts: fastener, insert and bearing dimensions (bd_warehouse), ISO 286 fits, unified inch threads."""
from __future__ import annotations

import re
from fractions import Fraction
from functools import lru_cache

from .common import DATA, load_json

UTS_FILE = DATA / "standards" / "unified_threads.json"
BDW_URL = "https://github.com/gumyr/bd_warehouse"
ISOFITS_URL = "https://github.com/pgreene16/isofits"
IN = 25.4

# ISO drawing symbols used as column names in the bd_warehouse tables. 's' depends on the part.
LEGEND = {
    "dk": "head diameter", "k": "head height", "s": "width across flats (hex head, nut) or hex socket size (socket screws); outer diameter for heat-set inserts",
    "t": "socket or recess depth", "m": "nut thickness; insert length for heat-set inserts", "d1": "washer inner diameter",
    "d2": "washer outer diameter", "h": "washer thickness", "short": "shortest standard length", "long": "longest standard length",
    "d": "bearing bore", "D": "bearing outer diameter", "B": "bearing width", "T": "tapered bearing total width",
    "drill": "drill size for the insert hole", "Designation": "bearing designation",
}
COUNTS = {"knurls"}  # numeric columns that are not lengths
TEXT = {"Designation", "part", "drill"}  # never parsed as numbers


def _snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


@lru_cache(maxsize=1)
def _catalogue() -> dict:
    """kind -> {cls, group, data}, discovered from bd_warehouse's own class tree."""
    from bd_warehouse import bearing, fastener

    cat = {}
    for group, base in (("screw", fastener.Screw), ("nut", fastener.Nut), ("washer", fastener.Washer),
                        ("bearing", bearing.Bearing)):
        for cls in _subclasses(base):
            data = cls.__dict__.get("fastener_data") or cls.__dict__.get("bearing_data")
            if data:
                cat[_snake(cls.__name__)] = {"cls": cls, "group": group, "data": data}
    return cat


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("bd_warehouse")
    except Exception:  # noqa: BLE001
        return "unknown"


def _source(standard: str) -> str:
    return f"bd_warehouse {_version()} parameter tables, type '{standard}' ({BDW_URL})"


def _unavailable(e: Exception) -> dict:
    return {"ok": False, "error": f"bd_warehouse could not be loaded: {type(e).__name__}: {e}",
            "install": "uv add bd_warehouse==0.4.0"}


def _resolve_kind(kind: str, cat: dict) -> tuple[str | None, list[str]]:
    k = _norm(kind)
    exact = [name for name in cat if _norm(name) == k]
    if exact:
        return exact[0], []
    partial = [name for name in cat if k and (k in _norm(name) or _norm(name) in k)]
    return (partial[0], []) if len(partial) == 1 else (None, partial or sorted(cat))


def _standards(entry: dict) -> list[str]:
    return sorted(entry["cls"].types())


def _sizes(entry: dict, standard: str) -> list[str]:
    return [size for size, row in entry["data"].items()
            if any(col.strip().split(":")[0] == standard and val != "" for col, val in row.items())]


def _size_key(s: str) -> str:
    return re.sub(r"[\s\"″]+", "", str(s).lower()).replace("x", "-")


def _resolve_size(size: str, sizes: list[str]) -> tuple[str | None, list[str]]:
    want = _size_key(size)
    exact = [s for s in sizes if _size_key(s) == want]
    if exact:
        return exact[0], []
    head = [s for s in sizes if _size_key(s.split("-")[0]) == want]  # "M3" -> "M3-0.5"
    if len(head) == 1:
        return head[0], []
    return None, head or [s for s in sizes if want and _size_key(s).startswith(want)]


def _designation(text) -> str:
    """Bearing designation without the catalogue's leading '*' marker."""
    return str(text).replace("*", "").strip().lower()


def _number(text: str) -> float | None:
    t = text.strip()
    if not re.fullmatch(r"[0-9./ ]+", t) or not re.search(r"\d", t):
        return None
    try:
        return float(sum(Fraction(p) for p in t.split()))
    except (ValueError, ZeroDivisionError):
        return None


def _row(entry: dict, standard: str, size: str) -> tuple[dict, dict]:
    """Split one table row into lengths in mm and everything else."""
    scale = 1.0 if size.startswith("M") else IN
    dims, other = {}, {}
    for col, val in entry["data"][size].items():
        std, key = col.strip().split(":")
        if std != standard or val == "":
            continue
        n = None if key in TEXT else _number(val)
        if n is None or key in COUNTS or (entry["group"] == "bearing" and key not in ("d", "D", "B", "T", "d1", "D1", "D2", "da", "Da")):
            other[key] = n if n is not None else val.strip()
        else:
            dims[f"{key}_mm"] = round(n * scale, 4)
    return dims, other


def _holes(entry: dict, size: str) -> dict:
    """Clearance and tap drill diameters (mm) from bd_warehouse's hole tables, where the size is listed."""
    cls, out = entry["cls"], {}
    if size.count("-") > 1:  # heat-set style "M3-0.5-Standard"
        size = "-".join(size.split("-")[:2])
    clear = getattr(cls, "clearance_hole_data", {}).get(size.split("-")[0])
    if clear and entry["group"] != "bearing":
        out["clearance_hole_mm"] = {k.lower(): round(v, 3) for k, v in clear.items()}
    tap = getattr(cls, "tap_hole_data", {}).get(size)
    if tap:
        out["tap_hole_mm"] = {("soft_material" if k == "Soft" else "hard_material"): round(v, 3) for k, v in tap.items()}
    return out


def standards_kinds() -> dict:
    """List every standard part kind bd_warehouse knows, with the standards (or makers) covering each.

    Groups: screw, nut (includes heat_set_nut inserts), washer, bearing. Use the kind and standard
    names returned here in fastener_sizes and fastener_dims.
    """
    try:
        cat = _catalogue()
    except Exception as e:  # noqa: BLE001
        return _unavailable(e)
    kinds = [{"kind": name, "group": e["group"], "standards": _standards(e), "sizes": len(e["data"])}
             for name, e in sorted(cat.items(), key=lambda kv: (kv[1]["group"], kv[0]))]
    return {"ok": True, "kinds": kinds, "source": f"bd_warehouse {_version()} ({BDW_URL})",
            "also": ["unified_thread (inch UNC/UNF/UNEF)", "fit_limits (ISO 286)"]}


def fastener_sizes(kind: str, standard: str = "") -> dict:
    """Sizes available for a part kind, per standard. kind e.g. socket_head_cap_screw, hex_nut, plain_washer.

    standard e.g. iso4762, iso4032; "" lists every standard for the kind. Sizes read "M3-0.5" or "1/4-20".
    """
    try:
        cat = _catalogue()
    except Exception as e:  # noqa: BLE001
        return _unavailable(e)
    name, options = _resolve_kind(kind, cat)
    if name is None:
        return {"ok": False, "error": f"Unknown or ambiguous kind '{kind}'.", "kinds": options}
    entry = cat[name]
    stds = _standards(entry)
    if standard:
        match = [s for s in stds if _norm(s) == _norm(standard)]
        if not match:
            return {"ok": False, "error": f"'{name}' has no standard '{standard}'.", "standards": stds}
        stds = match
    return {"ok": True, "kind": name, "group": entry["group"], "sizes": {s: _sizes(entry, s) for s in stds},
            "source": f"bd_warehouse {_version()} ({BDW_URL})"}


def fastener_dims(kind: str, size: str, standard: str = "") -> dict:
    """Dimensions (mm) of one standard part: head or nut dimensions, clearance and tap hole diameters.

    kind from standards_kinds, size like "M3" or "M3-0.5" or "1/4-20", standard like iso4762 ("" works
    when only one standard lists that size). Inch tables are converted to mm. Column names are ISO
    drawing symbols explained in 'legend'. Works for bearings and heat-set inserts too.
    """
    try:
        cat = _catalogue()
    except Exception as e:  # noqa: BLE001
        return _unavailable(e)
    name, options = _resolve_kind(kind, cat)
    if name is None:
        return {"ok": False, "error": f"Unknown or ambiguous kind '{kind}'.", "kinds": options}
    entry = cat[name]
    stds = _standards(entry)
    if standard:
        stds = [s for s in stds if _norm(s) == _norm(standard)]
        if not stds:
            return {"ok": False, "error": f"'{name}' has no standard '{standard}'.", "standards": _standards(entry)}
    found = {}
    for s in stds:
        hit, near = _resolve_size(size, _sizes(entry, s))
        if hit:
            found[s] = hit
        elif near:
            found.setdefault("_near", {})[s] = near[:12]
    near = found.pop("_near", {})
    if not found:
        return {"ok": False, "error": f"No {name} of size '{size}'" + (f" in {standard}" if standard else "") + ".",
                "similar_sizes": near or {s: _sizes(entry, s) for s in stds}}
    if len(found) > 1:
        return {"ok": False, "error": f"Size '{size}' is in several standards; pass one as 'standard'.",
                "standards": found}
    std, hit = next(iter(found.items()))
    dims, other = _row(entry, std, hit)
    out = {"ok": True, "kind": name, "group": entry["group"], "standard": std, "size": hit, "dims_mm": dims}
    if other:
        out["other"] = other
    if name == "heat_set_nut" and "drill" in other:
        from bd_warehouse.fastener import read_drill_sizes

        dia = read_drill_sizes().get(str(other["drill"]).strip())
        if dia:
            out["insert_hole_diameter_mm"] = round(dia, 3)
    if name != "heat_set_nut":
        out.update(_holes(entry, hit))
    keys = [k[:-3] for k in dims] + list(other)
    out["legend"] = {k: LEGEND[k] for k in keys if k in LEGEND}
    out["source"] = _source(std)
    return out


def insert_dims(size: str = "", maker: str = "") -> dict:
    """Heat-set threaded insert dimensions (mm) and the hole diameter to model for them.

    size like "M3" or "M3-0.5-5.7"; maker e.g. CNCKitchen, ruthex, McMaster-Carr. With no size, lists the
    sizes each maker offers. An "M3" with several lengths returns the options to choose from.
    """
    if not size:
        return fastener_sizes("heat_set_nut", maker)
    return fastener_dims("heat_set_nut", size, maker)


def bearing_dims(designation: str, kind: str = "") -> dict:
    """Bearing dimensions (mm) by designation ("608", "6204-2RS") or size ("M8-22-7" = bore-OD-width).

    Returns bore d, outer diameter D, width B, load ratings (kN) and limiting speeds (rpm) where listed.
    kind narrows the search, e.g. single_row_deep_groove_ball_bearing.
    """
    try:
        cat = _catalogue()
    except Exception as e:  # noqa: BLE001
        return _unavailable(e)
    kinds = {n: e for n, e in cat.items() if e["group"] == "bearing"}
    if kind:
        name, options = _resolve_kind(kind, kinds)
        if name is None:
            return {"ok": False, "error": f"Unknown bearing kind '{kind}'.", "kinds": options or sorted(kinds)}
        kinds = {name: kinds[name]}
    want, hits = str(designation).strip().lower(), []
    for name, entry in kinds.items():
        for std in _standards(entry):
            for size in _sizes(entry, std):
                dims, other = _row(entry, std, size)
                desig = _designation(other.get("Designation", ""))
                if want in (size.lower(), desig) or desig.startswith(want + "-"):
                    hits.append({"kind": name, "standard": std, "size": size, "dims_mm": dims, "other": other,
                                 "source": _source(std)})
    if not hits:
        return {"ok": False, "error": f"No bearing '{designation}'. Use fastener_sizes on a bearing kind to list sizes.",
                "kinds": sorted(kinds)}
    return {"ok": True, "bearings": hits, "legend": {k: LEGEND[k] for k in ("d", "D", "B", "T")},
            "units": "dims mm; C, C0, Pu in kN; speeds in rpm; mass in kg (bd_warehouse 'SKT' column names)"}


def _isofits():
    # isofits installs flat modules (isofits, data, module); import late so a clash only breaks this tool.
    import isofits

    return isofits


def fit_limits(nominal_mm: float, hole: str = "H7", shaft: str = "g6") -> dict:
    """ISO 286 hole/shaft fit: limit sizes (mm) and minimum/maximum clearance (mm) for a nominal diameter.

    nominal_mm over 3 up to 400. hole like "H7" (capital), shaft like "g6" (lower case). Negative
    clearance is interference. Deviations are returned in micrometres.
    """
    try:
        iso = _isofits()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"isofits could not be loaded: {type(e).__name__}: {e}",
                "install": "uv add isofits"}
    try:
        size = float(nominal_mm)
        if not 3 < size <= 400:
            raise ValueError("nominal_mm must be over 3 and at most 400 (the range isofits tabulates)")
        es_hole, ei_hole = iso.isotol("hole", size, hole, "both")
        es_shaft, ei_shaft = iso.isotol("shaft", size, shaft, "both")
    except Exception as e:  # noqa: BLE001 - isofits raises bare strings and ValueErrors
        from data import hole_data, shaft_data

        return {"ok": False, "error": str(e), "hole_classes": list(hole_data)[2:], "shaft_classes": list(shaft_data)[2:]}
    cmin, cmax = (ei_hole - es_shaft) / 1000, (es_hole - ei_shaft) / 1000
    kind = "clearance" if cmin >= 0 else "interference" if cmax <= 0 else "transition"
    r = lambda v: round(v, 4)  # noqa: E731
    return {"ok": True, "nominal_mm": size, "fit": f"{hole}/{shaft}", "fit_type": kind,
            "hole": {"upper_deviation_um": es_hole, "lower_deviation_um": ei_hole,
                     "max_mm": r(size + es_hole / 1000), "min_mm": r(size + ei_hole / 1000)},
            "shaft": {"upper_deviation_um": es_shaft, "lower_deviation_um": ei_shaft,
                      "max_mm": r(size + es_shaft / 1000), "min_mm": r(size + ei_shaft / 1000)},
            "min_clearance_mm": r(cmin), "max_clearance_mm": r(cmax),
            "source": f"isofits 1.0 tables of ISO 286 limit deviations ({ISOFITS_URL})"}


@lru_cache(maxsize=1)
def _uts() -> dict:
    return load_json(UTS_FILE, {}) or {}


def _uts_size(text: str) -> tuple[str, int | None]:
    t = str(text).upper().replace('"', "").replace("″", "").replace("IN", "")
    t = re.sub(r"\b(UNC|UNF|UNEF)\b", "", t).strip()
    m = re.fullmatch(r"(#?\d+(?:/\d+)?)\s*(?:-\s*(\d+))?", t)
    return (m[1], int(m[2]) if m[2] else None) if m else ("", None)


def unified_thread(size: str) -> dict:
    """Unified inch thread data: major diameter, TPI, pitch, tap drill, clearance holes, hex nut size (mm and inch).

    size like "1/4-20", "3/8-16", "#10-32", or just "1/4" for every series (UNC, UNF, UNEF). Covers #0 to 1 in.
    Hex nut across-flats and thickness are ASME B18.2.2 for 1/4 in and up.
    """
    doc = _uts()
    if not doc:
        return {"ok": False, "error": f"Missing data file {UTS_FILE}"}
    nominal, tpi = _uts_size(size)
    rec = next((t for t in doc["threads"] if t["size"] == nominal), None)
    if rec is None:
        return {"ok": False, "error": f"No unified thread '{size}'. Write it like 1/4-20 or #10-32.",
                "sizes": [t["size"] for t in doc["threads"]]}
    series = {k: v for k, v in rec["series"].items() if tpi is None or v["tpi"] == tpi}
    if not series:
        return {"ok": False, "error": f"{nominal} has no {tpi} TPI standard series.",
                "series": {k: v["designation"] for k, v in rec["series"].items()}}
    out = {"ok": True, "size": nominal, "major_diameter_in": rec["major_diameter_in"],
           "major_diameter_mm": rec["major_diameter_mm"], "series": series, "source": rec["source"]}
    if "hex_nut" in rec:
        out["hex_nut"] = rec["hex_nut"]
    try:
        from bd_warehouse.fastener import Screw

        clear = Screw.clearance_hole_data.get(nominal)
        if clear:
            out["clearance_hole_mm"] = {k.lower(): round(v, 3) for k, v in clear.items()}
            out["clearance_hole_source"] = f"bd_warehouse {_version()} clearance_hole_sizes.csv ({BDW_URL})"
    except Exception:  # noqa: BLE001 - the thread table stands on its own
        pass
    return out


@lru_cache(maxsize=1)
def _index() -> list[dict]:
    rows = []
    try:
        for name, entry in _catalogue().items():
            for std in _standards(entry):
                for size in _sizes(entry, std):
                    extra = entry["data"][size].get(f"{std}:Designation", "")
                    rows.append({"type": entry["group"], "kind": name, "standard": std, "size": size,
                                 "tokens": [size.lower(), _designation(extra)],
                                 "text": _norm(f"{name} {std} {entry['group']}"),
                                 "lookup": f'fastener_dims("{name}", "{size}", "{std}")'})
    except Exception:  # noqa: BLE001 - search still covers the local tables
        pass
    for t in _uts().get("threads", []):
        for s in t["series"].values():
            rows.append({"type": "unified_thread", "size": s["designation"],
                         "tokens": [f"{t['size']}-{s['tpi']}"],
                         "text": _norm(f"unified thread inch {s['designation'].split()[-1]}"),
                         "lookup": f'unified_thread("{t["size"]}-{s["tpi"]}")'})
    try:
        _isofits()
        from data import hole_data, shaft_data

        for body, table in (("hole", hole_data), ("shaft", shaft_data)):
            for cls in list(table)[2:]:
                # Case matters for fit classes (H7 is a hole, h7 a shaft), so keep it out of the folded text.
                rows.append({"type": "iso_fit", "size": cls, "body": body, "tokens": [cls], "case": True,
                             "text": _norm(f"iso 286 fit tolerance {body}"), "lookup": "fit_limits(nominal_mm, hole, shaft)"})
    except Exception:  # noqa: BLE001
        pass
    return rows


def _word_matches(word: str, row: dict) -> bool:
    """Size-like words must equal a size token or its thread prefix ("M3" matches "m3-0.5", not "m30-3.5")."""
    if row.get("case"):  # fit classes: H7 is a hole, h7 a shaft
        return word in row["tokens"] or (word.isalpha() and _norm(word) in row["text"])
    w = _size_key(word)
    if any(t == w or t.startswith(w + "-") for t in row["tokens"] if t):
        return True
    sizeish = bool(re.match(r"^(m\d|#\d|\d)", w))
    return not sizeish and _norm(word) != "" and _norm(word) in row["text"]


def standards_search(query: str, limit: int = 40) -> dict:
    """Search all standard parts, inch threads and ISO fit classes. Returns matches and the lookup call for each.

    Every word of the query must match: "M3 socket", "608", "1/4-20", "heat set M4", "H7". Fit classes
    are case-sensitive (H7 hole, h7 shaft).
    """
    words = [w for w in re.split(r"\s+", str(query).strip()) if w]
    if not words:
        return {"ok": False, "error": "Empty query. Try 'M3 socket', '608', '1/4-20' or 'H7'."}
    hits = []
    for row in _index():
        if all(_word_matches(w, row) for w in words):
            hits.append({k: v for k, v in row.items() if k not in ("text", "tokens", "case")})
    if not hits:
        return {"ok": False, "error": f"Nothing matches '{query}'. standards_kinds lists what is covered."}
    return {"ok": True, "count": len(hits), "truncated": len(hits) > limit, "results": hits[:limit]}


def register(mcp) -> None:
    for fn in (standards_kinds, fastener_sizes, fastener_dims, insert_dims, bearing_dims, fit_limits,
               unified_thread, standards_search):
        mcp.tool()(fn)
