"""Runs a project's model.py in its own process and writes every output file.

Invoked as: python -m tb.runner <project_dir>
Prints one JSON object on the last line of stdout.
"""
from __future__ import annotations

import hashlib
import json
import os
import runpy
import sys
import traceback
from pathlib import Path


def main(project: Path) -> dict:
    from build123d import Compound, Mesher, Unit, export_step, export_stl
    import trimesh

    out = project / "out"
    (out / "view").mkdir(parents=True, exist_ok=True)
    os.chdir(project)  # so model.py can open imports/<file> by relative path
    ns = runpy.run_path(str(project / "model.py"), run_name="__model__")
    specs = ns.get("PARTS")
    if not isinstance(specs, dict) or not specs:
        raise ValueError("model.py must define PARTS = {'name': part(shape, ...), ...}")

    parts = {}
    for name, spec in specs.items():
        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Part name {name!r}: use letters, digits, '-' and '_' only")
        shape = spec.shape
        bb = shape.bounding_box()
        com = shape.center()
        info = {
            "material": spec.material, "color": spec.color, "opacity": spec.opacity,
            "reference": spec.reference, "print_flip": spec.print_flip,
            "process": spec.process, "qty": spec.qty, "note": spec.note,
            "valid": bool(shape.is_valid),
            "volume_mm3": round(shape.volume, 2),
            "area_mm2": round(shape.area, 2),
            "bbox_mm": [round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3)],
            "bbox_min": [round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3)],
            "centre_of_mass": [round(com.X, 3), round(com.Y, 3), round(com.Z, 3)],
            "files": {},
        }

        # Viewer mesh: assembled position, converted to the viewer's Y-up frame.
        tmp = out / "view" / f"{name}.cad.stl"
        export_stl(shape, str(tmp), tolerance=0.05, angular_tolerance=0.2)
        mesh = trimesh.load_mesh(tmp)
        tmp.unlink()
        view = mesh.copy()
        v = view.vertices.copy()
        view.vertices = v[:, [0, 2, 1]] * [1, 1, -1]
        vpath = out / "view" / f"{name}.stl"
        view.export(vpath)
        info["files"]["view"] = f"out/view/{name}.stl?v={hashlib.md5(vpath.read_bytes()).hexdigest()[:8]}"

        if not spec.reference:
            export_step(shape, str(out / f"{name}.step"))
            info["files"]["step"] = f"out/{name}.step"
            # Print mesh: flipped if asked, centred in XY, sitting on Z=0.
            pm = mesh.copy()
            if spec.print_flip:
                pm.apply_transform(trimesh.transformations.rotation_matrix(3.141592653589793, [1, 0, 0]))
            lo, hi = pm.bounds
            pm.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
            pm.export(out / f"{name}.stl")
            info["files"]["stl"] = f"out/{name}.stl"
            mesher = Mesher(unit=Unit.MM)
            mesher.add_shape(shape)
            mesher.write(str(out / f"{name}.3mf"))
            info["files"]["3mf"] = f"out/{name}.3mf"
            info["mesh"] = {"triangles": int(len(pm.faces)), "watertight": bool(pm.is_watertight)}
        parts[name] = info

    real = [s.shape for s in specs.values() if not s.reference]
    if len(real) > 1:
        export_step(Compound(children=real), str(out / "assembly.step"))
    hardware = ns.get("HARDWARE", [])
    if not isinstance(hardware, list) or not all(isinstance(h, dict) and h.get("name") for h in hardware):
        raise ValueError("HARDWARE must be a list of dicts, each with at least 'name' (plus qty, spec, mpn, supplier, url)")
    return {"ok": True, "parts": parts, "hardware": hardware, "assembly_step": "out/assembly.step" if len(real) > 1 else None}


if __name__ == "__main__":
    try:
        result = main(Path(sys.argv[1]))
    except Exception as e:  # reported to the agent, which fixes model.py and retries
        result = {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1800:]}
    print(json.dumps(result))
