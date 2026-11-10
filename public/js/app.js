import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { TDSLoader } from 'three/addons/loaders/TDSLoader.js';
import { PLYLoader } from 'three/addons/loaders/PLYLoader.js';
import { STLExporter } from 'three/addons/exporters/STLExporter.js';
import { OBJExporter } from 'three/addons/exporters/OBJExporter.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { GeometryBuilders, analyzeGeometry } from '/js/geometry-builders.js';

// ── Three.js core setup ────────────────────────────────────────────────────

const canvas = document.getElementById('viewport');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

const scene = new THREE.Scene();
scene.background = new THREE.Color('#1a1f29');

const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100000);
camera.position.set(60, 60, 60);
camera.lookAt(0, 0, 0);

const orbitControls = new OrbitControls(camera, renderer.domElement);
orbitControls.enableDamping = true;
orbitControls.dampingFactor = 0.08;
orbitControls.screenSpacePanning = true;
orbitControls.maxPolarAngle = Math.PI;

const transformControls = new TransformControls(camera, renderer.domElement);
transformControls.addEventListener('dragging-changed', e => {
  orbitControls.enabled = !e.value;
});
transformControls.addEventListener('objectChange', () => {
  if (selectedObject) syncPropsFromObject(selectedObject);
});
scene.add(transformControls);

// ── Helpers ────────────────────────────────────────────────────────────────

let gridHelper = new THREE.GridHelper(200, 20, 0x444455, 0x2a2a3a);
scene.add(gridHelper);

let axesHelper = new THREE.AxesHelper(30);
scene.add(axesHelper);

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

// ── State ──────────────────────────────────────────────────────────────────

let currentScene = null;
let sceneObjects = new Map();  // id → THREE.Object3D
let selectedObject = null;
let selectedId = null;
let viewMode = 'solid';        // solid | wire | both
let shadingMode = 'material';  // material | flat | xray
let isMeasuring = false;
let measurePoints = [];
let units = 'mm';

// Undo / redo
const historyStack = [];
const redoStack = [];
const HISTORY_LIMIT = 50;
let historyMuted = false;

function pushHistory(label) {
  if (historyMuted || !currentScene) return;
  try {
    historyStack.push({ label, snapshot: JSON.stringify(currentScene) });
    if (historyStack.length > HISTORY_LIMIT) historyStack.shift();
    redoStack.length = 0;
    updateUndoRedoUI();
  } catch (e) { /* ignore */ }
}

function undo() {
  if (!historyStack.length || !currentScene) return;
  const current = JSON.stringify(currentScene);
  redoStack.push({ label: 'redo', snapshot: current });
  const entry = historyStack.pop();
  applySnapshot(entry.snapshot);
  toast(`Undo: ${entry.label}`);
  updateUndoRedoUI();
}

function redo() {
  if (!redoStack.length || !currentScene) return;
  const current = JSON.stringify(currentScene);
  historyStack.push({ label: 'undo', snapshot: current });
  const entry = redoStack.pop();
  applySnapshot(entry.snapshot);
  toast('Redo');
  updateUndoRedoUI();
}

function applySnapshot(snapshot) {
  historyMuted = true;
  try {
    const data = JSON.parse(snapshot);
    loadSceneJSON(data);
    // Persist to file so the scene file matches
    fetch('/api/scene', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: snapshot
    }).catch(() => {});
  } finally {
    historyMuted = false;
  }
}

function updateUndoRedoUI() {
  const u = document.getElementById('btn-undo');
  const r = document.getElementById('btn-redo');
  if (u) u.disabled = historyStack.length === 0;
  if (r) r.disabled = redoStack.length === 0;
}

// Projection / ortho-style views — uses a very narrow FOV at long range to
// emulate orthographic projection without refactoring the camera pipeline.
let savedPerspective = null;
let currentProjection = 'perspective';

function setProjection(mode) {
  if (currentProjection === mode) return;
  if (currentProjection === 'perspective') {
    savedPerspective = {
      pos: camera.position.toArray(),
      target: orbitControls.target.toArray(),
      fov: camera.fov,
      up: camera.up.toArray()
    };
  }
  currentProjection = mode;

  // Highlight active button
  ['btn-persp','btn-ortho-plan','btn-ortho-elev','btn-ortho-side'].forEach(id => {
    const el = document.getElementById(id); if (el) el.classList.remove('active');
  });

  if (mode === 'perspective') {
    document.getElementById('btn-persp')?.classList.add('active');
    if (savedPerspective) {
      camera.position.set(...savedPerspective.pos);
      orbitControls.target.set(...savedPerspective.target);
      camera.fov = savedPerspective.fov;
      camera.up.set(...savedPerspective.up);
    }
  } else {
    // Compute scene bounding box for view distance
    const box = new THREE.Box3();
    sceneObjects.forEach(o => box.expandByObject(o));
    if (box.isEmpty()) box.set(new THREE.Vector3(-100,-100,-100), new THREE.Vector3(100,100,100));
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const dist = maxDim * 35; // far away for narrow-FOV ortho effect
    camera.fov = 1.2;
    orbitControls.target.copy(center);
    if (mode === 'plan') {
      camera.position.set(center.x, center.y + dist, center.z);
      camera.up.set(0, 0, -1);
      document.getElementById('btn-ortho-plan')?.classList.add('active');
    } else if (mode === 'elevation') {
      camera.position.set(center.x, center.y, center.z + dist);
      camera.up.set(0, 1, 0);
      document.getElementById('btn-ortho-elev')?.classList.add('active');
    } else if (mode === 'section') {
      camera.position.set(center.x + dist, center.y, center.z);
      camera.up.set(0, 1, 0);
      document.getElementById('btn-ortho-side')?.classList.add('active');
    }
  }
  camera.updateProjectionMatrix();
  cameraManuallyMoved = true;
  toast(`View: ${mode}`);
  persistCamera();
}

// Environment controls modal
function openEnvModal() {
  if (!currentScene) return;
  const env = currentScene.environment || {};
  const lights = currentScene.lights || [];
  const findLight = (id) => lights.find(l => l.id === id) || {};

  document.getElementById('env-bg').value = env.background || '#0a0d14';
  document.getElementById('env-bg-bright').value = env._bgBrightness ?? 1;
  document.getElementById('env-bg-bright-val').textContent = (env._bgBrightness ?? 1).toFixed(2);

  const ambient = findLight('ambient');
  document.getElementById('env-ambient').value = ambient.intensity ?? 0.3;
  document.getElementById('env-ambient-val').textContent = (ambient.intensity ?? 0.3).toFixed(2);
  document.getElementById('env-ambient-color').value = ambient.color || '#c8d4ff';

  const key = findLight('key');
  document.getElementById('env-key').value = key.intensity ?? 1.45;
  document.getElementById('env-key-val').textContent = (key.intensity ?? 1.45).toFixed(2);

  const fill = findLight('fill');
  document.getElementById('env-fill').value = fill.intensity ?? 0.45;
  document.getElementById('env-fill-val').textContent = (fill.intensity ?? 0.45).toFixed(2);

  const rim = findLight('rim');
  document.getElementById('env-rim').value = rim.intensity ?? 0.5;
  document.getElementById('env-rim-val').textContent = (rim.intensity ?? 0.5).toFixed(2);

  document.getElementById('env-exposure').value = renderer.toneMappingExposure;
  document.getElementById('env-exposure-val').textContent = renderer.toneMappingExposure.toFixed(2);

  document.getElementById('env-grid').checked = env.grid !== false;
  document.getElementById('env-axes').checked = env.axes === true;
  document.getElementById('env-shadows').checked = env.shadows !== false;

  document.getElementById('env-modal').style.display = 'flex';
}

// ── Environment / view persistence ────────────────────────────────────────
const PREFS_KEY = '3d-agent-prefs';

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function savePrefs(patch) {
  try {
    const cur = loadPrefs() || {};
    localStorage.setItem(PREFS_KEY, JSON.stringify({ ...cur, ...patch }));
  } catch {}
}

function applySavedPrefs() {
  const p = loadPrefs();
  if (!p) return;
  if (!currentScene) return;
  if (!currentScene.environment) currentScene.environment = {};
  const env = currentScene.environment;

  if (p.bgColor) env.background = p.bgColor;
  if (p.bgBrightness !== undefined) env._bgBrightness = p.bgBrightness;
  if (p.bgColor) {
    const bgColor = new THREE.Color(p.bgColor).multiplyScalar(p.bgBrightness ?? 1);
    scene.background = bgColor;
  }
  const updateLightDef = (id, intensity, color) => {
    const def = (currentScene.lights || []).find(l => l.id === id);
    if (def) {
      if (intensity !== undefined) def.intensity = intensity;
      if (color) def.color = color;
    }
    if (intensity !== undefined) {
      const light = id === 'ambient'
        ? scene.children.find(c => c.isAmbientLight)
        : scene.children.find(c => c.isDirectionalLight && c.userData?.id === id);
      if (light) light.intensity = intensity;
      if (light && color) light.color = new THREE.Color(color);
    }
  };
  if (p.ambient !== undefined) updateLightDef('ambient', p.ambient, p.ambientColor);
  if (p.key !== undefined)     updateLightDef('key', p.key);
  if (p.fill !== undefined)    updateLightDef('fill', p.fill);
  if (p.rim !== undefined)     updateLightDef('rim', p.rim);

  if (p.exposure !== undefined) renderer.toneMappingExposure = p.exposure;
  if (p.grid !== undefined)    { gridHelper.visible = p.grid; env.grid = p.grid; }
  if (p.axes !== undefined)    { axesHelper.visible = p.axes; env.axes = p.axes; }
  if (p.shadows !== undefined) { renderer.shadowMap.enabled = p.shadows; env.shadows = p.shadows; }

  // Toolbar button states
  document.getElementById('btn-grid')?.classList.toggle('active', !!gridHelper.visible);
  document.getElementById('btn-axes')?.classList.toggle('active', !!axesHelper.visible);
  document.getElementById('btn-shadows')?.classList.toggle('active', !!renderer.shadowMap.enabled);

  // View modes
  if (p.viewMode && p.viewMode !== viewMode)        setViewMode(p.viewMode);
  if (p.shadingMode && p.shadingMode !== shadingMode) setShadingMode(p.shadingMode);

  // Camera state — apply only if user had moved it before
  if (p.camera) {
    cameraManuallyMoved = true;
    camera.position.set(...p.camera.pos);
    orbitControls.target.set(...p.camera.target);
    camera.fov = p.camera.fov;
    camera.up.set(...(p.camera.up || [0,1,0]));
    camera.updateProjectionMatrix();
    if (p.projection && p.projection !== 'perspective') {
      currentProjection = p.projection;
      ['btn-persp','btn-ortho-plan','btn-ortho-elev','btn-ortho-side'].forEach(id => {
        document.getElementById(id)?.classList.remove('active');
      });
      const map = { perspective: 'btn-persp', plan: 'btn-ortho-plan', elevation: 'btn-ortho-elev', section: 'btn-ortho-side' };
      document.getElementById(map[p.projection])?.classList.add('active');
    }
  }
}

function persistEnvFromUI() {
  savePrefs({
    bgColor: document.getElementById('env-bg').value,
    bgBrightness: parseFloat(document.getElementById('env-bg-bright').value),
    ambient: parseFloat(document.getElementById('env-ambient').value),
    ambientColor: document.getElementById('env-ambient-color').value,
    key: parseFloat(document.getElementById('env-key').value),
    fill: parseFloat(document.getElementById('env-fill').value),
    rim: parseFloat(document.getElementById('env-rim').value),
    exposure: parseFloat(document.getElementById('env-exposure').value),
    grid: document.getElementById('env-grid').checked,
    axes: document.getElementById('env-axes').checked,
    shadows: document.getElementById('env-shadows').checked
  });
}

function persistCamera() {
  savePrefs({
    camera: {
      pos: camera.position.toArray(),
      target: orbitControls.target.toArray(),
      fov: camera.fov,
      up: camera.up.toArray()
    },
    projection: currentProjection
  });
}

function onEnvChange() {
  if (!currentScene) return;
  if (!currentScene.environment) currentScene.environment = {};
  const env = currentScene.environment;

  // Background colour scaled by brightness
  const bg = document.getElementById('env-bg').value;
  const bright = parseFloat(document.getElementById('env-bg-bright').value);
  document.getElementById('env-bg-bright-val').textContent = bright.toFixed(2);
  env.background = bg;
  env._bgBrightness = bright;
  const bgColor = new THREE.Color(bg).multiplyScalar(bright);
  scene.background = bgColor;

  // Ambient
  const ambI = parseFloat(document.getElementById('env-ambient').value);
  document.getElementById('env-ambient-val').textContent = ambI.toFixed(2);
  const ambColor = document.getElementById('env-ambient-color').value;
  const ambLight = scene.children.find(c => c.isAmbientLight);
  if (ambLight) {
    ambLight.intensity = ambI;
    ambLight.color = new THREE.Color(ambColor);
  }
  const ambDef = (currentScene.lights || []).find(l => l.id === 'ambient');
  if (ambDef) { ambDef.intensity = ambI; ambDef.color = ambColor; }

  // Key/fill/rim directional intensities
  const setDirIntensity = (id, value, valEl) => {
    document.getElementById(valEl).textContent = value.toFixed(2);
    const def = (currentScene.lights || []).find(l => l.id === id);
    if (def) def.intensity = value;
    const light = scene.children.find(c => c.isDirectionalLight && c.userData?.id === id);
    if (light) light.intensity = value;
  };
  setDirIntensity('key',  parseFloat(document.getElementById('env-key').value),  'env-key-val');
  setDirIntensity('fill', parseFloat(document.getElementById('env-fill').value), 'env-fill-val');
  setDirIntensity('rim',  parseFloat(document.getElementById('env-rim').value),  'env-rim-val');

  // Exposure
  const exposure = parseFloat(document.getElementById('env-exposure').value);
  document.getElementById('env-exposure-val').textContent = exposure.toFixed(2);
  renderer.toneMappingExposure = exposure;

  // Helpers
  const grid = document.getElementById('env-grid').checked;
  const axes = document.getElementById('env-axes').checked;
  const shadows = document.getElementById('env-shadows').checked;
  gridHelper.visible = grid;
  axesHelper.visible = axes;
  renderer.shadowMap.enabled = shadows;
  env.grid = grid;
  env.axes = axes;
  env.shadows = shadows;

  // Persist
  persistEnvFromUI();
}

// ── Material factories ────────────────────────────────────────────────────

function makeMaterial(matDef = {}) {
  const type = matDef.type || 'standard';
  const color = new THREE.Color(matDef.color || '#4a9eff');
  const props = {
    color,
    metalness: matDef.metalness ?? 0,
    roughness: matDef.roughness ?? 0.5,
    transparent: matDef.transparent ?? false,
    opacity: matDef.opacity ?? 1,
    wireframe: matDef.wireframe ?? false,
    side: matDef.doubleSide ? THREE.DoubleSide : THREE.FrontSide,
    flatShading: matDef.flatShading ?? false,
    depthWrite: matDef.depthWrite !== undefined ? matDef.depthWrite : !(matDef.transparent && (matDef.opacity ?? 1) < 0.95),
  };
  if (matDef.emissive) {
    props.emissive = new THREE.Color(matDef.emissive);
    props.emissiveIntensity = matDef.emissiveIntensity ?? 1;
  }
  if (matDef.polygonOffset) {
    props.polygonOffset = true;
    props.polygonOffsetFactor = matDef.polygonOffsetFactor ?? -1;
    props.polygonOffsetUnits = matDef.polygonOffsetUnits ?? -1;
  }

  switch (type) {
    case 'phong':    return new THREE.MeshPhongMaterial(props);
    case 'basic':    return new THREE.MeshBasicMaterial({ color, wireframe: props.wireframe, transparent: props.transparent, opacity: props.opacity, side: props.side });
    case 'toon':     return new THREE.MeshToonMaterial(props);
    case 'physical': return new THREE.MeshPhysicalMaterial({ ...props, clearcoat: matDef.clearcoat ?? 0, transmission: matDef.transmission ?? 0 });
    default:         return new THREE.MeshStandardMaterial(props);
  }
}

function applyViewMode(mesh) {
  if (!mesh.isMesh) return;
  mesh.material.wireframe = viewMode === 'wire';
}

// ── Geometry factory ───────────────────────────────────────────────────────

function buildGeometry(objDef) {
  const type = objDef.type;
  const params = objDef.params || {};
  const builder = GeometryBuilders[type];
  if (builder) return builder(params);

  // Unknown type fallback
  console.warn(`Unknown geometry type: ${type} — using box`);
  return new THREE.BoxGeometry(5, 5, 5);
}

// ── Scene loading ────────────────────────────────────────────────────────

function applyTransform(obj3d, transform = {}) {
  const p = transform.position || [0, 0, 0];
  const r = transform.rotation || [0, 0, 0];
  const s = transform.scale    || [1, 1, 1];
  obj3d.position.set(...p);
  obj3d.rotation.set(r[0] * Math.PI / 180, r[1] * Math.PI / 180, r[2] * Math.PI / 180);
  obj3d.scale.set(...s);
}

function loadSceneJSON(sceneData) {
  currentScene = sceneData;

  // Background
  if (sceneData.environment?.background) {
    scene.background = new THREE.Color(sceneData.environment.background);
  }

  // Grid
  const showGrid = sceneData.environment?.grid !== false;
  gridHelper.visible = showGrid;
  const showAxes = sceneData.environment?.axes !== false;
  axesHelper.visible = showAxes;

  // Lights — remove all existing, rebuild
  scene.children.filter(c => c.isLight).forEach(l => scene.remove(l));
  (sceneData.lights || []).forEach(lightDef => addLight(lightDef));

  // Objects — diff update (add new, update changed, remove deleted)
  const newIds = new Set((sceneData.objects || []).map(o => o.id));

  // Remove deleted objects
  for (const [id, obj] of sceneObjects) {
    if (!newIds.has(id)) {
      scene.remove(obj);
      sceneObjects.delete(id);
      if (selectedId === id) deselect();
    }
  }

  // Add or update objects (skip group headers — they're UI-only)
  (sceneData.objects || []).forEach(objDef => {
    if (objDef._isGroup) return;
    if (sceneObjects.has(objDef.id)) {
      updateObject(objDef);
    } else {
      addObject(objDef);
    }
  });

  // Camera
  if (sceneData.camera && !cameraManuallyMoved) {
    const cp = sceneData.camera.position || [60, 60, 60];
    const ct = sceneData.camera.target || [0, 0, 0];
    camera.position.set(...cp);
    orbitControls.target.set(...ct);
    camera.fov = sceneData.camera.fov || 45;
    camera.updateProjectionMatrix();
  }

  // Units
  if (sceneData.metadata?.units) {
    units = sceneData.metadata.units;
    document.getElementById('unit-select').value = units;
  }

  rebuildObjectTree();
  updateSceneStats();
  updateScenePanel();
  syncUnitDisplay();
}

function addLight(def) {
  let light;
  const color = new THREE.Color(def.color || '#ffffff');
  const intensity = def.intensity ?? 1;

  switch (def.type) {
    case 'ambient':     light = new THREE.AmbientLight(color, intensity); break;
    case 'directional': light = new THREE.DirectionalLight(color, intensity); break;
    case 'point':       light = new THREE.PointLight(color, intensity, def.distance || 0); break;
    case 'spot':        light = new THREE.SpotLight(color, intensity); break;
    default:            light = new THREE.AmbientLight(color, intensity);
  }

  if (def.position) light.position.set(...def.position);
  if (def.castShadow) {
    light.castShadow = true;
    if (light.shadow) {
      light.shadow.mapSize.set(2048, 2048);
      light.shadow.camera.near = 0.5;
      light.shadow.camera.far = 1000;
      if (light.shadow.camera.left !== undefined) {
        light.shadow.camera.left = light.shadow.camera.bottom = -150;
        light.shadow.camera.right = light.shadow.camera.top = 150;
      }
    }
  }
  light.userData.id = def.id;
  scene.add(light);
}

function addObject(objDef) {
  let obj3d;

  if (objDef.type === 'file') {
    loadExternalFile(objDef);
    return;
  }
  if (objDef.type === 'group') {
    obj3d = new THREE.Group();
    (objDef.children || []).forEach(child => {
      const childMesh = buildMesh(child);
      if (childMesh) obj3d.add(childMesh);
    });
  } else {
    obj3d = buildMesh(objDef);
  }

  if (!obj3d) return;
  obj3d.userData.id = objDef.id;
  obj3d.userData.name = objDef.name || objDef.id;
  obj3d.name = objDef.name || objDef.id;
  applyTransform(obj3d, objDef.transform);
  obj3d.visible = objDef.visible !== false;
  if (obj3d.isMesh) {
    obj3d.castShadow = objDef.castShadow !== false;
    obj3d.receiveShadow = objDef.receiveShadow !== false;
  }

  scene.add(obj3d);
  sceneObjects.set(objDef.id, obj3d);
}

function buildMesh(objDef) {
  const geo = buildGeometry(objDef);
  if (!geo) return null;
  const mat = makeMaterial(objDef.material || {});
  const mesh = new THREE.Mesh(geo, mat);
  mesh.userData.objDef = objDef;
  // Render transparent shells last so opaque interior parts are not occluded
  if (mat.transparent && mat.opacity < 0.95) {
    mesh.renderOrder = (objDef.material?.renderOrder ?? 1);
  }

  if (viewMode === 'wire') mat.wireframe = true;
  if (viewMode === 'both') {
    const wireMat = new THREE.MeshBasicMaterial({ color: 0x888888, wireframe: true, opacity: 0.3, transparent: true });
    const wireMesh = new THREE.Mesh(geo, wireMat);
    mesh.add(wireMesh);
  }
  if (shadingMode === 'xray') {
    mat.transparent = true;
    mat.opacity = 0.25;
  }

  return mesh;
}

function updateObject(objDef) {
  const existing = sceneObjects.get(objDef.id);
  if (!existing) { addObject(objDef); return; }

  // Update transform
  applyTransform(existing, objDef.transform);
  existing.visible = objDef.visible !== false;
  existing.name = objDef.name || objDef.id;
  existing.userData.name = existing.name;

  // Update shadow flags
  if (existing.isMesh) {
    existing.castShadow = objDef.castShadow !== false;
    existing.receiveShadow = objDef.receiveShadow !== false;
  }

  // Update material on mesh
  if (existing.isMesh && objDef.material) {
    existing.material.dispose();
    existing.material = makeMaterial(objDef.material);
    if (viewMode === 'wire') existing.material.wireframe = true;
    if (shadingMode === 'xray') { existing.material.transparent = true; existing.material.opacity = 0.25; }
  }

  // Rebuild geometry if params changed (simple deep-equal check)
  const oldDef = existing.userData.objDef || {};
  if (JSON.stringify(oldDef.params) !== JSON.stringify(objDef.params) || oldDef.type !== objDef.type) {
    if (existing.isMesh) {
      existing.geometry.dispose();
      existing.geometry = buildGeometry(objDef);
    }
    existing.userData.objDef = objDef;
  }

  if (selectedId === objDef.id) syncPropsFromObject(existing);
}

// ── External file loading ─────────────────────────────────────────────────

function loadExternalFile(objDef) {
  const url = objDef.url;
  const ext = (objDef.format || url.split('.').pop()).toLowerCase();
  showLoading(`Loading ${ext.toUpperCase()}...`);

  const onLoad = (geo) => {
    hideLoading();
    let obj3d;
    if (geo.isGroup || geo.isObject3D) {
      obj3d = geo;
      obj3d.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
    } else {
      const mat = makeMaterial(objDef.material || { color: '#aaaaaa', metalness: 0.1, roughness: 0.5 });
      obj3d = new THREE.Mesh(geo, mat);
      obj3d.castShadow = true;
      obj3d.receiveShadow = true;
    }
    obj3d.userData.id = objDef.id;
    obj3d.userData.name = objDef.name || objDef.id;
    obj3d.name = obj3d.userData.name;
    applyTransform(obj3d, objDef.transform);

    // Auto-center and fit on first import
    if (objDef.autoCenter !== false) {
      const box = new THREE.Box3().setFromObject(obj3d);
      const center = box.getCenter(new THREE.Vector3());
      obj3d.position.sub(center);
      fitObjectInView(obj3d);
    }

    scene.add(obj3d);
    sceneObjects.set(objDef.id, obj3d);
    rebuildObjectTree();
    updateSceneStats();
    toast(`Imported ${obj3d.name}`, 'success');
  };

  const onError = (e) => { hideLoading(); toast(`Import failed: ${e.message || e}`, 'error'); };

  switch (ext) {
    case 'stl': new STLLoader().load(url, onLoad, null, onError); break;
    case 'obj': new OBJLoader().load(url, onLoad, null, onError); break;
    case 'gltf':
    case 'glb': new GLTFLoader().load(url, g => onLoad(g.scene), null, onError); break;
    case 'fbx': new FBXLoader().load(url, onLoad, null, onError); break;
    case '3ds': new TDSLoader().load(url, onLoad, null, onError); break;
    case 'ply': new PLYLoader().load(url, onLoad, null, onError); break;
    default: toast(`Unsupported format: ${ext}`, 'error'); hideLoading();
  }
}

// ── Selection ─────────────────────────────────────────────────────────────

function select(id) {
  // Respect locked
  const def = currentScene?.objects?.find(o => o.id === id);
  if (def?._locked) return;
  deselect();
  selectedId = id;
  selectedObject = sceneObjects.get(id);
  if (!selectedObject) return;

  // Highlight
  selectedObject.traverse(c => {
    if (c.isMesh) {
      c.userData._origMat = c.material;
      const hl = c.material.clone();
      hl.emissive = new THREE.Color(0x224466);
      hl.emissiveIntensity = 0.3;
      c.material = hl;
    }
  });

  transformControls.attach(selectedObject);
  syncPropsFromObject(selectedObject);
  updateObjectTree(id);

  const objDef = currentScene?.objects?.find(o => o.id === id);
  document.getElementById('status-selected').textContent = `Selected: ${selectedObject.name}`;
}

function deselect() {
  if (selectedObject) {
    selectedObject.traverse(c => {
      if (c.isMesh && c.userData._origMat) {
        c.material.dispose();
        c.material = c.userData._origMat;
        delete c.userData._origMat;
      }
    });
  }
  transformControls.detach();
  selectedObject = null;
  selectedId = null;
  document.getElementById('no-selection').style.display = '';
  document.getElementById('props-content').style.display = 'none';
  document.getElementById('no-selection-mat').style.display = '';
  document.getElementById('material-content').style.display = 'none';
  document.getElementById('status-selected').textContent = '—';
  updateObjectTree(null);
}

// ── Props panel sync ──────────────────────────────────────────────────────

function syncPropsFromObject(obj) {
  document.getElementById('no-selection').style.display = 'none';
  document.getElementById('props-content').style.display = '';
  document.getElementById('no-selection-mat').style.display = 'none';
  document.getElementById('material-content').style.display = '';

  document.getElementById('prop-name').value = obj.name;
  document.getElementById('pos-x').value = obj.position.x.toFixed(3);
  document.getElementById('pos-y').value = obj.position.y.toFixed(3);
  document.getElementById('pos-z').value = obj.position.z.toFixed(3);
  document.getElementById('rot-x').value = (obj.rotation.x * 180 / Math.PI).toFixed(2);
  document.getElementById('rot-y').value = (obj.rotation.y * 180 / Math.PI).toFixed(2);
  document.getElementById('rot-z').value = (obj.rotation.z * 180 / Math.PI).toFixed(2);
  document.getElementById('scl-x').value = obj.scale.x.toFixed(4);
  document.getElementById('scl-y').value = obj.scale.y.toFixed(4);
  document.getElementById('scl-z').value = obj.scale.z.toFixed(4);
  document.getElementById('prop-visible').checked = obj.visible;
  if (obj.isMesh) {
    document.getElementById('prop-cast-shadow').checked = obj.castShadow;
    document.getElementById('prop-receive-shadow').checked = obj.receiveShadow;
  }

  // Bounding box dimensions
  const box = new THREE.Box3().setFromObject(obj);
  const size = new THREE.Vector3();
  box.getSize(size);
  const factor = unitFactor();
  document.getElementById('dimensions-content').innerHTML =
    `W: ${(size.x / factor).toFixed(2)} ${units}<br>` +
    `H: ${(size.y / factor).toFixed(2)} ${units}<br>` +
    `D: ${(size.z / factor).toFixed(2)} ${units}`;

  // Material panel
  const mat = obj.isMesh ? obj.material : null;
  if (mat) {
    const colorHex = '#' + mat.color?.getHexString();
    document.getElementById('mat-color-swatch').style.background = colorHex;
    document.getElementById('mat-color-text').value = colorHex;
    document.getElementById('mat-metalness').value = mat.metalness ?? 0;
    document.getElementById('mat-metalness-val').textContent = (mat.metalness ?? 0).toFixed(2);
    document.getElementById('mat-roughness').value = mat.roughness ?? 0.5;
    document.getElementById('mat-roughness-val').textContent = (mat.roughness ?? 0.5).toFixed(2);
    document.getElementById('mat-opacity').value = mat.opacity ?? 1;
    document.getElementById('mat-opacity-val').textContent = (mat.opacity ?? 1).toFixed(2);
    document.getElementById('mat-transparent').checked = mat.transparent ?? false;
    document.getElementById('mat-wireframe').checked = mat.wireframe ?? false;
    document.getElementById('mat-double-side').checked = mat.side === THREE.DoubleSide;
    document.getElementById('mat-flat-shading').checked = mat.flatShading ?? false;
    const emissiveHex = '#' + (mat.emissive?.getHexString() || '000000');
    document.getElementById('mat-emissive-swatch').style.background = emissiveHex;
    document.getElementById('mat-emissive-text').value = emissiveHex;
    document.getElementById('mat-emissive-intensity').value = mat.emissiveIntensity ?? 1;
    document.getElementById('mat-emissive-intensity-val').textContent = (mat.emissiveIntensity ?? 1).toFixed(1);
  }
}

// ── Object tree ────────────────────────────────────────────────────────────

const typeIcons = { box: '📦', sphere: '⚾', cylinder: '🥫', cone: '🔺', torus: '🍩', plane: '▬', gear: '⚙️', spring: '🌀', pipe: '🔧', hex_bolt: '🔩', nut: '🔩', file: '📂', group: '📁', custom_code: '⌨️' };

function rebuildObjectTree() {
  const tree = document.getElementById('object-tree');
  tree.innerHTML = '';
  if (!currentScene?.objects?.length) {
    tree.innerHTML = '<div style="padding:12px;color:var(--muted);font-size:11px;text-align:center;">No objects in scene</div>';
    return;
  }

  // Build a map of group → children
  const groups = new Map();
  const ungrouped = [];
  currentScene.objects.forEach(def => {
    if (def._groupId) {
      if (!groups.has(def._groupId)) groups.set(def._groupId, []);
      groups.get(def._groupId).push(def);
    } else if (def._isGroup) {
      // group header — render with its children below
      ungrouped.push(def);
    } else {
      ungrouped.push(def);
    }
  });

  ungrouped.forEach(def => {
    const item = renderTreeItem(def);
    tree.appendChild(item);
    if (def._isGroup && !def._collapsed && groups.has(def.id)) {
      groups.get(def.id).forEach(child => {
        const childEl = renderTreeItem(child, true);
        tree.appendChild(childEl);
      });
    }
  });
}

function renderTreeItem(def, inGroup = false) {
  const item = document.createElement('div');
  const classes = ['obj-item'];
  if (def.id === selectedId) classes.push('selected');
  if (def.visible === false) classes.push('hidden');
  if (def._locked) classes.push('locked');
  if (def._isGroup) classes.push('group-header');
  if (inGroup) classes.push('in-group');
  item.className = classes.join(' ');
  item.dataset.id = def.id;
  item.draggable = !def._locked;

  const visIcon = def.visible !== false ? '👁' : '⊘';
  const lockIcon = def._locked ? '🔒' : '🔓';
  const groupToggle = def._isGroup
    ? `<button class="group-toggle" title="Collapse/expand">${def._collapsed ? '▶' : '▼'}</button>`
    : '';

  item.innerHTML = `
    ${groupToggle}
    <span class="obj-icon">${def._isGroup ? '📁' : (typeIcons[def.type] || '⬜')}</span>
    <span class="obj-name">${def.name || def.id}</span>
    <span class="obj-type">${def._isGroup ? 'group' : def.type}</span>
    <span class="obj-actions">
      <button class="act-btn vis-btn" title="Toggle visibility">${visIcon}</button>
      <button class="act-btn lock-btn ${def._locked ? 'active' : ''}" title="Lock / unlock">${lockIcon}</button>
      <button class="act-btn dup-btn" title="Duplicate">⎘</button>
    </span>
  `;

  item.addEventListener('click', (e) => {
    const t = e.target;
    if (t.classList.contains('vis-btn')) { toggleVisibility(def.id); return; }
    if (t.classList.contains('lock-btn')) { toggleLock(def.id); return; }
    if (t.classList.contains('dup-btn')) { duplicateObject(def.id); return; }
    if (t.classList.contains('group-toggle')) { toggleGroupCollapse(def.id); return; }
    if (def._locked) return; // can't select locked
    if (selectedId === def.id) deselect();
    else select(def.id);
  });
  item.addEventListener('contextmenu', e => { e.preventDefault(); select(def.id); showContextMenu(e.clientX, e.clientY); });

  // Drag-and-drop reordering / grouping
  item.addEventListener('dragstart', (e) => {
    if (def._locked) { e.preventDefault(); return; }
    item.classList.add('dragging');
    e.dataTransfer.setData('text/plain', def.id);
    e.dataTransfer.effectAllowed = 'move';
  });
  item.addEventListener('dragend', () => item.classList.remove('dragging'));
  item.addEventListener('dragover', (e) => { e.preventDefault(); item.classList.add('drop-target'); });
  item.addEventListener('dragleave', () => item.classList.remove('drop-target'));
  item.addEventListener('drop', (e) => {
    e.preventDefault();
    item.classList.remove('drop-target');
    const draggedId = e.dataTransfer.getData('text/plain');
    if (draggedId && draggedId !== def.id) {
      // Modifier+drop = group; plain drop = reorder
      if (e.altKey || e.shiftKey) groupTwo(draggedId, def.id);
      else reorderItem(draggedId, def.id);
    }
  });

  return item;
}

function updateObjectTree(selectedId) {
  document.querySelectorAll('.obj-item').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === selectedId);
  });
}

function toggleVisibility(id) {
  pushHistory('Toggle visibility');
  const obj = sceneObjects.get(id);
  if (obj) obj.visible = !obj.visible;
  if (currentScene?.objects) {
    const def = currentScene.objects.find(o => o.id === id);
    if (def) {
      def.visible = !(def.visible !== false);
      if (def._isGroup) {
        // toggle all children
        currentScene.objects.forEach(c => {
          if (c._groupId === id) {
            c.visible = def.visible;
            const childObj = sceneObjects.get(c.id);
            if (childObj) childObj.visible = def.visible;
          }
        });
      }
    }
  }
  rebuildObjectTree();
}

function toggleLock(id) {
  pushHistory('Toggle lock');
  const def = currentScene?.objects.find(o => o.id === id);
  if (def) def._locked = !def._locked;
  if (selectedId === id) deselect();
  rebuildObjectTree();
}

function duplicateObject(id) {
  pushHistory('Duplicate');
  const def = currentScene?.objects.find(o => o.id === id);
  if (!def) return;
  const copy = JSON.parse(JSON.stringify(def));
  copy.id = def.id + '_copy_' + Date.now().toString(36);
  copy.name = (def.name || def.id) + ' (copy)';
  if (copy.transform?.position) {
    copy.transform.position = [
      (copy.transform.position[0] || 0) + 20,
      (copy.transform.position[1] || 0),
      (copy.transform.position[2] || 0) + 20
    ];
  }
  delete copy._locked;
  // insert immediately after original
  const idx = currentScene.objects.indexOf(def);
  currentScene.objects.splice(idx + 1, 0, copy);
  addObject(copy);
  rebuildObjectTree();
  updateSceneStats();
  toast(`Duplicated "${def.name || def.id}"`);
}

function reorderItem(draggedId, targetId) {
  pushHistory('Reorder');
  const objs = currentScene.objects;
  const fromIdx = objs.findIndex(o => o.id === draggedId);
  const toIdx = objs.findIndex(o => o.id === targetId);
  if (fromIdx < 0 || toIdx < 0) return;
  const [moved] = objs.splice(fromIdx, 1);
  objs.splice(toIdx, 0, moved);
  rebuildObjectTree();
}

function groupTwo(idA, idB) {
  // If B is a group, add A to it; otherwise create a new group containing both
  pushHistory('Group');
  const objs = currentScene.objects;
  const defA = objs.find(o => o.id === idA);
  const defB = objs.find(o => o.id === idB);
  if (!defA || !defB) return;

  if (defB._isGroup) {
    defA._groupId = defB.id;
  } else {
    const groupId = 'group_' + Date.now().toString(36);
    const groupDef = {
      id: groupId,
      name: 'New Group',
      _isGroup: true,
      _collapsed: false,
      type: 'group',
      visible: true
    };
    const idxB = objs.indexOf(defB);
    objs.splice(idxB, 0, groupDef);
    defA._groupId = groupId;
    defB._groupId = groupId;
  }
  rebuildObjectTree();
}

function toggleGroupCollapse(id) {
  const def = currentScene?.objects.find(o => o.id === id);
  if (def?._isGroup) {
    def._collapsed = !def._collapsed;
    rebuildObjectTree();
  }
}

function ungroupSelected() {
  if (!selectedId) return;
  const def = currentScene?.objects.find(o => o.id === selectedId);
  if (!def?._isGroup) return;
  pushHistory('Ungroup');
  currentScene.objects.forEach(o => { if (o._groupId === def.id) delete o._groupId; });
  const idx = currentScene.objects.indexOf(def);
  currentScene.objects.splice(idx, 1);
  rebuildObjectTree();
}

// ── View modes ────────────────────────────────────────────────────────────

function setViewMode(mode) {
  viewMode = mode;
  savePrefs({ viewMode: mode });
  ['solid', 'wire', 'both'].forEach(m => document.getElementById(`btn-${m}`).classList.toggle('active', m === mode));
  sceneObjects.forEach((obj) => {
    obj.traverse(c => {
      if (!c.isMesh) return;
      if (mode === 'wire') { c.material.wireframe = true; }
      else if (mode === 'solid') {
        c.material.wireframe = false;
        // Remove any wire overlay children added by 'both' mode
        const wireKids = c.children.filter(k => k.isMesh && k.material.wireframe);
        wireKids.forEach(k => { k.geometry.dispose(); k.material.dispose(); c.remove(k); });
      } else if (mode === 'both') {
        c.material.wireframe = false;
        if (!c.children.some(k => k.isMesh && k.material.wireframe)) {
          const wireMat = new THREE.MeshBasicMaterial({ color: 0x888888, wireframe: true, opacity: 0.25, transparent: true });
          c.add(new THREE.Mesh(c.geometry, wireMat));
        }
      }
    });
  });
}

function setShadingMode(mode) {
  shadingMode = mode;
  savePrefs({ shadingMode: mode });
  ['material', 'flat', 'xray'].forEach(m => document.getElementById(`btn-${m}`).classList.toggle('active', m === mode));
  sceneObjects.forEach(obj => {
    obj.traverse(c => {
      if (!c.isMesh || c.material.wireframe) return;
      c.material.flatShading = mode === 'flat';
      c.material.transparent = mode === 'xray';
      c.material.opacity = mode === 'xray' ? 0.25 : 1;
      c.material.needsUpdate = true;
    });
  });
}

// ── Camera presets ────────────────────────────────────────────────────────

let cameraManuallyMoved = false;
orbitControls.addEventListener('start', () => { cameraManuallyMoved = true; });
let _cameraSaveTimer = null;
orbitControls.addEventListener('end', () => {
  clearTimeout(_cameraSaveTimer);
  _cameraSaveTimer = setTimeout(() => persistCamera(), 250);
});

function setCameraPreset(preset) {
  // Compute scene bounding box to pick an appropriate distance
  const box = new THREE.Box3();
  sceneObjects.forEach(obj => box.expandByObject(obj));
  const size = new THREE.Vector3();
  box.getSize(size);
  const center = new THREE.Vector3();
  box.getCenter(center);
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  const d = Math.max((maxDim / 2) / Math.tan(fov / 2) * 1.6, 100);
  const cx = center.x, cy = center.y, cz = center.z;
  const targets = {
    persp: { pos: [cx + d*0.7, cy + d*0.7, cz + d*0.7], up: [0, 1, 0] },
    front: { pos: [cx, cy, cz + d],                      up: [0, 1, 0] },
    top:   { pos: [cx, cy + d, cz],                      up: [0, 0, -1] },
    side:  { pos: [cx + d, cy, cz],                      up: [0, 1, 0] },
  };
  const t = targets[preset];
  if (!t) return;
  camera.position.set(...t.pos);
  camera.up.set(...t.up);
  orbitControls.target.set(0, 0, 0);
  orbitControls.update();
  cameraManuallyMoved = true;
}

function fitAllInView() {
  if (sceneObjects.size === 0) return;
  const box = new THREE.Box3();
  sceneObjects.forEach(obj => box.expandByObject(obj));
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  const dist = (maxDim / 2) / Math.tan(fov / 2) * 1.5;
  const dir = camera.position.clone().sub(center).normalize();
  camera.position.copy(center).addScaledVector(dir, dist);
  orbitControls.target.copy(center);
  orbitControls.update();
  cameraManuallyMoved = true;
}

function fitObjectInView(obj) {
  const box = new THREE.Box3().setFromObject(obj);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  const dist = (maxDim / 2) / Math.tan(fov / 2) * 1.8;
  camera.position.set(center.x + dist, center.y + dist * 0.7, center.z + dist);
  orbitControls.target.copy(center);
  orbitControls.update();
  cameraManuallyMoved = true;
}

// ── Analysis ──────────────────────────────────────────────────────────────

function runAnalysis() {
  if (!selectedObject || !selectedObject.isMesh) {
    toast('Select a mesh object first', 'info');
    return;
  }
  const result = analyzeGeometry(selectedObject.geometry);
  const f = unitFactor();
  const overlay = document.getElementById('analysis-overlay');
  const content = document.getElementById('analysis-content');
  content.innerHTML = `
    <div class="analysis-row"><span class="label">Width</span><span class="value">${(result.width/f).toFixed(2)} ${units}</span></div>
    <div class="analysis-row"><span class="label">Height</span><span class="value">${(result.height/f).toFixed(2)} ${units}</span></div>
    <div class="analysis-row"><span class="label">Depth</span><span class="value">${(result.depth/f).toFixed(2)} ${units}</span></div>
    <div class="analysis-row"><span class="label">Volume</span><span class="value">${(result.volume/f**3).toFixed(2)} ${units}³</span></div>
    <div class="analysis-row"><span class="label">Surface</span><span class="value">${(result.surfaceArea/f**2).toFixed(2)} ${units}²</span></div>
    <div class="analysis-row"><span class="label">Triangles</span><span class="value">${result.triangles.toLocaleString()}</span></div>
    <div class="analysis-row"><span class="label">Overhangs</span><span class="value ${result.printable ? 'ok' : 'warn-val'}">${result.overhangPercent}%</span></div>
    <div class="analysis-row"><span class="label">Printable</span><span class="value ${result.printable ? 'ok' : 'warn-val'}">${result.printable ? '✓ Yes' : '⚠ Check'}</span></div>
  `;
  overlay.classList.add('active');
}

// ── Export ────────────────────────────────────────────────────────────────

// ── Print-part aware STL export ───────────────────────────────────────────
// Objects are split into separate STL files by their `_printPart` field.
// `_reference: true` objects (fit ghosts, datum aids) are never exported.
// `_printFlip: true` rotates a part 180deg about X so downward-opening
// pockets face up and don't need bridging.

function printPartsIndex() {
  const parts = new Map();      // partName -> [objDef]
  const loose = [];             // printable but untagged
  let refs = 0;
  for (const o of (currentScene?.objects || [])) {
    if (o._isGroup) continue;
    if (o._reference) { refs++; continue; }
    if (!sceneObjects.has(o.id)) continue;
    if (o.visible === false) continue;
    if (o._printPart) {
      if (!parts.has(o._printPart)) parts.set(o._printPart, []);
      parts.get(o._printPart).push(o);
    } else loose.push(o);
  }
  return { parts, loose, refs };
}

// Bake one part into a slicer-ready geometry: world transforms applied,
// Z-up, centred in XY, sitting on Z=0.
function bakePartGeometry(defs, flip) {
  const pos = [];
  for (const def of defs) {
    const src = sceneObjects.get(def.id);
    if (!src) continue;
    src.updateMatrixWorld(true);
    src.traverse(c => {
      if (!c.isMesh || c.material?.wireframe) return;
      let g = c.geometry;
      g = g.index ? g.toNonIndexed() : g.clone();
      g.applyMatrix4(c.matrixWorld);
      const a = g.getAttribute('position');
      for (let i = 0; i < a.count; i++) pos.push(a.getX(i), a.getY(i), a.getZ(i));
    });
  }
  if (!pos.length) return null;
  const m = new THREE.BufferGeometry();
  m.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  if (flip) m.rotateX(Math.PI);     // pocket-side up
  m.rotateX(Math.PI / 2);           // Y-up -> Z-up for slicers
  m.computeBoundingBox();
  m.translate(0, 0, -m.boundingBox.min.z);
  m.computeBoundingBox();
  const b = m.boundingBox;
  m.translate(-(b.min.x + b.max.x) / 2, -(b.min.y + b.max.y) / 2, 0);
  m.computeBoundingBox();
  m.computeVertexNormals();
  return m;
}

async function exportSTLParts() {
  const { parts, loose, refs } = printPartsIndex();
  if (loose.length) parts.set(parts.size ? 'untagged' : 'model', loose);
  if (!parts.size) { toast('Nothing printable to export', 'error'); return; }

  const exporter = new STLExporter();
  const base = (currentScene?.metadata?.name || 'model')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

  const built = [];
  for (const [name, defs] of parts) {
    const flip = defs.some(d => d._printFlip);
    const geo = bakePartGeometry(defs, flip);
    if (!geo) continue;
    const dv = exporter.parse(new THREE.Mesh(geo), { binary: true });
    const bytes = new Uint8Array(dv.buffer !== undefined ? dv.buffer : dv);
    const size = geo.boundingBox.getSize(new THREE.Vector3());
    built.push({ file: `${base}-${name}.stl`, bytes, size, flip });
  }

  // 1) Write every part server-side. This is the reliable path — browsers
  //    silently block rapid consecutive downloads, so we never depend on them.
  const saved = [];
  for (const b of built) {
    let bin = ''; const CH = 8192;
    for (let i = 0; i < b.bytes.length; i += CH) {
      bin += String.fromCharCode.apply(null, b.bytes.subarray(i, i + CH));
    }
    try {
      const r = await fetch('/api/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: b.file, data: btoa(bin), encoding: 'base64' })
      });
      const res = await r.json();
      if (res.success) saved.push({ ...b, url: res.url });
    } catch (e) { /* fall through to download-only */ }
  }

  // 2) Also offer them as downloads, staggered so the browser doesn't drop them.
  for (let i = 0; i < built.length; i++) {
    setTimeout(() => saveBlob(new Blob([built[i].bytes], { type: 'model/stl' }), built[i].file), i * 700);
  }

  showExportResult(saved.length ? saved : built, refs);
}

// Persistent result panel — a toast disappears before you can click the links.
function showExportResult(items, refs) {
  document.getElementById('export-modal').style.display = 'none';
  let el = document.getElementById('export-result');
  if (!el) {
    el = document.createElement('div');
    el.id = 'export-result';
    document.body.appendChild(el);
  }
  const rows = items.map(it => {
    const d = it.size;
    const dims = `${d.x.toFixed(0)}\u00d7${d.y.toFixed(0)}\u00d7${d.z.toFixed(0)}mm`;
    const kb = Math.round(it.bytes.length / 1024);
    const link = it.url
      ? `<a href="${it.url}" download style="color:var(--accent)">${it.file}</a>`
      : `<span style="color:var(--text)">${it.file}</span>`;
    const flip = it.flip ? ' <span style="color:var(--warn)">flipped</span>' : '';
    return `<div style="padding:3px 0">${link} &mdash; <span style="color:var(--muted)">${dims}, ${kb} KB</span>${flip}</div>`;
  }).join('');
  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <b style="color:var(--accent2)">Exported ${items.length} part${items.length>1?'s':''}</b>
      <button id="export-result-close" class="btn btn-icon" style="margin-left:auto">\u2715</button>
    </div>
    ${rows}
    ${refs ? `<div style="color:var(--muted);margin-top:6px">${refs} reference object(s) excluded</div>` : ''}
    <div style="color:var(--muted);margin-top:8px;font-size:10px">
      Saved to <code>exports/</code>. Downloads may be blocked by the browser &mdash; click a filename above to fetch it.
    </div>`;
  el.style.display = 'block';
  document.getElementById('export-result-close').onclick = () => { el.style.display = 'none'; };
}

function exportScene(format) {
  if (format === 'stl') { exportSTLParts(); return; }

  const exportGroup = new THREE.Group();
  const refIds = new Set((currentScene?.objects || []).filter(o => o._reference).map(o => o.id));
  sceneObjects.forEach((obj, id) => { if (!refIds.has(id)) exportGroup.add(obj.clone()); });

  switch (format) {
    case 'obj': {
      const exporter = new OBJExporter();
      const data = exporter.parse(exportGroup);
      saveFile('scene.obj', data);
      break;
    }
    case 'gltf':
    case 'glb': {
      const exporter = new GLTFExporter();
      const binary = format === 'glb';
      exporter.parse(exportGroup, (result) => {
        if (binary) {
          const blob = new Blob([result], { type: 'application/octet-stream' });
          saveBlob(blob, 'scene.glb');
        } else {
          saveFile('scene.gltf', JSON.stringify(result, null, 2));
        }
      }, (e) => toast(`Export error: ${e}`, 'error'), { binary });
      break;
    }
    case 'ply': {
      // Simple ASCII PLY export
      const positions = [];
      exportGroup.traverse(c => {
        if (c.isMesh) {
          const pos = c.geometry.getAttribute('position');
          for (let i = 0; i < pos.count; i++) positions.push([pos.getX(i), pos.getY(i), pos.getZ(i)]);
        }
      });
      let ply = `ply\nformat ascii 1.0\nelement vertex ${positions.length}\nproperty float x\nproperty float y\nproperty float z\nend_header\n`;
      positions.forEach(([x, y, z]) => ply += `${x.toFixed(6)} ${y.toFixed(6)} ${z.toFixed(6)}\n`);
      saveFile('scene.ply', ply);
      break;
    }
  }
  hideExportModal();
  toast(`Exported as ${format.toUpperCase()}`, 'success');
}

function saveFile(filename, data) {
  const blob = new Blob([data], { type: 'text/plain' });
  saveBlob(blob, filename);
}
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── File import via upload API ────────────────────────────────────────────

async function importFile(file) {
  showLoading(`Uploading ${file.name}...`);
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const { url, filename, format } = await res.json();
    hideLoading();
    const id = `import_${Date.now()}`;
    const objDef = {
      id, name: filename, type: 'file', url, format,
      material: { type: 'standard', color: '#c0c0c0', metalness: 0.1, roughness: 0.5 },
      transform: { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
      visible: true, autoCenter: true
    };
    if (currentScene) {
      currentScene.objects = currentScene.objects || [];
      currentScene.objects.push(objDef);
    }
    addObject(objDef);
    rebuildObjectTree();
  } catch (e) {
    hideLoading();
    toast(`Import failed: ${e.message}`, 'error');
  }
}

// ── Add primitive (from modal) ─────────────────────────────────────────────

function addPrimitive(type) {
  const id = `${type}_${Date.now()}`;
  const defaults = {
    box:      { params: { width: 10, height: 10, depth: 10 } },
    sphere:   { params: { radius: 5 } },
    cylinder: { params: { radiusTop: 5, radiusBottom: 5, height: 10 } },
    cone:     { params: { radius: 5, height: 10 } },
    torus:    { params: { radius: 8, tube: 2 } },
    plane:    { params: { width: 20, height: 20 } },
    gear:     { params: { teeth: 20, module_: 1, thickness: 5, holeRadius: 2 } },
    spring:   { params: { coilRadius: 8, wireRadius: 1.2, turns: 6, height: 30 } },
    pipe:     { params: { outerRadius: 5, innerRadius: 4, height: 20 } },
    hex_bolt: { params: { drive: 8, shankDiameter: 5, shankLength: 20 } },
  };
  const objDef = {
    id, name: type, type,
    ...defaults[type],
    material: { type: 'standard', color: '#4a9eff', metalness: 0.1, roughness: 0.4 },
    transform: { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
    visible: true, castShadow: true, receiveShadow: true
  };
  if (currentScene) {
    currentScene.objects = currentScene.objects || [];
    currentScene.objects.push(objDef);
  }
  addObject(objDef);
  rebuildObjectTree();
  updateSceneStats();
  select(id);
  hideAddModal();
}

// ── Units ─────────────────────────────────────────────────────────────────

function unitFactor() {
  switch (units) {
    case 'cm': return 10;
    case 'm':  return 1000;
    case 'in': return 25.4;
    default:   return 1; // mm
  }
}
function syncUnitDisplay() {
  document.getElementById('unit-select').value = units;
}

// ── Scene stats ────────────────────────────────────────────────────────────

function updateSceneStats() {
  const count = sceneObjects.size;
  document.getElementById('status-objects').textContent = `${count} object${count !== 1 ? 's' : ''}`;
  let tris = 0;
  sceneObjects.forEach(obj => {
    obj.traverse(c => {
      if (c.isMesh) {
        const idx = c.geometry.index;
        tris += idx ? idx.count / 3 : c.geometry.getAttribute('position').count / 3;
      }
    });
  });
  document.getElementById('status-triangles').textContent = `${Math.round(tris).toLocaleString()} tri`;
  document.getElementById('scene-stats').innerHTML =
    `Objects: ${count}<br>Triangles: ${Math.round(tris).toLocaleString()}<br>Units: ${units}`;
}

function updateScenePanel() {
  if (!currentScene) return;
  document.getElementById('scene-name').value = currentScene.metadata?.name || '';
  document.getElementById('bg-color-text').value = currentScene.environment?.background || '#1a1f29';
  document.getElementById('bg-color-swatch').style.background = currentScene.environment?.background || '#1a1f29';
  document.getElementById('env-grid').checked = currentScene.environment?.grid !== false;
  document.getElementById('env-axes').checked = currentScene.environment?.axes !== false;
  document.getElementById('env-shadows').checked = currentScene.environment?.shadows !== false;
  const ambient = currentScene.lights?.find(l => l.type === 'ambient');
  if (ambient) {
    document.getElementById('ambient-intensity').value = ambient.intensity;
    document.getElementById('ambient-intensity-val').textContent = ambient.intensity.toFixed(2);
  }
}

// ── WebSocket connection ────────────────────────────────────────────────────

function connectWS() {
  const ws = new WebSocket(`ws://${location.host}`);
  const dot = document.getElementById('ws-dot');
  const status = document.getElementById('ws-status');

  dot.className = 'status-dot connecting';
  status.textContent = 'Connecting...';

  ws.onopen = () => {
    dot.className = 'status-dot';
    status.textContent = 'Live — watching scene';
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'scene_update') {
      loadSceneJSON(msg.scene);
      toast('Scene updated', 'info');
    } else if (msg.type === 'error') {
      toast(msg.message, 'error');
    }
  };
  ws.onclose = () => {
    dot.className = 'status-dot disconnected';
    status.textContent = 'Disconnected — reconnecting...';
    setTimeout(connectWS, 2000);
  };
  ws.onerror = () => {
    dot.className = 'status-dot disconnected';
    status.textContent = 'Connection error';
  };
}

// ── UI helpers ────────────────────────────────────────────────────────────

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function showLoading(msg = 'Loading...') {
  document.getElementById('loading-text').textContent = msg;
  document.getElementById('loading').classList.add('visible');
}
function hideLoading() { document.getElementById('loading').classList.remove('visible'); }

function showContextMenu(x, y) {
  const menu = document.getElementById('context-menu');
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  menu.classList.add('visible');
}
function hideContextMenu() { document.getElementById('context-menu').classList.remove('visible'); }

function hideExportModal() {
  document.getElementById('export-modal').style.display = 'none';
}
function hideAddModal() {
  document.getElementById('add-modal').style.display = 'none';
}

// ── Event wiring ──────────────────────────────────────────────────────────

// Tab system
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`)?.classList.add('active');
  });
});

// Toolbar buttons
document.getElementById('btn-solid').addEventListener('click', () => setViewMode('solid'));
document.getElementById('btn-wire').addEventListener('click', () => setViewMode('wire'));
document.getElementById('btn-both').addEventListener('click', () => setViewMode('both'));
document.getElementById('btn-material').addEventListener('click', () => setShadingMode('material'));
document.getElementById('btn-flat').addEventListener('click', () => setShadingMode('flat'));
document.getElementById('btn-xray').addEventListener('click', () => setShadingMode('xray'));

// ── Project bundle + Docs panel ───────────────────────────────────────────

// Toolbar dropdown menus (close on outside click)
function setupMenu(buttonId, menuId) {
  const btn = document.getElementById(buttonId);
  const menu = document.getElementById(menuId);
  if (!btn || !menu) return;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.menu.open').forEach(m => { if (m !== menu) m.classList.remove('open'); });
    menu.classList.toggle('open');
  });
  menu.addEventListener('click', (e) => {
    if (e.target.classList.contains('menu-item')) {
      menu.classList.remove('open');
    }
  });
}
setupMenu('btn-project', 'menu-project');
setupMenu('btn-generate', 'menu-generate');
document.addEventListener('click', () => {
  document.querySelectorAll('.menu.open').forEach(m => m.classList.remove('open'));
});

// Project menu actions
document.getElementById('menu-project')?.addEventListener('click', async (e) => {
  const act = e.target?.dataset?.act;
  if (!act) return;
  if (act === 'project-new') {
    if (!confirm('Start a new (empty) project? Current scene will be replaced.')) return;
    const empty = {
      metadata: { version: '1.0', name: 'New Project', units: 'mm' },
      environment: { background: '#0a0d14', grid: true, axes: false, shadows: true },
      camera: { position: [80, 80, 200], target: [0, 0, 0], fov: 45 },
      lights: [
        { id: 'ambient', type: 'ambient', color: '#ffffff', intensity: 0.4 },
        { id: 'key', type: 'directional', color: '#ffffff', intensity: 1.2, position: [80,120,60], castShadow: true }
      ],
      objects: []
    };
    await fetch('/api/scene', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(empty) });
    loadSceneJSON(empty);
    toast('New project created');
  } else if (act === 'project-open') {
    document.getElementById('project-file-input').click();
  } else if (act === 'project-save') {
    await downloadProjectBundle();
  } else if (act === 'project-docs') {
    openDocsPanel();
  } else if (act === 'project-export-svgs') {
    await exportAllDrawingsZip();
  }
});

// Generate menu actions — these surface a prompt the user can copy to Claude
const GEN_PROMPTS = {
  'gen-bom':      'Regenerate the Bill of Materials in deliverables/{project}/BOM.md based on the current scene/current.json. Cross-check every object has a BOM line.',
  'gen-plan':     'Regenerate the manufacturing plan in deliverables/{project}/manufacturing-plan.md based on the current scene. Update print times and section assignments.',
  'gen-design':   'Regenerate the design document in deliverables/{project}/design-document.md from the current scene. Preserve open questions and risks unless they no longer apply.',
  'gen-assembly': 'Regenerate the assembly instructions in deliverables/{project}/assembly-instructions.md based on the current scene and BOM cross-references.',
  'gen-drawings': 'Regenerate all SVG drawings in deliverables/{project}/drawings/ based on current geometry: 01-front-elevation, 02-section-view, 03-plan-view, 04-bottom-view, 05-exploded-isometric, 06-edf-detail (or appropriate subsystem detail).',
  'gen-all':      'Regenerate ALL deliverables in deliverables/{project}/ from the current scene: BOM, manufacturing plan, design document, assembly instructions, all drawings, and the README index.'
};

document.getElementById('menu-generate')?.addEventListener('click', async (e) => {
  const act = e.target?.dataset?.act;
  if (!act || !GEN_PROMPTS[act]) return;
  const slug = currentProjectSlug || 'drone-rocket-mk2';
  const prompt = GEN_PROMPTS[act].replaceAll('{project}', slug);
  // Copy to clipboard + show toast with instructions
  try {
    await navigator.clipboard.writeText(prompt);
    toast(`Prompt copied — paste to Claude: "${prompt.slice(0, 60)}…"`, 'success');
  } catch {
    // Fallback — show in a modal
    alert('Copy this and paste to Claude:\n\n' + prompt);
  }
});

// Project file import
document.getElementById('project-file-input')?.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const text = await file.text();
    const bundle = JSON.parse(text);
    if (bundle.format !== '3d-agent-project') {
      toast('Not a valid 3D Agent project bundle', 'error');
      return;
    }
    const res = await fetch('/api/project/bundle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: text
    });
    if (!res.ok) { toast('Import failed', 'error'); return; }
    const result = await res.json();
    if (bundle.scene) loadSceneJSON(bundle.scene);
    currentProjectSlug = result.project;
    toast(`Project "${bundle.metadata?.name}" loaded`, 'success');
  } catch (err) {
    toast('Failed to load: ' + err.message, 'error');
  }
  e.target.value = '';
});

let currentProjectSlug = null;

async function downloadProjectBundle() {
  try {
    const res = await fetch('/api/project/bundle');
    const bundle = await res.json();
    const slug = bundle.metadata?.projectSlug || 'project';
    currentProjectSlug = slug;
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    saveBlob(blob, `${slug}-${new Date().toISOString().slice(0,10)}.3dap`);
    toast(`Saved ${slug}.3dap (${Math.round(blob.size/1024)} KB)`, 'success');
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  }
}

async function exportAllDrawingsZip() {
  // Without a zip lib, just download each SVG individually
  const res = await fetch('/api/project/documents');
  const idx = await res.json();
  const drawings = Object.keys(idx.drawings || {});
  if (!drawings.length) { toast('No drawings to export'); return; }
  for (const slug of drawings) {
    const r = await fetch(`/api/project/doc/${slug}`);
    const d = await r.json();
    const blob = new Blob([d.content], { type: 'image/svg+xml' });
    saveBlob(blob, `${slug}.svg`);
  }
  toast(`Exported ${drawings.length} SVG drawings`);
}

// ── Docs panel (right-side vertical split, dockable into #main) ───────────
async function openDocsPanel() {
  const panel = document.getElementById('docs-panel');
  const main = document.getElementById('main');
  // Move panel into #main so it becomes a flex sibling — viewport will auto-shrink
  if (panel.parentElement !== main) main.appendChild(panel);
  panel.style.display = 'flex';
  // Restore saved width
  const savedW = parseInt(localStorage.getItem('docs-panel-w'), 10);
  if (savedW && savedW >= 380) panel.style.width = savedW + 'px';
  document.getElementById('btn-toggle-docs')?.classList.add('active');
  await refreshDocsList();
}

function closeDocsPanel() {
  document.getElementById('docs-panel').style.display = 'none';
  document.getElementById('btn-toggle-docs')?.classList.remove('active');
}

document.getElementById('docs-close')?.addEventListener('click', closeDocsPanel);

// Direct toolbar toggle for Docs panel
document.getElementById('btn-toggle-docs')?.addEventListener('click', function() {
  const panel = document.getElementById('docs-panel');
  const isOpen = panel.style.display === 'flex';
  if (isOpen) closeDocsPanel();
  else openDocsPanel();
});

// Resizable docs panel — drag the left edge
(function() {
  const handle = document.getElementById('docs-resize');
  const panel = document.getElementById('docs-panel');
  if (!handle || !panel) return;
  let dragging = false;
  handle.addEventListener('mousedown', (e) => {
    dragging = true; document.body.style.cursor = 'ew-resize'; e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const main = document.getElementById('main');
    const rect = main.getBoundingClientRect();
    // distance from right edge
    const w = Math.max(380, Math.min(rect.width * 0.7, rect.right - e.clientX));
    panel.style.width = w + 'px';
  });
  window.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false; document.body.style.cursor = '';
    localStorage.setItem('docs-panel-w', parseInt(panel.style.width, 10));
  });
})();
document.getElementById('docs-refresh')?.addEventListener('click', refreshDocsList);

async function refreshDocsList() {
  try {
    const res = await fetch('/api/project/documents');
    const idx = await res.json();
    document.getElementById('docs-project-name').textContent = idx.project ? `— ${idx.project}` : '— (no project)';
    currentProjectSlug = idx.project;

    const docsEl = document.getElementById('docs-list-documents');
    docsEl.innerHTML = '';
    Object.values(idx.documents || {}).forEach(d => docsEl.appendChild(renderDocItem(d, '📄')));
    if (!Object.keys(idx.documents || {}).length) {
      docsEl.innerHTML = '<div style="padding:10px 14px; color:var(--muted); font-size:11px;">No documents — use Generate menu</div>';
    }

    const drgEl = document.getElementById('docs-list-drawings');
    drgEl.innerHTML = '';
    Object.values(idx.drawings || {}).forEach(d => drgEl.appendChild(renderDocItem(d, '✏')));
    if (!Object.keys(idx.drawings || {}).length) {
      drgEl.innerHTML = '<div style="padding:10px 14px; color:var(--muted); font-size:11px;">No drawings yet</div>';
    }
  } catch (e) {
    console.warn('docs refresh failed', e);
  }
}

function renderDocItem(d, icon) {
  const el = document.createElement('div');
  el.className = 'doc-item';
  el.dataset.slug = d.slug;
  el.innerHTML = `
    <span class="doc-icon">${icon}</span>
    <span class="doc-name">${d.title}</span>
    <span class="doc-size">${(d.size / 1024).toFixed(1)} KB</span>
  `;
  el.addEventListener('click', () => {
    document.querySelectorAll('.doc-item').forEach(x => x.classList.remove('active'));
    el.classList.add('active');
    viewDoc(d.slug);
  });
  return el;
}

async function viewDoc(slug) {
  const viewer = document.getElementById('docs-viewer');
  viewer.innerHTML = '<div class="docs-empty">Loading…</div>';
  try {
    const res = await fetch(`/api/project/doc/${slug}`);
    const doc = await res.json();
    if (doc.format === 'svg') {
      viewer.innerHTML = doc.content;
    } else if (doc.format === 'markdown') {
      viewer.innerHTML = renderMarkdown(doc.content);
    } else {
      viewer.innerHTML = `<pre>${doc.content}</pre>`;
    }
  } catch (e) {
    viewer.innerHTML = `<div class="docs-empty">Error: ${e.message}</div>`;
  }
}

// Minimal Markdown renderer — headings, lists, tables, code, links, hr
function renderMarkdown(md) {
  // Escape HTML
  let html = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  // Code blocks
  html = html.replace(/```([\s\S]*?)```/g, (_, c) => `<pre><code>${c.trim()}</code></pre>`);
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Tables — find blocks of consecutive | rows
  html = html.replace(/((?:^\|.*\|\s*$\n?)+)/gm, (block) => {
    const rows = block.trim().split('\n').filter(r => r.trim().startsWith('|'));
    if (rows.length < 2) return block;
    // Second row is separator |---|---|
    const isSep = /^\|\s*[:\-]+/.test(rows[1]);
    const dataRows = isSep ? rows.filter((_, i) => i !== 1) : rows;
    const cells = dataRows.map(r => r.replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
    const head = isSep ? cells.shift() : null;
    let t = '<table>';
    if (head) t += '<thead><tr>' + head.map(c => `<th>${c}</th>`).join('') + '</tr></thead>';
    t += '<tbody>' + cells.map(r => '<tr>' + r.map(c => `<td>${c}</td>`).join('') + '</tr>').join('') + '</tbody>';
    return t + '</table>';
  });
  // Headings
  html = html.replace(/^###### (.+)$/gm, '<h6>$1</h6>');
  html = html.replace(/^##### (.+)$/gm, '<h5>$1</h5>');
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Hr
  html = html.replace(/^---+$/gm, '<hr>');
  // Bold + italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>');
  // Links (no auto)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Lists
  html = html.replace(/^(\s*)[*\-] (.+)$/gm, '$1<li>$2</li>');
  html = html.replace(/^(\s*)\d+\. (.+)$/gm, '$1<li>$2</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>(?:\n<li>[\s\S]*?<\/li>)*)/g, '<ul>$1</ul>');
  // Paragraphs
  html = html.split(/\n{2,}/).map(block => {
    if (/^<(h\d|ul|ol|table|pre|hr|p)/.test(block.trim())) return block;
    return '<p>' + block.trim().replace(/\n/g, '<br>') + '</p>';
  }).join('\n');
  return html;
}

// Resizable left panel
(function() {
  const handle = document.getElementById('left-resize');
  const panel = document.getElementById('panel-left');
  if (!handle || !panel) return;
  let dragging = false;
  // restore saved width
  const saved = parseInt(localStorage.getItem('left-panel-w'), 10);
  if (saved && saved > 180 && saved < 600) panel.style.width = saved + 'px';
  handle.addEventListener('mousedown', (e) => {
    dragging = true; document.body.style.cursor = 'ew-resize'; e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const w = Math.max(180, Math.min(600, e.clientX));
    panel.style.width = w + 'px';
    if (typeof onWindowResize === 'function') onWindowResize();
  });
  window.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false; document.body.style.cursor = '';
    localStorage.setItem('left-panel-w', parseInt(panel.style.width, 10));
  });
})();

// Undo / redo
document.getElementById('btn-undo')?.addEventListener('click', undo);
document.getElementById('btn-redo')?.addEventListener('click', redo);
window.addEventListener('keydown', (e) => {
  const meta = e.metaKey || e.ctrlKey;
  if (meta && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
  else if (meta && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); redo(); }
});

// Projection / Ortho views
document.getElementById('btn-persp')?.addEventListener('click', () => setProjection('perspective'));
document.getElementById('btn-ortho-plan')?.addEventListener('click', () => setProjection('plan'));
document.getElementById('btn-ortho-elev')?.addEventListener('click', () => setProjection('elevation'));
document.getElementById('btn-ortho-side')?.addEventListener('click', () => setProjection('section'));

// Environment modal
document.getElementById('btn-env')?.addEventListener('click', () => openEnvModal());
document.getElementById('env-close')?.addEventListener('click', () => document.getElementById('env-modal').style.display = 'none');
['env-bg-bright','env-ambient','env-key','env-fill','env-rim','env-exposure'].forEach(id => {
  const el = document.getElementById(id);
  el?.addEventListener('input', () => onEnvChange());
});
['env-bg','env-ambient-color'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', () => onEnvChange());
});
['env-grid','env-axes','env-shadows'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => onEnvChange());
});

document.getElementById('btn-grid').addEventListener('click', function() {
  this.classList.toggle('active');
  gridHelper.visible = this.classList.contains('active');
  savePrefs({ grid: gridHelper.visible });
});
document.getElementById('btn-axes').addEventListener('click', function() {
  this.classList.toggle('active');
  axesHelper.visible = this.classList.contains('active');
  savePrefs({ axes: axesHelper.visible });
});
document.getElementById('btn-shadows').addEventListener('click', function() {
  this.classList.toggle('active');
  renderer.shadowMap.enabled = this.classList.contains('active');
  savePrefs({ shadows: renderer.shadowMap.enabled });
});

document.getElementById('btn-analyze').addEventListener('click', () => {
  const overlay = document.getElementById('analysis-overlay');
  if (overlay.classList.contains('active')) {
    overlay.classList.remove('active');
  } else {
    runAnalysis();
  }
});

document.getElementById('btn-measure').addEventListener('click', function() {
  isMeasuring = !isMeasuring;
  this.classList.toggle('active', isMeasuring);
  measurePoints = [];
  toast(isMeasuring ? 'Click two points to measure distance' : 'Measure off', 'info');
});

document.getElementById('btn-import').addEventListener('click', () => {
  document.getElementById('file-input').click();
});

document.getElementById('file-input').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) importFile(file);
  e.target.value = '';
});

document.getElementById('btn-export').addEventListener('click', () => {
  // Show what will actually come out before the user commits
  const el = document.getElementById('export-parts-summary');
  if (el) {
    const { parts, loose, refs } = printPartsIndex();
    const rows = [];
    for (const [name, defs] of parts) {
      const flip = defs.some(d => d._printFlip) ? ' <span style="color:var(--warn)">(flipped for print)</span>' : '';
      rows.push(`<div>&bull; <b style="color:var(--text)">${name}.stl</b> — ${defs.length} object${defs.length>1?'s':''}${flip}</div>`);
    }
    if (loose.length) rows.push(`<div>&bull; <b style="color:var(--text)">untagged.stl</b> — ${loose.length} object(s) with no <code>_printPart</code></div>`);
    if (refs) rows.push(`<div style="color:var(--muted)">&bull; ${refs} reference object(s) excluded</div>`);
    el.innerHTML = rows.length
      ? `<div style="color:var(--muted);margin-bottom:5px;">STL exports as separate parts:</div>${rows.join('')}`
      : '<span style="color:var(--warn)">Nothing printable in this scene.</span>';
  }
  document.getElementById('export-modal').style.display = 'flex';
});

document.getElementById('export-close').addEventListener('click', hideExportModal);
document.querySelectorAll('#export-modal [data-format]').forEach(btn => {
  btn.addEventListener('click', () => exportScene(btn.dataset.format));
});

document.getElementById('btn-add-obj').addEventListener('click', () => {
  document.getElementById('add-modal').style.display = 'flex';
});
document.getElementById('add-close').addEventListener('click', hideAddModal);
document.querySelectorAll('#add-modal [data-type]').forEach(btn => {
  btn.addEventListener('click', () => addPrimitive(btn.dataset.type));
});

// View overlay buttons
document.getElementById('vbtn-persp').addEventListener('click', () => setCameraPreset('persp'));
document.getElementById('vbtn-front').addEventListener('click', () => setCameraPreset('front'));
document.getElementById('vbtn-top').addEventListener('click', () => setCameraPreset('top'));
document.getElementById('vbtn-side').addEventListener('click', () => setCameraPreset('side'));
document.getElementById('vbtn-fit').addEventListener('click', fitAllInView);

// Props panel inputs
function onPropChange() {
  if (!selectedObject) return;
  selectedObject.position.set(
    parseFloat(document.getElementById('pos-x').value) || 0,
    parseFloat(document.getElementById('pos-y').value) || 0,
    parseFloat(document.getElementById('pos-z').value) || 0,
  );
  const toRad = d => (parseFloat(d) || 0) * Math.PI / 180;
  selectedObject.rotation.set(
    toRad(document.getElementById('rot-x').value),
    toRad(document.getElementById('rot-y').value),
    toRad(document.getElementById('rot-z').value),
  );
  selectedObject.scale.set(
    parseFloat(document.getElementById('scl-x').value) || 1,
    parseFloat(document.getElementById('scl-y').value) || 1,
    parseFloat(document.getElementById('scl-z').value) || 1,
  );
}
['pos-x','pos-y','pos-z','rot-x','rot-y','rot-z','scl-x','scl-y','scl-z'].forEach(id => {
  document.getElementById(id).addEventListener('input', onPropChange);
});
document.getElementById('prop-visible').addEventListener('change', function() {
  if (selectedObject) selectedObject.visible = this.checked;
});

// Material panel
document.getElementById('mat-color-text').addEventListener('input', function() {
  if (!selectedObject?.isMesh) return;
  try { selectedObject.material.color.set(this.value); document.getElementById('mat-color-swatch').style.background = this.value; } catch(e){}
});
document.getElementById('mat-metalness').addEventListener('input', function() {
  if (!selectedObject?.isMesh || selectedObject.material.metalness === undefined) return;
  selectedObject.material.metalness = parseFloat(this.value);
  document.getElementById('mat-metalness-val').textContent = parseFloat(this.value).toFixed(2);
});
document.getElementById('mat-roughness').addEventListener('input', function() {
  if (!selectedObject?.isMesh || selectedObject.material.roughness === undefined) return;
  selectedObject.material.roughness = parseFloat(this.value);
  document.getElementById('mat-roughness-val').textContent = parseFloat(this.value).toFixed(2);
});
document.getElementById('mat-opacity').addEventListener('input', function() {
  if (!selectedObject?.isMesh) return;
  selectedObject.material.opacity = parseFloat(this.value);
  document.getElementById('mat-opacity-val').textContent = parseFloat(this.value).toFixed(2);
});
document.getElementById('mat-transparent').addEventListener('change', function() {
  if (!selectedObject?.isMesh) return;
  selectedObject.material.transparent = this.checked;
  selectedObject.material.needsUpdate = true;
});
document.getElementById('mat-wireframe').addEventListener('change', function() {
  if (!selectedObject?.isMesh) return;
  selectedObject.material.wireframe = this.checked;
});
document.getElementById('mat-flat-shading').addEventListener('change', function() {
  if (!selectedObject?.isMesh) return;
  selectedObject.material.flatShading = this.checked;
  selectedObject.material.needsUpdate = true;
});
document.getElementById('mat-double-side').addEventListener('change', function() {
  if (!selectedObject?.isMesh) return;
  selectedObject.material.side = this.checked ? THREE.DoubleSide : THREE.FrontSide;
  selectedObject.material.needsUpdate = true;
});
document.getElementById('mat-emissive-text').addEventListener('input', function() {
  if (!selectedObject?.isMesh) return;
  try { selectedObject.material.emissive?.set(this.value); document.getElementById('mat-emissive-swatch').style.background = this.value; } catch(e){}
});
document.getElementById('mat-emissive-intensity').addEventListener('input', function() {
  if (!selectedObject?.isMesh) return;
  selectedObject.material.emissiveIntensity = parseFloat(this.value);
  document.getElementById('mat-emissive-intensity-val').textContent = parseFloat(this.value).toFixed(1);
});

// Scene panel
document.getElementById('bg-color-text').addEventListener('input', function() {
  try { scene.background = new THREE.Color(this.value); document.getElementById('bg-color-swatch').style.background = this.value; } catch(e){}
});
document.getElementById('env-grid').addEventListener('change', function() { gridHelper.visible = this.checked; });
document.getElementById('env-axes').addEventListener('change', function() { axesHelper.visible = this.checked; });
document.getElementById('ambient-intensity').addEventListener('input', function() {
  const al = scene.children.find(c => c.isAmbientLight);
  if (al) al.intensity = parseFloat(this.value);
  document.getElementById('ambient-intensity-val').textContent = parseFloat(this.value).toFixed(2);
});

// Units
document.getElementById('unit-select').addEventListener('change', function() {
  units = this.value;
  if (selectedObject) syncPropsFromObject(selectedObject);
  updateSceneStats();
});

// Context menu
document.getElementById('ctx-focus').addEventListener('click', () => { if (selectedObject) fitObjectInView(selectedObject); hideContextMenu(); });
document.getElementById('ctx-delete').addEventListener('click', () => {
  if (selectedId) {
    scene.remove(sceneObjects.get(selectedId));
    sceneObjects.delete(selectedId);
    if (currentScene?.objects) currentScene.objects = currentScene.objects.filter(o => o.id !== selectedId);
    deselect();
    rebuildObjectTree();
    updateSceneStats();
  }
  hideContextMenu();
});
document.getElementById('ctx-reset-transform').addEventListener('click', () => {
  if (selectedObject) {
    selectedObject.position.set(0, 0, 0);
    selectedObject.rotation.set(0, 0, 0);
    selectedObject.scale.set(1, 1, 1);
    syncPropsFromObject(selectedObject);
  }
  hideContextMenu();
});
document.getElementById('ctx-export-stl').addEventListener('click', () => { exportScene('stl'); hideContextMenu(); });
document.getElementById('ctx-export-obj').addEventListener('click', () => { exportScene('obj'); hideContextMenu(); });
document.getElementById('ctx-duplicate').addEventListener('click', () => {
  if (selectedId && currentScene?.objects) {
    const src = currentScene.objects.find(o => o.id === selectedId);
    if (src) {
      const copy = JSON.parse(JSON.stringify(src));
      copy.id = `${src.type}_${Date.now()}`;
      copy.name = src.name + ' copy';
      copy.transform.position = [(src.transform?.position?.[0] || 0) + 15, src.transform?.position?.[1] || 0, src.transform?.position?.[2] || 0];
      currentScene.objects.push(copy);
      addObject(copy);
      rebuildObjectTree();
      select(copy.id);
    }
  }
  hideContextMenu();
});

document.addEventListener('click', () => hideContextMenu());

// Panel toggles
document.getElementById('btn-toggle-left').addEventListener('click', function() {
  const panel = document.getElementById('panel-left');
  panel.classList.toggle('collapsed');
  this.classList.toggle('active', !panel.classList.contains('collapsed'));
  // Trigger resize so canvas fills new space
  window.dispatchEvent(new Event('resize'));
});
document.getElementById('btn-toggle-right').addEventListener('click', function() {
  const panel = document.getElementById('panel-right');
  panel.classList.toggle('open');
  panel.style.display = panel.classList.contains('open') ? 'flex' : '';
  this.classList.toggle('active', panel.classList.contains('open'));
  window.dispatchEvent(new Event('resize'));
});

// Drag & drop
const vc = document.getElementById('viewport-container');
vc.addEventListener('dragover', e => { e.preventDefault(); document.getElementById('drop-overlay').classList.add('active'); });
vc.addEventListener('dragleave', () => document.getElementById('drop-overlay').classList.remove('active'));
vc.addEventListener('drop', e => {
  e.preventDefault();
  document.getElementById('drop-overlay').classList.remove('active');
  const file = e.dataTransfer.files[0];
  if (file) importFile(file);
});


// ── Spacebar navigation (hold Space + drag to pan, like Figma/Photoshop) ──
let spacePanActive = false;
let suppressNextClick = false;

const ORBIT_BUTTONS = {
  LEFT: THREE.MOUSE.ROTATE,
  MIDDLE: THREE.MOUSE.DOLLY,
  RIGHT: THREE.MOUSE.PAN
};
const PAN_BUTTONS = {
  LEFT: THREE.MOUSE.PAN,
  MIDDLE: THREE.MOUSE.DOLLY,
  RIGHT: THREE.MOUSE.PAN
};
orbitControls.mouseButtons = ORBIT_BUTTONS;

function isTypingTarget(t) {
  if (!t) return false;
  const tag = t.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable;
}

function setSpacePan(on) {
  if (spacePanActive === on) return;
  spacePanActive = on;
  orbitControls.mouseButtons = on ? PAN_BUTTONS : ORBIT_BUTTONS;
  renderer.domElement.style.cursor = on ? 'grab' : '';
  document.getElementById('nav-hint')?.classList.toggle('active', on);
}

window.addEventListener('keydown', (e) => {
  if (e.code !== 'Space' || isTypingTarget(e.target)) return;
  e.preventDefault();           // stop the page scrolling
  setSpacePan(true);
}, { capture: true });

window.addEventListener('keyup', (e) => {
  if (e.code !== 'Space') return;
  setSpacePan(false);
}, { capture: true });

// Release pan if focus leaves the window mid-drag
window.addEventListener('blur', () => setSpacePan(false));

// Cursor feedback + swallow the click that ends a pan drag
renderer.domElement.addEventListener('pointerdown', () => {
  if (spacePanActive) { renderer.domElement.style.cursor = 'grabbing'; suppressNextClick = true; }
});
renderer.domElement.addEventListener('pointerup', () => {
  if (spacePanActive) renderer.domElement.style.cursor = 'grab';
});

// Click to select in viewport
renderer.domElement.addEventListener('click', (e) => {
  if (e.target !== renderer.domElement) return;
  if (spacePanActive || suppressNextClick) { suppressNextClick = false; return; }
  const rect = renderer.domElement.getBoundingClientRect();
  mouse.set(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1
  );
  raycaster.setFromCamera(mouse, camera);
  const meshes = [];
  sceneObjects.forEach(obj => obj.traverse(c => { if (c.isMesh && c !== transformControls.object) meshes.push(c); }));
  const hits = raycaster.intersectObjects(meshes, false);
  if (hits.length > 0) {
    let hit = hits[0].object;
    while (hit.parent && !hit.userData.id) hit = hit.parent;
    if (hit.userData.id) {
      select(hit.userData.id);
    }
  } else {
    deselect();
  }
});

// Keyboard shortcuts
window.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  switch (e.key.toLowerCase()) {
    case 'delete': case 'backspace':
      if (selectedId) {
        scene.remove(sceneObjects.get(selectedId));
        sceneObjects.delete(selectedId);
        if (currentScene?.objects) currentScene.objects = currentScene.objects.filter(o => o.id !== selectedId);
        deselect(); rebuildObjectTree(); updateSceneStats();
      }
      break;
    case 'f': if (selectedObject) fitObjectInView(selectedObject); break;
    case 'g': transformControls.setMode('translate'); break;
    case 'r': transformControls.setMode('rotate'); break;
    case 's': if (e.ctrlKey || e.metaKey) break; transformControls.setMode('scale'); break;
    case 'escape': deselect(); break;
    case '1': setCameraPreset('front'); break;
    case '3': setCameraPreset('side'); break;
    case '7': setCameraPreset('top'); break;
    case 'numpad1': setCameraPreset('front'); break;
  }
});

// ── Resize handler ────────────────────────────────────────────────────────

const resizeObserver = new ResizeObserver(() => {
  const container = document.getElementById('viewport-container');
  const w = container.clientWidth;
  const h = container.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
});
resizeObserver.observe(document.getElementById('viewport-container'));

// ── Render loop ───────────────────────────────────────────────────────────

// ── Rulers ────────────────────────────────────────────────────────────────
const rulerTop = document.getElementById('ruler-top');
const rulerLeft = document.getElementById('ruler-left');
const rulerTopCtx = rulerTop?.getContext('2d');
const rulerLeftCtx = rulerLeft?.getContext('2d');
let lastRulerKey = '';

function animate() {
  requestAnimationFrame(animate);
  orbitControls.update();
  renderer.render(scene, camera);
  drawRulers();
}
animate();

function drawRulers() {
  if (!rulerTopCtx || !rulerLeftCtx) return;
  const container = document.getElementById('viewport-container');
  const w = container.clientWidth, h = container.clientHeight;

  // Compute world-space units per pixel at the orbit target depth
  const target = orbitControls.target;
  const dist = camera.position.distanceTo(target);
  const fovRad = camera.fov * Math.PI / 180;
  const worldPerPxV = (2 * Math.tan(fovRad / 2) * dist) / Math.max(1, h);

  // Choose a tick spacing that yields ~50–120 px between major ticks
  const targetPx = 80;
  const rawStep = worldPerPxV * targetPx;
  const niceStep = niceNumber(rawStep);
  const pxPerStep = niceStep / worldPerPxV;

  // Throttle re-renders
  const key = `${w}|${h}|${niceStep.toFixed(4)}|${target.x.toFixed(2)}|${target.y.toFixed(2)}|${camera.position.x.toFixed(1)}|${camera.position.y.toFixed(1)}|${camera.position.z.toFixed(1)}|${camera.fov}`;
  if (key === lastRulerKey) return;
  lastRulerKey = key;

  // Resize canvases (account for device pixel ratio)
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const topW = Math.max(1, w - 18), topH = 18;
  const leftW = 18, leftH = Math.max(1, h - 18);
  if (rulerTop.width !== topW * dpr || rulerTop.height !== topH * dpr) {
    rulerTop.width = topW * dpr; rulerTop.height = topH * dpr;
    rulerTop.style.width = topW + 'px'; rulerTop.style.height = topH + 'px';
  }
  if (rulerLeft.width !== leftW * dpr || rulerLeft.height !== leftH * dpr) {
    rulerLeft.width = leftW * dpr; rulerLeft.height = leftH * dpr;
    rulerLeft.style.width = leftW + 'px'; rulerLeft.style.height = leftH + 'px';
  }
  rulerTopCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  rulerLeftCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const labelColor = '#88909a';
  const tickColor = '#5a6470';
  const subColor = '#3a414b';
  const font = '9px ui-monospace, Menlo, monospace';

  // ─ Top ruler (X axis) ─
  rulerTopCtx.clearRect(0, 0, topW, topH);
  rulerTopCtx.font = font;
  rulerTopCtx.fillStyle = labelColor;
  rulerTopCtx.strokeStyle = tickColor;
  rulerTopCtx.lineWidth = 1;
  rulerTopCtx.textAlign = 'left';
  rulerTopCtx.textBaseline = 'top';

  // Centre = 0 of target.x in screen coordinates
  const centerX = topW / 2;
  // Major + minor ticks across the visible range
  const numStepsX = Math.ceil(topW / pxPerStep) + 2;
  for (let i = -numStepsX; i <= numStepsX; i++) {
    const px = centerX + i * pxPerStep;
    if (px < 0 || px > topW) continue;
    const value = i * niceStep + target.x;
    rulerTopCtx.beginPath();
    rulerTopCtx.moveTo(px, 12); rulerTopCtx.lineTo(px, 18);
    rulerTopCtx.stroke();
    rulerTopCtx.fillText(formatRulerNum(value), px + 2, 1);
    // Sub-ticks
    rulerTopCtx.strokeStyle = subColor;
    for (let s = 1; s < 5; s++) {
      const sx = px + (s * pxPerStep / 5);
      if (sx > topW) break;
      rulerTopCtx.beginPath();
      rulerTopCtx.moveTo(sx, 14); rulerTopCtx.lineTo(sx, 18);
      rulerTopCtx.stroke();
    }
    rulerTopCtx.strokeStyle = tickColor;
  }

  // ─ Left ruler (Y axis) ─
  rulerLeftCtx.clearRect(0, 0, leftW, leftH);
  rulerLeftCtx.font = font;
  rulerLeftCtx.fillStyle = labelColor;
  rulerLeftCtx.strokeStyle = tickColor;
  const centerY = leftH / 2;
  const numStepsY = Math.ceil(leftH / pxPerStep) + 2;
  for (let i = -numStepsY; i <= numStepsY; i++) {
    const py = centerY + i * pxPerStep;
    if (py < 0 || py > leftH) continue;
    // World Y goes up, screen Y goes down
    const value = -i * niceStep + target.y;
    rulerLeftCtx.beginPath();
    rulerLeftCtx.moveTo(12, py); rulerLeftCtx.lineTo(18, py);
    rulerLeftCtx.stroke();
    rulerLeftCtx.save();
    rulerLeftCtx.translate(8, py + 2);
    rulerLeftCtx.rotate(-Math.PI / 2);
    rulerLeftCtx.textAlign = 'left';
    rulerLeftCtx.textBaseline = 'middle';
    rulerLeftCtx.fillText(formatRulerNum(value), 0, 0);
    rulerLeftCtx.restore();
    rulerLeftCtx.strokeStyle = subColor;
    for (let s = 1; s < 5; s++) {
      const sy = py + (s * pxPerStep / 5);
      if (sy > leftH) break;
      rulerLeftCtx.beginPath();
      rulerLeftCtx.moveTo(14, sy); rulerLeftCtx.lineTo(18, sy);
      rulerLeftCtx.stroke();
    }
    rulerLeftCtx.strokeStyle = tickColor;
  }
}

function niceNumber(n) {
  if (n <= 0) return 1;
  const exp = Math.floor(Math.log10(n));
  const f = n / Math.pow(10, exp);
  let nice;
  if (f < 1.5) nice = 1;
  else if (f < 3.5) nice = 2;
  else if (f < 7.5) nice = 5;
  else nice = 10;
  return nice * Math.pow(10, exp);
}

function formatRulerNum(v) {
  const abs = Math.abs(v);
  if (abs < 0.001) return '0';
  if (abs >= 1000) return (v / 1000).toFixed(1) + 'k';
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 10) return v.toFixed(0);
  if (abs >= 1) return v.toFixed(1);
  return v.toFixed(2);
}

// ── Initial load ──────────────────────────────────────────────────────────

(async () => {
  try {
    const res = await fetch('/api/scene');
    const sceneData = await res.json();
    loadSceneJSON(sceneData);
    applySavedPrefs();
    toast('3D Agent ready', 'success');
  } catch (e) {
    toast('Could not load scene — start the server', 'error');
  }
  connectWS();
})();
