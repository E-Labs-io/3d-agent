---
description: Pack the current project into one zip for sharing or backup
argument-hint: [project slug]
---

1. Project: "$ARGUMENTS", or the one shown in the viewer.
2. `cad_build(project, show=False)` so the outputs are current.
3. `project_pack(project)`.
4. Tell the user the zip path and size. It holds the model source, brief, drawings, BOM, STEP, STL and 3MF files, so the design can be rebuilt from it.
