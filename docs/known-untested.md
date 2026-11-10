# Known untested routes

Written from published documentation and tested only against mocks. Each needs a shake-down the first time the real program, key or device is present.

| Route | Module | What is unproven |
|---|---|---|
| DigiKey, Mouser, Farnell live search | `tb/sourcing.py` | Live calls. Farnell's response wrapper name and lead-time unit are not in its docs. |
| KiCad ERC/DRC and exports | `tb/electronics.py` | Report JSON parsing is a guess at the layout. Flags are from the KiCad 10 CLI reference. |
| ngspice simulation | `tb/electronics.py` | Batch flags and raw-file settings were written from memory. Parser tested on synthetic data. |
| WireViz diagrams | `tb/electronics.py` | Not installed here. The built-in diagram route is tested. |
| PrusaSlicer, OrcaSlicer | `tb/make.py` | G-code comment patterns and OrcaSlicer output naming are from memory. |
| Moonraker, PrusaLink, OctoPrint | `tb/printers.py` | No real printer. PrusaLink API-key auth is not described in its spec. |
| OSHWA, EPO patent search, GitHub code search | `tb/sources.py` | Need keys. EPO token and response shapes are partly from memory. |
| CalculiX | `tb/fea.py` | Not implemented. The built-in solver is the working route. |

## Data gaps (left out rather than invented)

- No FDM PA12 filament record; `pa12` is SLS powder.
- Brass and acrylic have no strength or modulus; several plastics have no heat deflection value.
- Inch nut thickness only from 1/4 in up; smaller sizes have across-flats only, marked low confidence.
- Between-layer shear stiffness for printed parts is an estimate and is flagged in every result that uses it.
- Reuse terms for Printables, MakerWorld, Thingiverse, GrabCAD, Thangs, TraceParts and McMaster-Carr could not be read; they are link-only and marked unconfirmed.
- The Bambu Lab adapter is a stub; its wiki page could not be fetched, so the wording is general.

## Limits of the analysis

Linear static only: no fatigue, impact, creep, contact or heat. Printed parts are modelled as solid, not as perimeters and infill.
