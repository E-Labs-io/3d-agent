---
description: Stop the 3D Agent live viewer
allowed-tools: Bash
---

Stop the viewer that `/3d-start` launched, and only that process:

```bash
PIDFILE="${THREED_AGENT_HOME:-$HOME/Documents/3D-Agent}/viewer.pid"; [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" && rm "$PIDFILE" && echo stopped || echo "no viewer started by /3d-start"
```

If there is no pid file but port 3030 is in use, tell the user which process holds it (`lsof -nP -iTCP:3030 -sTCP:LISTEN`) and let them decide. Do not kill a process you did not start.
