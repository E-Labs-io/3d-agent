---
description: Save the current project as a single .3dap bundle (scene + docs + drawings)
argument-hint: "[output-path]"
allowed-tools: Bash, Read, Write
---

Save the current 3D project as a self-contained `.3dap` JSON bundle.

Output path (optional): **$ARGUMENTS** — defaults to `<project-slug>-<YYYY-MM-DD>.3dap` in the current directory.

1. If the 3D Agent server is running on port 3030, prefer the live API:
   ```bash
   curl -s http://localhost:3030/api/project/bundle > /tmp/3da-bundle.json
   ```

2. Otherwise, build the bundle manually by reading:
   - `scene/current.json` → bundle.scene
   - `deliverables/{slug}/*.md` → bundle.documents (one entry per file, with title/format/path/content)
   - `deliverables/{slug}/drawings/*.svg` → bundle.drawings

   The bundle structure:
   ```json
   {
     "format": "3d-agent-project",
     "version": "1.0",
     "metadata": { "name": "...", "projectSlug": "...", "exportedAt": "ISO-timestamp" },
     "scene": { ... },
     "documents": { "bom": { "title": "...", "format": "markdown", "path": "BOM.md", "content": "..." } },
     "drawings": { "01-front-elevation": { "title": "...", "format": "svg", "path": "drawings/01-front-elevation.svg", "content": "<svg>..." } }
   }
   ```

3. Write the bundle to the output path. Confirm to the user with file size.

A `.3dap` file is self-contained — sharable by email, version-controllable, and can be re-imported via the viewer's Project menu → "Open .3dap…".
