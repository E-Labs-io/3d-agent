---
description: Run every design check on the current project and report pass or fail
argument-hint: "[project slug]"
---

1. Use the project named in "$ARGUMENTS", or the one shown in the viewer (`project_list` if unsure).
2. `cad_build(project)` so the checks run on current geometry.
3. `check_all(project)`.
4. Report the verdict, then each problem with its location and the size of the miss. Offer to fix them; do not change the model unless asked.
