---
description: Generate 2D plans + exploded views (SVG drawings) for the active scene
allowed-tools: Task, Read, Write
---

The user wants the Manager to produce the engineering drawings for the current 3D scene.

1. Read `scene/current.json` and identify the project slug from `metadata.name`.

2. Spawn the `manager` subagent with this prompt:

> Produce the full set of 2D engineering drawings in `deliverables/{slug}/drawings/`:
>
> 1. `01-front-elevation.svg` — orthographic front view at a sensible scale (1:5 typical), all key external dimensions
> 2. `02-section-view.svg` — cutaway through the centre line, hatched by material, internal components labelled, cross-referenced to BOM
> 3. `03-plan-view.svg` — top-down view at appropriate scale
> 4. `04-bottom-view.svg` — view from below
> 5. `05-exploded-isometric.svg` — exploded view with all parts/sections separated, leader lines, callouts numbered to match BOM, assembly order list
> 6. `06-{subsystem}-detail.svg` — detail view of the most important subsystem (e.g. propulsion / linkage / mechanism), 2:1 scale
>
> Apply standard engineering line weights: visible 0.7 mm, hidden 0.35 mm dashed, centre 0.25 mm dash-dot, dimension 0.25 mm. Title block bottom-right with project name, drawing number, scale, date, drawn-by ("3D Agent"), sheet n of m.
>
> SVGs must be standalone — embed all styles inline.

3. After the Manager finishes, list which drawings were produced and their sizes. The user can view them via the 📄 Docs panel in the viewer.
