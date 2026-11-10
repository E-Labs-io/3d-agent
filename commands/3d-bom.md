---
description: Generate the bill of materials for the current project
argument-hint: [project slug]
---

1. Project: "$ARGUMENTS", or the one shown in the viewer.
2. `check_all(project)`. If it fails, say so and ask whether to continue.
3. `bom_make(project)`.
4. Report the line count, the known total, which lines are unpriced, and link the `bom.md` file. If `sourcing_status` shows no supplier keys, say prices need DigiKey, Mouser or Farnell keys and that links are provided instead.
