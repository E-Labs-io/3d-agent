# 3D Agent

An engineering design environment for Claude. Designs are parametric CAD code, checked and analysed by tools, shown in a live viewer.

## Layout

| Path | What it is |
|---|---|
| `toolbox/` | Python MCP server (`server.py`) and tool modules (`tb/`). Run with `uv`. |
| `toolbox/data/` | Sourced data: materials, process rules, standards, electronics tables. |
| `toolbox/tests/` | `uv run pytest -q` from `toolbox/`. |
| `server.js`, `public/` | The viewer: Node server plus Three.js front end, port 3030. |
| `agents/`, `commands/`, `skills/` | The Claude Code plugin layer. |
| `examples/` | Example projects (copied into the data folder by tests). |
| `docs/` | Research notes and design decisions. |

User designs are **not** in this repo. They live in `~/Documents/3D-Agent` (override with `THREED_AGENT_HOME`):

```
~/Documents/3D-Agent/
  scene/current.json        what the viewer shows
  projects/<slug>/
    model.py                the design (build123d)
    brief.md, circuit.py    optional
    imports/                STEP/STL brought in, each with a source sidecar
    out/                    everything generated: STEP, STL, 3MF, drawings, bom, fea
  exports/                  zips and viewer exports
```

## How a design is made

1. `model.py` defines `PARTS` (name to `part(shape, material=..., ...)`) and optionally `HARDWARE`.
2. `cad_build` runs it in a subprocess and writes STEP, STL and 3MF per part, an assembly STEP, `out/build.json`, and the viewer scene.
3. `check_all` gates it: mesh health, wall thickness, printability, clashes.
4. Analysis, drawings, BOM and making tools all read `out/build.json` and the files beside it.

Units are millimetres. CAD is Z-up; the viewer is Y-up and the build converts.

## Working on this repo

- **Tool modules** follow `toolbox/CONTRIBUTING.md`: plain functions, dict out with `ok`, numbers with units, sources on all data, optional programs detected and never installed.
- **No value from memory.** Material properties, standard dimensions and prices come from `toolbox/data/` (with a source) or a live lookup.
- **GPL and AGPL programs are subprocesses,** never imports.
- **Dependencies** are pinned in `toolbox/pyproject.toml`. The lockfile is committed.
- **The viewer server** binds to 127.0.0.1 and refuses cross-origin requests. Keep it that way.
- **Tests must pass offline** and must not need KiCad, ngspice, a slicer or a printer.

## Viewer scene format

The toolbox writes `scene/current.json`; you rarely edit it by hand. Each built part is an object of `type: "file"` pointing at its mesh, tagged `_printPart`, or `_reference: true` for fit ghosts. The older primitive types (`box`, `cylinder`, `custom_code` and so on) still render and are fine for a quick sketch, but they are meshes only: no STEP, no checks. Anything real goes through `model.py`.
