# Known untested routes

Written from published documentation and tested only against mocks. Each needs a shake-down the first time the real program, key or device is present.

| Route | Module | What is unproven |
|---|---|---|
| DigiKey, Mouser, Farnell live search | `tb/sourcing.py` | Live calls. Farnell's response wrapper name and lead-time unit are not in its docs. |
| Moonraker, PrusaLink, OctoPrint | `tb/printers.py` | No real printer. PrusaLink API-key auth is not described in its spec. |
| OSHWA, EPO patent search, GitHub code search | `tb/sources.py` | Need keys. EPO token and response shapes are partly from memory. |
| CalculiX | `tb/fea.py` | Not implemented. The built-in solver is the working route. |

## Shaken down on 10 Nov 2026

Run for real on macOS (Apple silicon). The live tests for these run whenever the program is installed.

| Route | Version | Result |
|---|---|---|
| ngspice | 47 | Operating point, transient and AC runs match hand calculations. Fixed: a netlist that opened with a part lost it to the SPICE title line. |
| WireViz + Graphviz | 0.4.1, 16.1.1 | Diagram, wire list and cable list produced. No changes needed. |
| PrusaSlicer | 2.9.7 | Sliced both cradle parts; time and filament read correctly. With no profile it uses its own defaults (PLA, 0.3 mm, 20%), now reported under `settings`. |
| OrcaSlicer | 2.5.0 | Slices and reads back with a machine and process JSON. Its bundled profiles are packed (`.opc`) and cannot be passed to the command line, so profiles must be exported from the app. A minimal hand-written filament JSON crashed it (exit 139); an exported filament preset is untested. |
| KiCad | 10.0.8 | ERC, DRC, PDF, SVG, BOM, netlist, SPICE, Gerbers and drill ran on the `pic_programmer` demo. Fixed: STEP export exits non-zero when a part has no 3D model although the board file is written. Run from the disk image, before first launch, so library warnings were expected. |

## Data gaps (left out rather than invented)

- No FDM PA12 filament record; `pa12` is SLS powder.
- Brass and acrylic have no strength or modulus; several plastics have no heat deflection value.
- Inch nut thickness only from 1/4 in up; smaller sizes have across-flats only, marked low confidence.
- Between-layer shear stiffness for printed parts is an estimate and is flagged in every result that uses it.
- Reuse terms for Printables, MakerWorld, Thingiverse, GrabCAD, Thangs, TraceParts and McMaster-Carr could not be read; they are link-only and marked unconfirmed.
- The Bambu Lab adapter is a stub; its wiki page could not be fetched, so the wording is general.

## Limits of the analysis

Linear static only: no fatigue, impact, creep, contact or heat. Printed parts are modelled as solid, not as perimeters and infill.
