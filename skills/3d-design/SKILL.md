---
name: 3D Design
description: Use when the user asks to design, build, model, render, or modify 3D objects — products, parts, mechanical assemblies, architectural elements, 3D-printable items, vehicles, drones, rockets, or anything else physical that needs a CAD-style representation. Also use for BOMs, manufacturing plans, exploded views, and engineering drawings.
---

# 3D Design — 3D Agent plugin

The user is working with the 3D Agent — a live AI-powered 3D design environment. Scenes live as JSON in `scene/current.json` and render in real time at http://localhost:3030 via WebSocket file-watcher.

## When to invoke this skill

- User says "design / build / model / make a 3D ___"
- User asks for a CAD-style render of a physical object
- User wants to modify, iterate on, or redesign an existing 3D scene
- User asks for a Bill of Materials, manufacturing plan, exploded view, or 2D drawings of a 3D design
- User mentions 3D printing, machining, assembly, or DfM in the context of a specific part

## How to start

1. **Check server status.** If port 3030 isn't running, run the `/3d-start` command first. The viewer needs the server live to update.

2. **Locate the scene file.** Look for `scene/current.json` in the current working directory (project-local) or fall back to the plugin's bundled location. The user can have multiple projects each with their own scene + deliverables.

3. **Read existing context** before changing anything:
   - `scene/current.json` — the live model
   - `briefs/{project}.md` — any prior engineering brief
   - `deliverables/{project}/` — any prior BOM / plans / drawings

4. **Pick the right specialist subagent**:

   | Task | Agent |
   |------|-------|
   | Research / plan / write engineering brief for a new product | `engineer-designer` |
   | Build geometry / iterate / adjust the scene | `3d-specialist` |
   | Produce BOM, plans, exploded views, assembly instructions | `manager` |
   | One-off geometry tweak (no full design needed) | `3d-modeler` |
   | Specific advice on 3D printing | `3d-printing` |
   | Specific advice on manufacturing / DfM | `manufacturing` |
   | Material selection question | `materials` |
   | Tolerances / GD&T / precision CAD | `cad-designer` |

   Typical full workflow for a new product: **engineer-designer** → **3d-specialist** → **manager**.

5. **Always write `scene/current.json` directly** — don't just describe in text. The viewer updates instantly.

6. **Auto-group multi-part assemblies.** Read `agents/3d-modeler.md` § "Auto-grouping" for the spec. Group by subsystem (Structure / Aerodynamics / Propulsion / Power / Avionics / Hardware) using `_isGroup` and `_groupId` JSON fields.

## Quick slash commands available

- `/3d-start` — launch viewer server
- `/3d-stop` — kill server
- `/3d-status` — server + scene state
- `/3d-new "Project Name"` — fresh empty scene
- `/3d-design <description>` — full Engineer → 3D Specialist → Manager workflow
- `/3d-bom` — regenerate Bill of Materials from current scene
- `/3d-plans` — regenerate 2D drawings from current scene
- `/3d-bundle` — export scene + docs + drawings as a single `.3dap` file

## Scene format reference

See the `CLAUDE.md` in the plugin root. Key points:

- **Units are mm** by default
- **Geometry types**: box, sphere, cylinder, cone, torus, plane, capsule, pipe, gear, spring, hex_bolt, nut, lathe, extrude, custom_code, file, group
- **Material presets**: steel/aluminium/brass/copper/gold/PLA/ABS/rubber/wood/glass — values listed in CLAUDE.md
- **Critical rule**: every scene write must keep the JSON valid; use the existing structure (metadata, environment, camera, lights, objects)

## Anti-patterns

- **Never** describe a scene without writing it. The user expects to see it.
- **Never** use `cylinder` with `openEnded: true` for visible shells — z-fighting. Use `lathe` with closed annular profile instead.
- **Always** `computeVertexNormals()` after merging custom_code geometry, or the surface goes black.
- **Always** auto-group assemblies with > 6 objects; flat lists become unmanageable in the scene panel.
- **Don't** invent component part numbers in the BOM — use real ones from RS, Mouser, McMaster, T-Motor, etc.

## Plugin context

This skill ships with eight subagents (engineer-designer, 3d-specialist, manager, 3d-modeler, 3d-printing, manufacturing, materials, cad-designer) and eight slash commands. The Node + Three.js server in the plugin root provides the live viewer. Project bundles use the `.3dap` JSON format (scene + docs + drawings in one file).

To install: register the plugin source path, then enable. See the plugin's `README.md` for full install instructions.
