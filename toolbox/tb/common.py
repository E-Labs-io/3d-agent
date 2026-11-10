"""Shared paths, project lookup and route detection for the toolbox."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

TOOLBOX = Path(__file__).resolve().parent.parent
# Code lives with the plugin; user designs live in their own folder so a plugin
# update never touches them. The viewer (server.js) uses the same variable.
HOME = Path(os.environ.get("THREED_AGENT_HOME", "~/Documents/3D-Agent")).expanduser().resolve()
ROOT = HOME  # older name, kept for modules that import it
PROJECTS = HOME / "projects"
DATA = TOOLBOX / "data"
SCENE_FILE = HOME / "scene" / "current.json"

_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def project_dir(slug: str, create: bool = False) -> Path:
    """Resolve a project slug to its folder. Slugs are a single plain path segment."""
    if not isinstance(slug, str) or not _SLUG.match(slug) or ".." in slug:
        raise ValueError(f"Invalid project slug: {slug!r} (use lowercase letters, digits, '-', '_')")
    d = PROJECTS / slug
    if create:
        (d / "out").mkdir(parents=True, exist_ok=True)
    elif not d.is_dir():
        raise FileNotFoundError(f"No project '{slug}'. Existing: {sorted(p.name for p in PROJECTS.glob('*') if p.is_dir())}")
    return d


def inside(base: Path, rel: str) -> Path:
    """Join a caller-supplied relative path to base, refusing anything that escapes it."""
    target = (base / rel).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        raise ValueError(f"Path escapes the project: {rel!r}")
    return target


def which(*names: str) -> str | None:
    """First executable found on PATH or in the usual macOS app bundles."""
    bundles = {
        "kicad-cli": "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        "prusa-slicer": "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer",
        "orca-slicer": "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer",
        "FreeCADCmd": "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd",
        "openscad": "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    }
    for n in names:
        p = shutil.which(n)
        if p:
            return p
        b = bundles.get(n)
        if b and Path(b).exists():
            return b
    return None


def load_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))
