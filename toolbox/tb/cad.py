"""Geometry tools: create a project, build its model, push it to the viewer."""
from __future__ import annotations

import json
import subprocess
import sys

from .common import HOME, PROJECTS, SCENE_FILE, TOOLBOX, inside, load_json, project_dir, save_json

MODEL_TEMPLATE = '''"""{title}

Units are millimetres, Z is up. Shapes sit in their assembled position.
Rebuild with the cad_build tool after every edit.
"""
from build123d import *
from tb.model import part

body = Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))

PARTS = {{
    "body": part(body, material="petg", color="#3a3f4a"),
}}
'''


def _write_scene(slug: str, title: str, parts: dict) -> None:
    """Point the live viewer at the freshly built meshes."""
    span = max((max(p["bbox_mm"]) for p in parts.values()), default=100)
    objects = []
    for name, p in parts.items():
        obj = {
            "id": name, "name": name, "type": "file", "format": "stl",
            "url": f"/projects/{slug}/{p['files']['view']}", "autoCenter": False,
            "material": {"type": "standard", "color": p["color"], "metalness": 0.05, "roughness": 0.7},
            "transform": {"position": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]},
            "visible": True, "castShadow": not p["reference"], "receiveShadow": True,
        }
        if p["opacity"] < 1:
            obj["material"].update(transparent=True, opacity=p["opacity"], depthWrite=False)
        if p["reference"]:
            obj["_reference"] = True
        else:
            obj["_printPart"] = name
            if p["print_flip"]:
                obj["_printFlip"] = True
        objects.append(obj)
    prev = load_json(SCENE_FILE, {}) or {}
    scene = {
        "metadata": {"version": "1.0", "name": title, "units": "mm", "project": slug, "source": "toolbox"},
        "environment": prev.get("environment") or {"background": "#12161f", "grid": True, "axes": False, "shadows": True,
                                                    "gridSize": 300, "gridDivisions": 30},
        "camera": {"position": [span * 2.0, span * 1.5, span * 2.4], "target": [0, span * 0.15, 0], "fov": 42},
        "lights": prev.get("lights") or [
            {"id": "ambient", "type": "ambient", "color": "#c8d4ff", "intensity": 0.45},
            {"id": "key", "type": "directional", "color": "#ffffff", "intensity": 1.35, "position": [190, 270, 170], "castShadow": True},
            {"id": "fill", "type": "directional", "color": "#88a0ff", "intensity": 0.42, "position": [-170, 120, -140]},
        ],
        "objects": objects,
    }
    save_json(SCENE_FILE, scene)


def project_new(slug: str, title: str = "") -> dict:
    """Create projects/<slug>/ with a starter model.py. Fails if it already exists."""
    d = project_dir(slug, create=True)
    model = d / "model.py"
    if model.exists():
        return {"ok": False, "error": f"Project '{slug}' already exists", "model": str(model)}
    model.write_text(MODEL_TEMPLATE.format(title=title or slug))
    save_json(d / "project.json", {"slug": slug, "title": title or slug})
    return {"ok": True, "project": slug, "model": str(model)}


def project_list() -> dict:
    """List projects and whether each has been built."""
    rows = []
    for d in sorted(PROJECTS.glob("*")):
        if (d / "model.py").exists():
            rows.append({"slug": d.name, "built": (d / "out" / "build.json").exists()})
    return {"ok": True, "projects": rows}


def cad_build(project: str, show: bool = True) -> dict:
    """Run the project's model.py, export STEP/STL/3MF per part and (if show) update the viewer.

    Returns per-part volume, bounding box, centre of mass, validity and file paths.
    On a model error returns ok=False with the Python traceback so the model can be fixed.
    """
    d = project_dir(project)
    proc = subprocess.run(
        [sys.executable, "-m", "tb.runner", str(d)],
        cwd=TOOLBOX, capture_output=True, text=True, timeout=300,
    )
    last = proc.stdout.strip().splitlines()[-1:] or [""]
    try:
        result = json.loads(last[0])
    except json.JSONDecodeError:
        return {"ok": False, "error": "Model process produced no result", "stderr": proc.stderr[-1800:]}
    if not result["ok"]:
        return result
    title = (load_json(d / "project.json", {}) or {}).get("title", project)
    save_json(d / "out" / "build.json", result)
    if show:
        _write_scene(project, title, result["parts"])
    result["project_dir"] = str(d)
    result["viewer"] = "http://localhost:3030" if show else None
    return result


def cad_read(project: str, path: str = "model.py") -> dict:
    """Read a text file from the project folder (default model.py)."""
    f = inside(project_dir(project), path)
    return {"ok": True, "path": str(f), "content": f.read_text()}


def cad_write(project: str, content: str, path: str = "model.py") -> dict:
    """Write a text file into the project folder (default model.py). Does not build."""
    f = inside(project_dir(project, create=True), path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    return {"ok": True, "path": str(f), "bytes": len(content)}


def cad_import(project: str, file: str, name: str = "") -> dict:
    """Copy a STEP/STL/3MF/DXF file into the project's imports/ folder for use from model.py.

    In model.py load it with import_step("imports/<file>") or import_stl(...).
    """
    from pathlib import Path
    import shutil

    src = Path(file).expanduser()
    if not src.is_file():
        return {"ok": False, "error": f"No such file: {src}"}
    if src.suffix.lower() not in {".step", ".stp", ".stl", ".3mf", ".dxf", ".svg", ".brep"}:
        return {"ok": False, "error": f"Unsupported format {src.suffix}"}
    dest = inside(project_dir(project, create=True), f"imports/{name or src.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return {"ok": True, "path": f"imports/{dest.name}", "hint": f'import_step("imports/{dest.name}")'}


def project_pack(project: str) -> dict:
    """Zip the whole project (model, brief, circuit, imports and every output) into exports/ for sharing or backup."""
    import datetime as dt
    import zipfile

    d = project_dir(project)
    dest = HOME / "exports" / f"{project}-{dt.date.today().isoformat()}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.rglob("*")):
            if f.is_file() and "view" not in f.relative_to(d).parts and "__pycache__" not in f.parts:
                z.write(f, f"{project}/{f.relative_to(d)}")
                count += 1
    return {"ok": True, "file": str(dest), "files": count, "size_kb": round(dest.stat().st_size / 1024)}


def register(mcp) -> None:
    for fn in (project_new, project_list, project_pack, cad_build, cad_read, cad_write, cad_import):
        mcp.tool()(fn)
