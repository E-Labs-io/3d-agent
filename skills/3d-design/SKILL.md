---
name: 3D Design
description: Use when the user wants to design, model, check, analyse, document or make a physical object: enclosures, brackets, mounts, mechanisms, printed or machined parts, assemblies, and their electronics and wiring. Also for stress checks, material choice, standard parts and fits, drawings, bills of materials, print estimates and printer jobs.
---

# 3D Design with the 3D Agent toolbox

Designs are parametric CAD code checked by tools, not shapes described in prose. The `3d-toolbox` MCP server does the work; the viewer at http://localhost:3030 shows the result.

## Start

1. If the toolbox tools are not available, run `/3d-setup`.
2. `/3d-start` if the viewer is not running.
3. `project_list` to find an existing project, or `project_new` for a new one.

## The loop

**Write the model, build it, check it, fix it, repeat until the checks pass.**

| Step | Tool |
|---|---|
| Edit the model (`model.py`, build123d) | `cad_read`, `cad_write` |
| Build: STEP, STL, 3MF, viewer update | `cad_build` |
| Gate: mesh, walls, printability, clashes | `check_all` |
| Loads: stress, deflection, safety factor | `fea_faces`, `fea_static`, `beam_check`, `bolt_check` |
| Mass and centre of gravity | `mass_properties` |

## Look it up, do not recall it

| Need | Tool |
|---|---|
| Material properties and selection | `material_get`, `material_compare`, `material_select` |
| Process limits (wall, overhang, clearance) | `rules_get`, `rules_check` |
| Fasteners, holes, inserts, bearings, fits | `fastener_dims`, `fit_limits`, `standards_search` |
| Existing designs and parts | `design_search`, `design_fetch`, `design_links`, `step_inspect` |
| Components with price and stock | `part_search`, `part_best_price`, `sourcing_links` |

If a tool has no data, say so. Never fill a gap with a remembered number, price or part number.

## Outputs

| Output | Tool |
|---|---|
| Drawings (SVG, DXF), projected from the solid | `drawing_make` |
| Bill of materials with links and tracking | `bom_make`, `bom_set_status` |
| Circuits, wiring diagrams, power budget | `circuit_build`, `wiring_diagram`, `power_budget` |
| Print time, material, orientation, bed layout | `print_estimate`, `print_orient`, `print_bed_layout` |
| Printers | `printer_status`, `printer_upload`, `printer_start` |
| Share or back up a project | `project_pack` |

## Agents

For anything beyond a small edit, use the specialists: **engineer** (brief and targets), **cad-builder** (model and check loop), **analyst** (verification), **electronics** (circuits and wiring), **manager** (drawings, BOM, making). `/3d-design <request>` runs them in order.

## Rules

- Units are millimetres, Z is up.
- A design is not done until `check_all` passes, or the user has accepted each remaining problem by name.
- Judge geometry from tool numbers, not screenshots.
- More than one route exists for most jobs. `toolbox_status` shows what is installed; when a route is missing, use the next one and say which you used.
- Starting, resuming or cancelling a print needs the user's explicit yes for that job.
- User designs live in `~/Documents/3D-Agent` (or `$THREED_AGENT_HOME`), never inside the plugin.
