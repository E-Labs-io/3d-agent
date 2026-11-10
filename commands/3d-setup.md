---
description: Install the 3D Agent toolbox environment and report which tool routes are available
allowed-tools: Bash, Read
---

Set up the toolbox. Steps:

1. Check `uv` is installed (`command -v uv`). If not, tell the user to install it from https://docs.astral.sh/uv/ and stop.

2. Sync the Python environment (about 900 MB on first run; tell the user before starting):
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}/toolbox" && uv sync --extra extras
   ```

3. Install the viewer's dependencies if `${CLAUDE_PLUGIN_ROOT}/node_modules` is missing:
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && npm install
   ```

4. Call the `toolbox_status` tool. Report which tool groups loaded and which optional programs are missing (KiCad, ngspice, a slicer, Graphviz, CalculiX), with the install command for each. Do not install any of them without the user asking.

5. Tell the user designs are kept in `~/Documents/3D-Agent` (or `$THREED_AGENT_HOME`).
