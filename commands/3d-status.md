---
description: Show 3D Agent viewer, toolbox and project status
allowed-tools: Bash, Read
---

Report, briefly:

1. Viewer: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3030/api/scene` (200 means running).
2. Toolbox: call `toolbox_status` and list tool groups that failed to load and optional programs that are missing.
3. Projects: call `project_list`. For the project shown in the viewer, call `check_all` and give the pass or fail verdict with its problems.
