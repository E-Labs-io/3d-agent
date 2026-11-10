"""Bill of materials generated from the model, with supplier links and order tracking."""
from __future__ import annotations

import csv
import datetime as dt
import io

from .common import load_json, project_dir, save_json

STATUSES = ["needed", "ordered", "received", "in stock", "printed"]


def _material(name: str) -> dict:
    try:
        from .materials import get_material
        return get_material(name) or {}
    except Exception:  # noqa: BLE001 - materials module is optional
        return {}


def _links(query: str) -> dict:
    try:
        from .sourcing import sourcing_links
        r = sourcing_links(query)
        return r.get("links", {}) if r.get("ok") else {}
    except Exception:  # noqa: BLE001 - sourcing module is optional
        return {}


def _lines(project: str, infill_pct: float, filament_price_per_kg: float | None) -> tuple[list[dict], list[str]]:
    d = project_dir(project)
    build = load_json(d / "out" / "build.json")
    if not build:
        raise FileNotFoundError(f"Project '{project}' has not been built. Run cad_build first.")
    status = load_json(d / "bom-status.json", {}) or {}
    notes, lines = [], []

    # Use the print estimator for made-part mass when it is available: it accounts for
    # shells, infill and supports. The volume-and-infill figure below is the fallback.
    estimate, basis = {}, "volume x density x infill"
    try:
        from .make import print_estimate
        est = print_estimate(project, profile={"infill_fraction": infill_pct / 100})
        if est.get("ok"):
            estimate = {n: v.get("filament_g") for n, v in est.get("parts", {}).items()}
            basis = f"print estimate ({est.get('route', 'estimate')})"
    except Exception:  # noqa: BLE001 - make module is optional
        pass
    notes.append(f"Made-part mass basis: {basis}.")

    for name, p in build["parts"].items():
        if p["reference"]:
            if p["process"] == "bought":
                lines.append({"id": f"ref:{name}", "kind": "bought", "name": name, "qty": p["qty"],
                              "spec": p.get("note", ""), "links": _links(p.get("note") or name)})
            continue
        mat = _material(p["material"])
        rho = mat.get("density_g_cm3")
        price = filament_price_per_kg or mat.get("price_per_kg_gbp")
        # shell + infill estimate; the slicer gives the real figure
        fill = 0.25 + 0.75 * infill_pct / 100
        mass = estimate.get(name) or (round(p["volume_mm3"] / 1000 * rho * fill, 1) if rho else None)
        line = {"id": f"part:{name}", "kind": "made", "name": name, "qty": p["qty"],
                "spec": f"{p['material'].upper()} / {p['process'].upper()}, {p['bbox_mm'][0]:g} x {p['bbox_mm'][1]:g} x {p['bbox_mm'][2]:g} mm",
                "mass_g_each": mass, "files": p["files"].get("step")}
        if mass and price:
            line["unit_price"] = round(mass / 1000 * price, 2)
            line["currency"] = "GBP"
        if not rho:
            notes.append(f"No density for material '{p['material']}', so no mass for {name}.")
        lines.append(line)

    for i, h in enumerate(build.get("hardware", []), start=1):
        line = {"id": f"hw:{i}:{h['name']}", "kind": "hardware", "name": h["name"], "qty": h.get("qty", 1),
                "spec": h.get("spec", ""), "mpn": h.get("mpn", ""), "supplier": h.get("supplier", ""),
                "use": h.get("use", "")}
        if h.get("url"):
            line["url"] = h["url"]
        if h.get("unit_price") is not None:
            line["unit_price"], line["currency"] = h["unit_price"], h.get("currency", "GBP")
        line["links"] = _links(h.get("mpn") or h["name"])
        lines.append(line)

    # electronics: one line per distinct value/footprint/part number, refs grouped
    circuit = load_json(d / "out" / "electronics" / "circuit.json", {}) or {}
    grouped: dict[tuple, dict] = {}
    for e in circuit.get("parts", []):
        fields = {k.lower(): v for k, v in (e.get("fields") or {}).items()}
        mpn = fields.get("mpn") or fields.get("manufacturer part number") or ""
        key = (e.get("value", ""), e.get("footprint", ""), mpn)
        g = grouped.setdefault(key, {"refs": [], "mpn": mpn, "desc": e.get("description", "")})
        g["refs"].append(e.get("ref", "?"))
    for (value, footprint, mpn), g in grouped.items():
        lines.append({"id": f"el:{g['refs'][0]}", "kind": "electronic", "name": value or g["desc"] or g["refs"][0],
                      "qty": len(g["refs"]), "spec": footprint, "mpn": mpn, "use": ", ".join(g["refs"]),
                      "links": _links(mpn or value)})

    for n, line in enumerate(lines, start=1):
        line["item"] = n
        st = status.get(line["id"], {})
        line["status"] = st.get("status", "needed")
        if st.get("note"):
            line["status_note"] = st["note"]
        if "unit_price" in line:
            line["line_total"] = round(line["unit_price"] * line["qty"], 2)
    if not any(l.get("links") for l in lines):
        notes.append("No supplier links: sourcing module not available.")
    return lines, notes


def bom_make(project: str, infill_pct: float = 30.0, filament_price_per_kg: float = 0.0) -> dict:
    """Generate the bill of materials from the built model: made parts, bought items, hardware, electronics.

    Made-part mass (g) is estimated from volume, material density and infill; prices in GBP where known.
    Writes bom.json, bom.csv and bom.md to out/bom/. Unpriced lines are listed, not guessed.
    """
    try:
        lines, notes = _lines(project, infill_pct, filament_price_per_kg or None)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    d = project_dir(project)
    out = d / "out" / "bom"
    out.mkdir(parents=True, exist_ok=True)
    priced = [l for l in lines if "line_total" in l]
    total = round(sum(l["line_total"] for l in priced), 2)
    summary = {"lines": len(lines), "priced_lines": len(priced), "known_total_gbp": total,
               "unpriced": [l["name"] for l in lines if "line_total" not in l]}
    save_json(out / "bom.json", {"project": project, "generated": dt.date.today().isoformat(),
                                 "summary": summary, "lines": lines, "notes": notes})

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["item", "kind", "name", "qty", "spec", "mpn", "unit_price", "line_total", "status", "link"])
    for l in lines:
        link = l.get("url") or next(iter(l.get("links", {}).values()), "")
        w.writerow([l["item"], l["kind"], l["name"], l["qty"], l.get("spec", ""), l.get("mpn", ""),
                    l.get("unit_price", ""), l.get("line_total", ""), l["status"], link])
    (out / "bom.csv").write_text(buf.getvalue())

    md = [f"# Bill of materials: {project}", "", f"Generated {dt.date.today().isoformat()} from the built model.", "",
          "| # | Kind | Item | Qty | Spec | Unit £ | Total £ | Status | Find it |", "|--:|---|---|--:|---|--:|--:|---|---|"]
    for l in lines:
        links = dict(l.get("links", {}))
        if l.get("url"):
            links = {"supplier": l["url"], **links}
        find = " · ".join(f"[{k}]({v})" for k, v in list(links.items())[:4])
        md.append(f"| {l['item']} | {l['kind']} | {l['name']} | {l['qty']} | {l.get('spec', '')} | "
                  f"{l.get('unit_price', '')} | {l.get('line_total', '')} | {l['status']} | {find} |")
    md += ["", f"**Known total: £{total:.2f}** across {len(priced)} of {len(lines)} lines."]
    if summary["unpriced"]:
        md.append(f"Not priced: {', '.join(summary['unpriced'])}.")
    md += [""] + [f"- {n}" for n in notes]
    (out / "bom.md").write_text("\n".join(md) + "\n")
    return {"ok": True, "summary": summary, "lines": lines, "notes": notes,
            "files": {"json": "out/bom/bom.json", "csv": "out/bom/bom.csv", "md": "out/bom/bom.md"}}


def bom_set_status(project: str, item_id: str, status: str, note: str = "") -> dict:
    """Track one BOM line: status is needed, ordered, received, in stock or printed. item_id is the line's 'id'."""
    if status not in STATUSES:
        return {"ok": False, "error": f"status must be one of {STATUSES}"}
    try:
        d = project_dir(project)
        lines, _ = _lines(project, 30.0, None)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}
    if item_id not in {l["id"] for l in lines}:
        return {"ok": False, "error": f"No BOM line '{item_id}'. Ids: {[l['id'] for l in lines]}"}
    state = load_json(d / "bom-status.json", {}) or {}
    state[item_id] = {"status": status, "note": note, "updated": dt.date.today().isoformat()}
    save_json(d / "bom-status.json", state)
    return {"ok": True, "item_id": item_id, "status": status}


def register(mcp) -> None:
    mcp.tool()(bom_make)
    mcp.tool()(bom_set_status)
