---
description: Kick off a full product-design workflow — Engineer/Designer → 3D Specialist → Manager
argument-hint: "<product description>"
allowed-tools: Task, Read, Write, Bash
---

The user wants to design and build a 3D product end-to-end:

> **$ARGUMENTS**

Run the standard E-Labs product-design workflow:

## Stage 1 — Engineer / Designer

Spawn the `engineer-designer` subagent with this brief:

> The user wants to design: **$ARGUMENTS**
>
> Produce a complete engineering brief covering:
> 1. Use case & constraints (assume 300×300×300 mm print volume unless stated otherwise)
> 2. Functional requirements with measurable targets
> 3. Subsystem architecture
> 4. Material selection per part
> 5. Mechanical design (load paths, joints)
> 6. Electrical design (if applicable: power budget, real part numbers)
> 7. Manufacturing plan (DfM, print sections)
> 8. Open questions and risks
> 9. Tabulated parts list ready for the 3D Specialist
>
> Write the brief to `briefs/{slug}.md` where slug is a kebab-case version of the product name. Show the brief summary to the user before moving on.

Wait for the Engineer/Designer to finish. Show the user a 1-paragraph summary of the brief.

## Stage 2 — 3D Specialist

Spawn the `3d-specialist` subagent with this brief:

> Build the design from `briefs/{slug}.md` into `scene/current.json`. Auto-group all parts by subsystem per the spec in `agents/3d-modeler.md` § Auto-grouping. Set the camera to frame the assembly. Write the scene file and confirm what got built (object count, group breakdown).

The viewer at http://localhost:3030 will update live as the scene is written. If the server isn't running, tell the user to run `/3d-start` first.

## Stage 3 — Manager

After the scene is built, ask the user whether to also produce the deliverables (BOM, manufacturing plan, design doc, drawings, assembly instructions). If yes, spawn the `manager` subagent to produce them in `deliverables/{slug}/`.

## Output

Briefly confirm what was completed at each stage. The user will see the live model update in the viewer; the Engineer/Designer's brief and Manager's deliverables are markdown/SVG on disk.
