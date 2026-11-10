---
description: Start the 3D Agent live viewer (port 3030)
allowed-tools: Bash, Read
---

Start the viewer. Steps:

1. Check whether it is already up:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3030/api/scene
   ```
   If that prints `200`, say the viewer is already running at http://localhost:3030 and stop.

2. If `${CLAUDE_PLUGIN_ROOT}/node_modules` is missing, run `/3d-setup` first.

3. Start it and record the process id so `/3d-stop` can stop exactly this process:
   ```bash
   mkdir -p "${THREED_AGENT_HOME:-$HOME/Documents/3D-Agent}" && cd "${CLAUDE_PLUGIN_ROOT}" && (node server.js > "${THREED_AGENT_HOME:-$HOME/Documents/3D-Agent}/viewer.log" 2>&1 & echo $! > "${THREED_AGENT_HOME:-$HOME/Documents/3D-Agent}/viewer.pid")
   ```

4. Wait two seconds, repeat the check from step 1, and tell the user the viewer is at http://localhost:3030. If it failed, show the last lines of `viewer.log`.
