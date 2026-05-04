---
description: Stop the 3D Agent live viewer server
allowed-tools: Bash
---

Stop the 3D Agent server. Run:

```bash
PID=$(lsof -ti:3030 2>/dev/null)
if [ -n "$PID" ]; then
  kill $PID && echo "Stopped 3D Agent (PID $PID)"
else
  echo "No 3D Agent server running on port 3030"
fi
```

Confirm to the user with one short line.
