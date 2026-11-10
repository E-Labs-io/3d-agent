# 3D Agent

A Claude Code plugin that designs physical things properly: parametric CAD on a real kernel, automatic design checks, stress analysis, sourced material and standards data, drawings and a bill of materials generated from the model, circuits and wiring, and print preparation. A live viewer shows the model as it changes.

## Install

```
/plugin marketplace add E-Labs-io/3d-agent
/plugin install 3d-agent@3d-agent
/3d-setup
```

`/3d-setup` needs [uv](https://docs.astral.sh/uv/) and Node. The first run downloads about 900 MB of Python packages.

## Use

```
/3d-design a wall bracket for a 2 kg speaker, printed in PETG on a 256 mm bed
```

or just describe what you want. Other commands: `/3d-start`, `/3d-stop`, `/3d-status`, `/3d-new`, `/3d-check`, `/3d-plans`, `/3d-bom`, `/3d-bundle`.

Designs are kept in `~/Documents/3D-Agent` (set `THREED_AGENT_HOME` to move them).

## What is inside

| Job | Works out of the box | Needs something installed or a key |
|---|---|---|
| Solid modelling, STEP/STL/3MF | build123d, bd_warehouse | |
| Design checks | mesh, walls, printability, clashes | |
| Stress and hand calcs | built-in solver, beams, bolts, buckling | CalculiX route (not implemented yet) |
| Materials, rules, standards | sourced tables | |
| Drawings | SVG and DXF projected from the solid | |
| BOM | generated, with supplier search links | live prices: DigiKey, Mouser, Farnell keys |
| Circuits | SKiDL netlist and rules check | KiCad for exports, ngspice for simulation |
| Wiring diagrams | built-in SVG and cut list | WireViz + Graphviz |
| Print estimates | volume-based estimate, orientation, bed layout | PrusaSlicer or OrcaSlicer for real figures |
| Printers | | Moonraker, PrusaLink or OctoPrint printer |
| Finding designs | KiCad libraries, GitHub | OSHWA and EPO keys |

`toolbox_status` reports what is available on your machine. Routes that need a program or key say exactly what is missing.

## Known untested

These are written from published documentation but have not been run against the real thing: supplier APIs, the KiCad and ngspice routes, slicer command lines, and all three printer adapters. Expect a shake-down the first time each is used. See `docs/` for details.

## Development

```
cd toolbox && uv sync --extra extras && uv run pytest -q
npm install && node server.js
```

See `CLAUDE.md` and `toolbox/CONTRIBUTING.md`.

## Licence

MIT. Optional programs it can drive (KiCad, slicers, WireViz, Gmsh) keep their own licences and are run as separate processes.

## Safety note

A project's `model.py` and `circuit.py` are Python and run with your user account's rights when built. Only build projects you wrote or trust, the same as any script.
