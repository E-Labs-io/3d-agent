# 3D Agent

Live AI-powered 3D design environment for Claude Code. Build, modify, and export 3D objects via chat with a real-time viewer at `http://localhost:3030`.

A Claude Code plugin packaging the live viewer + Node server with eight subagents and eight slash commands for product-design workflows.

---

## Features

- **Live 3D viewer** at `http://localhost:3030` — Three.js, no build step. WebSocket pushes updates the moment Claude writes the scene file.
- **Scene-as-JSON** — `scene/current.json` is the source of truth. Claude writes; the viewer renders.
- **17 geometry types** — box / sphere / cylinder / cone / torus / lathe / extrude / gear / spring / hex_bolt / nut / pipe / capsule / custom_code (Three.js strings) / file (STL/OBJ/GLTF/GLB/FBX/3DS/PLY import) / group / plane.
- **Editor UI** — scene panel with hide/lock/duplicate per object, drag-to-group, undo/redo, environment controls, plan/section/elevation orthographic views, ruler overlays, and a Docs panel that splits the page vertically for live BOM/drawings reading.
- **Project bundles** — single `.3dap` JSON file with scene + all documents + all drawings. Sharable, version-controllable.
- **Three core workflow subagents** — Engineer/Designer → 3D Specialist → Manager, plus four expertise subagents (3d-modeler, 3d-printing, manufacturing, materials, cad-designer).
- **Eight slash commands** — `/3d-start`, `/3d-stop`, `/3d-new`, `/3d-design`, `/3d-bom`, `/3d-plans`, `/3d-bundle`, `/3d-status`.

---

## Install as a Claude Code plugin

The plugin lives in this directory. Register it as a local plugin:

### Option A — single user, current install location

Add this plugin to `~/.claude/settings.json`:

```json
{
  "plugins": {
    "3d-agent": {
      "source": "/Users/tuck/Documents/E-Labs/Products/e_labs-claude/3D-Agent",
      "enabled": true
    }
  }
}
```

Then restart Claude Code or run `/plugin reload`.

### Option B — Git-based marketplace (recommended for sharing)

1. Push this directory to a Git repo (e.g. `e-labs/3d-agent`)
2. From any Claude Code session: `/plugin marketplace add e-labs/3d-agent`
3. `/plugin install 3d-agent`

Updates are then `git pull` away — Claude Code re-pulls on next session start.

### Option C — symlink into ~/.claude/plugins/

```bash
ln -s "/Users/tuck/Documents/E-Labs/Products/e_labs-claude/3D-Agent" \
      "$HOME/.claude/plugins/3d-agent"
```

This makes the plugin available system-wide while leaving the source in the original location, so edits to `agents/`, `commands/`, `skills/`, or scene files take effect immediately.

### Verify install

```
/plugin list
```

You should see `3d-agent` listed with 8 agents, 8 commands, and 1 skill.

---

## First run

```bash
cd /Users/tuck/Documents/E-Labs/Products/e_labs-claude/3D-Agent
npm install
```

Then in any Claude Code session anywhere on your machine:

```
/3d-start
/3d-design "small desktop wind-up clock"
```

The Engineer/Designer writes the brief → 3D Specialist builds it in the viewer → Manager produces BOM and drawings.

---

## What's in this repo

```
3D-Agent/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest (Claude Code reads this)
├── agents/                  # 8 subagents
│   ├── engineer-designer.md
│   ├── 3d-specialist.md
│   ├── manager.md
│   ├── 3d-modeler.md
│   ├── 3d-printing.md
│   ├── manufacturing.md
│   ├── materials.md
│   └── cad-designer.md
├── commands/                # 8 slash commands
│   ├── 3d-start.md
│   ├── 3d-stop.md
│   ├── 3d-new.md
│   ├── 3d-design.md
│   ├── 3d-bom.md
│   ├── 3d-plans.md
│   ├── 3d-bundle.md
│   └── 3d-status.md
├── skills/3d-design/
│   └── SKILL.md             # Auto-activated when 3D design is requested
├── server.js                # Express + WebSocket + chokidar (port 3030)
├── package.json
├── public/                  # Three.js viewer (HTML/CSS/JS)
│   ├── index.html
│   ├── css/styles.css
│   └── js/{app.js, geometry-builders.js}
├── scene/
│   ├── current.json         # The live scene — Claude writes, viewer renders
│   └── default.json         # Fallback empty scene
├── deliverables/
│   └── {project-slug}/      # Per-project BOM/plans/docs/drawings
└── CLAUDE.md                # Instructions Claude reads when working in this dir
```

---

## Updating the plugin

Edits to any file in this directory take effect on next Claude Code session start (or `/plugin reload`). The Node server picks up scene-file changes live via chokidar; no restart needed for those.

For new agents, commands, or skills:

1. Add the file under `agents/`, `commands/`, or `skills/{name}/SKILL.md`
2. Update `.claude-plugin/plugin.json` to register it
3. `/plugin reload`

---

## License

MIT — see project root.

## Author

E-Labs (`tuck@pttrn.live`)
