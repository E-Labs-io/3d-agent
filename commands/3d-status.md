---
description: Show 3D Agent server + scene status
allowed-tools: Bash, Read
---

Report current 3D Agent state:

1. Server status — check port 3030:
   ```bash
   if lsof -ti:3030 >/dev/null 2>&1; then
     echo "✓ Server running (PID $(lsof -ti:3030))"
   else
     echo "✗ Server stopped"
   fi
   ```

2. If server is running, hit `/api/project/list` to see active project + all known projects:
   ```bash
   curl -s http://localhost:3030/api/project/list 2>/dev/null
   ```

3. Read `scene/current.json` (look in CWD first, then plugin root) and report:
   - Scene name
   - Object count (excluding `_isGroup` headers)
   - Group count
   - Triangle count if available

4. Check for deliverables:
   ```bash
   find deliverables -maxdepth 2 -name "*.md" -o -name "*.svg" 2>/dev/null | wc -l
   ```

5. Print a compact status block:
   ```
   3D Agent
   ========
   Server:    [running PID … | stopped]
   Viewer:    http://localhost:3030
   Project:   <name>
   Objects:   N (M groups)
   Docs:      X markdown, Y svgs
   ```

If the server is stopped suggest `/3d-start`. If no scene present suggest `/3d-new "Project Name"`.
