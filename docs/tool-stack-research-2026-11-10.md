# Tool stack research, 10 Nov 2026

Versions and licences read from PyPI, npm, GitHub and vendor docs on 10 Nov 2026.
Nothing here was installed or run. Items marked UNVERIFIED need checking before use.

## Recommended stack

| Job | First route | Other routes | Licence note |
|---|---|---|---|
| Solid modelling | build123d 0.13.0 | CadQuery 2.8.0 (constraint-solved assemblies), FreeCAD 1.1 headless, Zoo text-to-CAD (paid cloud) | Apache-2.0; FreeCAD LGPL |
| Standard parts | bd_warehouse 0.4.0 | FreeCAD Fasteners workbench | Apache-2.0; UNC by name UNVERIFIED |
| Mesh work | manifold3d 3.5.4 + trimesh 5.2.0 | OpenSCAD for existing .scad libraries | Apache-2.0 / MIT |
| Drawings | build123d projection (visible + hidden edges, dimension objects) | FreeCAD TechDraw (headless export UNVERIFIED) | |
| Printability | augura 0.1.8 | own rule file per process | Apache-2.0; young project |
| Stress | Gmsh 4.15.2 then CalculiX 2.23 | PyNite 3.2.1 for beams; FEniCSx for custom physics | GPL: run as subprocess |
| Fits and stacks | isofits 1.0, dimstack 0.9.0 | stackcore (Monte Carlo) | MIT |
| Optimisation | pytopo3d 0.3.0 | BESO, dl4to4ocp | MIT / LGPL |
| Mechanisms | MuJoCo 4.0.0 | pychrono | Apache-2.0 |
| Airflow | OpenFOAM.app v2606 | | GPL-3 |
| Circuits | SKiDL 3.0.0 or atopile 0.15.9, checked by kicad-cli (KiCad 10) | tscircuit | MIT |
| Circuit simulation | ngspice batch mode + spicelib 1.6.4 | | |
| Wiring diagrams | WireViz 0.4.1 | | GPL-3: subprocess |
| Sourcing | DigiKey, Mouser, Farnell APIs; jlcparts offline | Nexar (free tier 100 parts) | approval-gated |
| BOM store | InvenTree 1.7.1 | kicad-cli BOM export | MIT |
| Slicing | PrusaSlicer 2.9.7 CLI | OrcaSlicer 2.5.0 CLI | AGPL: subprocess |
| Printer link | Moonraker adapter | PrusaLink; OctoPrint | Bambu blocks third-party control |

## Gaps to fill ourselves

- Materials: MatWeb terms exclude AI use. No open dataset has layer-direction strength for printed parts. Build a table from Prusa and Bambu data sheets.
- Design rules: no open machine-readable set for any process. Write one per process with a source per number.
- Standards: ISO 286 and most ISO/DIN are paywalled. FED-STD-H28 covers threads for free.
- Run times for stress checks: no source gave them. Measure on the first build.

## Avoid

- MeshLib (non-commercial licence), raw opencascade.js (stale since 2023), PyMeshLab and pymeshfix if linking (GPL-3).
- McMaster, MakerWorld, GrabCAD for automated access (refused or terms unreadable).
- KiCad IPC API for headless work (needs the GUI until KiCad 11).

## Existing MCP servers worth reading before building

- build123d: https://github.com/pzfreo/build123d-mcp and https://github.com/jdilla1277/agentcad
- FreeCAD: https://github.com/neka-nat/freecad-mcp
- KiCad: https://github.com/mixelpixx/KiCAD-MCP-Server
- Printers: https://github.com/DMontgomery40/mcp-3D-printer-server (GPL-2.0), https://github.com/codeofaxel/Kiln (AGPL-3.0)
- DfM: https://jsr.io/@casys/mcp-dfm

## Key sources

- https://build123d.readthedocs.io/en/latest/import_export.html
- https://bd-warehouse.readthedocs.io/en/latest/fastener.html
- https://github.com/elalish/manifold
- https://pypi.org/project/augura/
- https://dhondt.de/ov_calcu.htm
- https://apm.matweb.com/reference/terms.aspx
- https://github.com/OpenFilamentCollective/open-filament-database
- https://docs.kicad.org/10.0/en/cli/cli.html
- https://arxiv.org/abs/2602.00510
- https://github.com/Arksine/moonraker
- https://wiki.bambulab.com/en/software/third-party-integration
- https://benchlm.ai/benchmarks/cadgenbenchgeneration
- https://arxiv.org/abs/2605.10865
