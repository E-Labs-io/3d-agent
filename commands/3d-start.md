---
description: Start the 3D Agent live viewer server (port 3030)
allowed-tools: Bash, Read
---

Start the 3D Agent server. Steps:

1. Check whether port 3030 is already in use:
   ```bash
   lsof -ti:3030 || echo "free"
   ```

2. If free, find the 3D Agent installation:
   - First try the current working directory (look for `package.json` mentioning `3d-agent` and a `server.js` plus `public/` and `scene/`).
   - If not present, fall back to the plugin's bundled location: `${CLAUDE_PLUGIN_ROOT}` (the directory containing this command's plugin manifest). That directory has its own `server.js`.
   - As a last resort, the canonical install at `/Users/tuck/Documents/E-Labs/Products/e_labs-claude/3D-Agent`.

3. Run dependencies install if `node_modules` is missing:
   ```bash
   cd <agent-dir> && npm install
   ```

4. Launch the server in the background:
   ```bash
   cd <agent-dir> && node server.js > /tmp/3d-agent.log 2>&1 &
   ```

5. Wait 1–2 seconds, then verify it's responding:
   ```bash
   curl -s http://localhost:3030/api/scene >/dev/null && echo "ready" || echo "failed"
   ```

6. Tell the user the viewer is at **http://localhost:3030** and that scene edits land in `<agent-dir>/scene/current.json`.

If the port is already in use, just confirm the existing server and skip the start.
