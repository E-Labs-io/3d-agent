---
description: Start a fresh 3D scene (overwrites current scene)
argument-hint: "[project-name]"
allowed-tools: Bash, Write, Read
---

The user wants a fresh 3D project. Project name (optional): **$ARGUMENTS**

1. Locate the active 3D Agent install (current working directory if it has `scene/current.json`, else `${CLAUDE_PLUGIN_ROOT}`).

2. Confirm with the user that overwriting the current scene is OK if it's not empty.

3. Write a new minimal scene to `scene/current.json`:

```json
{
  "metadata": {
    "version": "1.0",
    "name": "$ARGUMENTS",
    "units": "mm",
    "description": "New project"
  },
  "environment": {
    "background": "#0a0d14",
    "grid": true,
    "axes": false,
    "shadows": true,
    "gridSize": 400,
    "gridDivisions": 20
  },
  "camera": {
    "position": [120, 120, 200],
    "target": [0, 50, 0],
    "fov": 45
  },
  "lights": [
    { "id": "ambient", "type": "ambient", "color": "#ffffff", "intensity": 0.4 },
    { "id": "key", "type": "directional", "color": "#ffffff", "intensity": 1.2, "position": [80,120,60], "castShadow": true },
    { "id": "fill", "type": "directional", "color": "#5577ff", "intensity": 0.4, "position": [-80,80,-80], "castShadow": false }
  ],
  "objects": [
    {
      "id": "ground_plane",
      "name": "Ground Plane",
      "type": "plane",
      "params": { "width": 400, "height": 400 },
      "material": { "type": "standard", "color": "#0d1320", "metalness": 0, "roughness": 1, "transparent": true, "opacity": 0.55 },
      "transform": { "position": [0, -1, 0], "rotation": [-90, 0, 0], "scale": [1, 1, 1] },
      "visible": true, "castShadow": false, "receiveShadow": true
    }
  ],
  "annotations": [],
  "measurements": []
}
```

4. If $ARGUMENTS is empty, default the name to "New Project".

5. If the server is running (port 3030), the viewer will pick up the new scene automatically. Otherwise tell the user to run `/3d-start`.

6. Suggest next steps: "Tell me what you want to build, or use `/3d-design <description>` to kick off the engineer/designer flow."
