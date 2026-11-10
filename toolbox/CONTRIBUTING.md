# Toolbox module contract

The toolbox is an MCP server (`server.py`) for an AI design agent. Each file in `tb/` is one
tool group and exposes `register(mcp)`, which calls `mcp.tool()(fn)` for each public function.
See `tb/cad.py` for the pattern and `tb/common.py` for shared helpers.

## Rules for every tool

- **Plain functions, typed arguments, JSON-serialisable dict out.** Always include `"ok": True/False`.
  On failure return `{"ok": False, "error": "<what and how to fix>"}`; do not raise to the caller.
- **Docstrings are the tool descriptions the agent reads.** First line says what it does and returns.
  Say units. Keep them short.
- **Numbers, not opinions.** Return measured values with units in the key name (`mass_g`, `stress_mpa`).
- **Routes.** Where more than one program can do a job, take a `route` argument defaulting to `"auto"`.
  Detect optional programs with `common.which(...)`. If a route is not installed, return
  `{"ok": False, "error": ..., "install": "<exact command or URL>"}`. Never install anything yourself.
- **Every data value has a source.** Data files live in `data/<group>/` as JSON. Each record carries
  `source` (URL or document name) and, where it is an estimate or rule of thumb, `"basis": "estimate"`.
  Never invent a material property, standard dimension or price. Leave it out and say so.
- **Projects.** A project is `projects/<slug>/` with `model.py`, `out/build.json` (written by
  `cad_build`: per-part volume, bbox, centre of mass, material, process, files) and STEP/STL/3MF
  in `out/`. Resolve it with `common.project_dir(slug)`; build paths with `common.inside(...)`.
  Write your outputs under `projects/<slug>/out/<group>/`.
- **Secrets** come from environment variables only. Never log them. A missing key is an
  `ok: False` with the variable name and where to apply for it.
- **Network** calls use `httpx` with a timeout. Tests must pass offline (mock or skip).
- **Licences.** GPL/AGPL programs are run as subprocesses, never imported.
- **No new dependencies.** Installed: build123d, bd_warehouse, trimesh, manifold3d, gmsh, scikit-fem,
  meshio, numpy, scipy, httpx, pyyaml, mcp, augura, isofits, dimstack, PyNiteFEA, skidl, spicelib.
  If you need another, do not add it: finish without it and list it in your final report.
- **Stay in your files.** Only create or edit the files named in your brief. Do not edit
  `pyproject.toml`, `server.py`, `tb/common.py`, `tb/cad.py`, `tb/runner.py`, `tb/model.py`.

## Tests

`tests/test_<group>.py`, run with `uv run pytest tests/test_<group>.py -q` from `toolbox/`.
Test against the built example project `mif4-cradle` (run `cad_build("mif4-cradle", show=False)`
in a fixture if `out/build.json` is missing). Verify numbers against a hand calculation where one exists.

## Style

Python 3.12, type hints, small functions, comments only where the reason is not obvious.
