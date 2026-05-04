# 3D Agent — Claude Instructions

## What this project is

A live 3D design environment. Claude builds and modifies 3D objects by writing `scene/current.json`. The file is watched by `server.js`, which pushes updates to the Three.js viewer at `http://localhost:3030` via WebSocket. Changes appear instantly.

## How to interact with the scene

**To build or modify:** Write the updated `scene/current.json` using the Write tool. The viewer updates automatically — no server restart needed.

**To check the current state:** Read `scene/current.json`.

**The viewer runs at:** `http://localhost:3030` (start with `npm start` in this directory)

---

## Scene JSON format

```json
{
  "metadata": {
    "version": "1.0",
    "name": "Scene name",
    "units": "mm"
  },
  "environment": {
    "background": "#1a1f29",
    "grid": true,
    "axes": true,
    "shadows": true,
    "gridSize": 200,
    "gridDivisions": 20
  },
  "camera": {
    "position": [60, 60, 60],
    "target": [0, 0, 0],
    "fov": 45
  },
  "lights": [
    { "id": "ambient", "type": "ambient", "color": "#ffffff", "intensity": 0.4 },
    { "id": "key", "type": "directional", "color": "#ffffff", "intensity": 1.2,
      "position": [80, 120, 60], "castShadow": true }
  ],
  "objects": [ /* see object schema below */ ]
}
```

## Object schema

```json
{
  "id": "unique_snake_case_id",
  "name": "Human readable name",
  "type": "box",
  "params": { "width": 20, "height": 10, "depth": 15 },
  "material": {
    "type": "standard",
    "color": "#4a9eff",
    "metalness": 0.1,
    "roughness": 0.4,
    "transparent": false,
    "opacity": 1.0,
    "wireframe": false,
    "doubleSide": false,
    "flatShading": false,
    "emissive": "#000000",
    "emissiveIntensity": 1.0
  },
  "transform": {
    "position": [0, 5, 0],
    "rotation": [0, 0, 0],
    "scale": [1, 1, 1]
  },
  "visible": true,
  "castShadow": true,
  "receiveShadow": true
}
```

**Positioning convention:** place flat-bottom objects at `position.y = height/2` so the base rests on the ground plane (Y=0).

## Geometry types and params

```
box         → width, height, depth, widthSegments, heightSegments, depthSegments
sphere      → radius, widthSegments (32), heightSegments (16)
cylinder    → radiusTop, radiusBottom, height, radialSegments (32), openEnded
cone        → radius, height, radialSegments (32)
torus       → radius, tube, radialSegments (16), tubularSegments (64)
torusKnot  → radius, tube, tubularSegments, radialSegments, p, q
plane       → width, height
capsule     → radius, length
pipe        → outerRadius, innerRadius, height, segments
roundedBox  → width, height, depth, radius, segments
gear        → teeth, module_ (tooth size), thickness, pressureAngle (20), holeRadius
spring      → coilRadius, wireRadius, turns, height, segments
hex_bolt    → drive (hex across-flats), shankDiameter, shankLength, headHeight
nut         → drive, thickness, holeRadius
lathe       → points [[x,y], ...], segments (32)
extrude     → pathPoints [[x,y], ...], depth, bevel, bevelThickness, bevelSize
file        → url, format (stl|obj|gltf|glb|fbx|3ds|ply)
custom_code → geometry_code (Three.js JS string that returns a BufferGeometry)
group       → children (array of object schemas)
```

## Material presets

```
stainless_steel  → color:#c0c0c0, metalness:0.85, roughness:0.10
aluminium        → color:#b8b8c0, metalness:0.70, roughness:0.25
mild_steel       → color:#808080, metalness:0.75, roughness:0.30
brass            → color:#d4a017, metalness:0.80, roughness:0.20
copper           → color:#b87333, metalness:0.90, roughness:0.15
gold             → color:#ffd700, metalness:1.00, roughness:0.05
pla_white        → color:#f0f0f0, metalness:0.00, roughness:0.70
abs_grey         → color:#d0d0d0, metalness:0.00, roughness:0.60
rubber           → color:#2a2a2a, metalness:0.00, roughness:0.95
wood_pine        → color:#c8a87a, metalness:0.00, roughness:0.85
glass            → color:#a8d8f0, metalness:0.00, roughness:0.05, transparent:true, opacity:0.3
```

## Custom geometry code example

```json
{
  "type": "custom_code",
  "params": {
    "geometry_code": "const shape = new THREE.Shape(); shape.moveTo(-10,0); shape.lineTo(10,0); shape.lineTo(0,20); shape.closePath(); const geo = new THREE.ExtrudeGeometry(shape, {depth:5, bevelEnabled:false}); geo.rotateX(-Math.PI/2); geo.computeVertexNormals(); return geo;"
  }
}
```

## Agent specialisms

Read the relevant agent file before responding to specialist requests. The three "core" subagents handle full project workflows; the rest are reference material the core agents draw on.

### Core workflow agents

| Task | Agent file |
|------|-----------|
| Research and design a product end-to-end (function, materials, mechanics, electronics, DfM) | `agents/engineer-designer.md` |
| Take a design brief and build it in 3D / iterate / redesign | `agents/3d-specialist.md` |
| Produce BOMs, 2D plans, exploded views (2D + 3D animation), build instructions | `agents/manager.md` |

### Expertise reference

| Task | Agent file |
|------|-----------|
| Build / modify 3D geometry (basic) | `agents/3d-modeler.md` |
| 3D printing advice / analysis | `agents/3d-printing.md` |
| Manufacturing process / DFM | `agents/manufacturing.md` |
| Material selection | `agents/materials.md` |
| Precision CAD / tolerances | `agents/cad-designer.md` |

### Typical workflow

For a new product: **Engineer/Designer** writes a brief → **3D Specialist** builds it in `scene/current.json` → **Manager** produces BOM, plans, exploded views, build instructions.

For modifications to an existing design: skip straight to the **3D Specialist** (or **Engineer/Designer** if the change has design-level implications), then **Manager** updates the deliverables.

The 3D Specialist always auto-groups assemblies — read `agents/3d-modeler.md` § "Auto-grouping" for the spec on how groups are encoded in the scene JSON.

## Critical rules

1. **Always write scene/current.json** — never just describe the scene in text. Write it.
2. **Preserve existing objects** unless explicitly asked to remove them.
3. **All units are mm** unless `metadata.units` says otherwise.
4. **Object IDs are unique** — use `type_timestamp` format for new objects.
5. **Never leave malformed JSON** — validate mentally before writing.
6. **After every scene write**, briefly describe what changed.
7. **For analysis requests**, first check that the server is running and the object exists in the scene.
