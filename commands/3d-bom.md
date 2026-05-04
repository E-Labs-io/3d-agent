---
description: Generate or regenerate the Bill of Materials for the active scene
allowed-tools: Task, Read, Write
---

The user wants the Manager to produce the BOM for the current 3D scene.

1. Read `scene/current.json` to inventory all objects (skip group headers, i.e. `_isGroup: true`).

2. Identify the project slug from `metadata.name` (kebab-case it).

3. Spawn the `manager` subagent with this prompt:

> Produce a complete Bill of Materials in `deliverables/{slug}/BOM.md` based on the current scene at `scene/current.json`.
>
> Group rows by subsystem (use the `_groupId` field on each object → group's name). Subtotal per subsystem and grand total at the bottom.
>
> For purchased components (motors, ESCs, sensors, fasteners) use real part numbers and a vendor — RS Components, Mouser, Digi-Key, McMaster, AliExpress, hobbyking, T-Motor — whichever fits. For printed/machined parts list material + process.
>
> Cross-check: every object in the scene must have a BOM row, OR be tagged in BOM as "represented in CAD only" if it's purely visual.
>
> End with: total component count, estimated total cost, longest lead time, critical-path notes.

4. After the Manager finishes, summarise for the user: total parts, total cost, lead-time gating part. Open the Docs panel in the viewer (if running) so they can read it.
