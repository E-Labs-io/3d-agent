# MIF4 Cradle — Print Notes

Exported 2026-09-07. Units **mm**, Z-up, both parts centred in XY and sitting on Z=0.

| File | Footprint (mm) | Height | Tris |
|------|---------------|-------:|-----:|
| `mif4-cradle-body.stl` | 193 x 111 | 56.5 | 2,816 |
| `mif4-top-plate.stl`   | 193 x 111 | 12.0 | 3,316 |

Both fit a 256 x 256 bed with room to spare. Print separately — they will not fit side by side on a 256 bed (2 x 193 = 386).

## Orientation — already baked into the files

**Body** — exported open-side-up, exactly as it should print. Do not rotate.
- Wall nut pockets are horizontal holes in vertical walls. The hex is **point-up**, so the top self-supports and needs no bridging.
- Floor vents bridge ~14 mm. Fine on any tuned machine.

**Top plate** — exported **already flipped**, shoulder-side down. Do not rotate.
- This puts the 3 mm shoulder on the build plate (solid, small holes only) and opens the hex pockets upward as plain cavities.
- If you flip it the other way you will be bridging over 16.8 mm hex openings and the pockets will sag.

## Settings

| | Body | Plate |
|---|---|---|
| Layer | 0.2 mm | 0.2 mm |
| Walls | 4 | 5 |
| Top/bottom | 5 / 4 | 5 / 5 |
| Infill | 30% gyroid | 40% gyroid |
| Supports | none | none |
| Brim | 5 mm recommended (193 mm footprint) | 5 mm |

Material: PETG or ABS/ASA. PLA works but creeps under sustained load — avoid if the cradle will hang from a spigot for long periods.

## Hardware

| Location | Thread | Nut | Qty |
|----------|--------|-----|----:|
| Top plate, centre line | 3/8"-16 UNC | AF 14.29 x 8.73 | 3 |
| Top plate, outboard | 1/4"-20 UNC | AF 11.11 x 5.56 | 4 |
| Each wall, centre | 3/8"-16 UNC | AF 14.29 x 8.73 | 1 (x2) |
| Each wall, flanking | 1/4"-20 UNC | AF 11.11 x 5.56 | 2 (x2) |
| Plate to walls | M4 | heat-set insert | 4 |

Pockets are modelled at nominal AF + 0.15 clearance. Test-fit one nut in a printed corner before committing.

## Known issues

**The meshes are not watertight.** Each part is built from stacked/overlapping solids, so there are coincident internal faces where layers meet. Every mainstream slicer (PrusaSlicer, Cura, Bambu, Orca) unions these correctly on slice. If yours complains, run through the free Microsoft 3D repair service or `admesh`. This does not affect the printed result.

**Cavity clearance is 0.5 mm per side.** Tight. Print a 30 mm corner test slice and check the MIF4 corner drops in before running the full ~8 h part.

**Check the MIF4 top face before printing.** The plate sits 0.5 mm above the unit. Anything proud on its lid (label, screw head, domed cover) will foul.
