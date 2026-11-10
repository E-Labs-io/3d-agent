---
description: Full design workflow, from request to checked model, drawings and BOM
argument-hint: <what to design>
---

Design: $ARGUMENTS

Run the workflow, passing each stage's output to the next:

1. **engineer** agent: write `brief.md` with numbered requirements, load cases, materials and parts list. If the request is missing something only the user knows (what it holds, where it mounts, which printer), ask before starting, in one message.
2. **cad-builder** agent: build `model.py` from the brief and loop build, check, fix until `check_all` passes.
3. **electronics** agent, only if the brief has an electrical side: circuit, wiring diagram, power budget. Feed board and connector sizes back to cad-builder.
4. **analyst** agent: run every load case and report pass or fail per requirement. If anything fails, send the fix to cad-builder and re-run. Stop after three rounds and report what is still failing rather than looping forever.
5. **manager** agent: drawings, BOM, print estimate.

Finish with a short summary: what was built, the requirement table with results, BOM total and unpriced lines, print time, and where the files are. Make sure the viewer is running (`/3d-start`) so the user can see it.
