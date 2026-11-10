---
description: Start a new design project
argument-hint: <project name>
---

Create a project for "$ARGUMENTS".

1. Make a slug from the name (lowercase, hyphens). Call `project_new(slug, title)`.
2. Call `cad_build(slug)` so the starter model appears in the viewer.
3. Tell the user the project folder and ask what they want to build, unless the request already says.
