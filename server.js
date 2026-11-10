const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const chokidar = require('chokidar');
const multer = require('multer');
const path = require('path');
const fs = require('fs');

const PORT = Number(process.env.PORT) || 3030;
const os = require('os');

// Code lives with the plugin; user data lives in its own folder so a plugin
// update never touches designs. Override with THREED_AGENT_HOME.
const CODE = __dirname;
const ROOT = path.resolve(process.env.THREED_AGENT_HOME || path.join(os.homedir(), 'Documents', '3D-Agent'));
const SCENE_FILE = path.join(ROOT, 'scene', 'current.json');
const UPLOADS_DIR = path.join(ROOT, 'uploads');
const EXPORTS_DIR = path.join(ROOT, 'exports');

// Bootstrap directories
for (const dir of [path.join(ROOT, 'scene'), path.join(ROOT, 'projects'), UPLOADS_DIR, EXPORTS_DIR]) {
  fs.mkdirSync(dir, { recursive: true });
}

// Seed a default scene on first run
if (!fs.existsSync(SCENE_FILE)) {
  const defaultScene = JSON.parse(
    fs.readFileSync(path.join(CODE, 'scene', 'default.json'), 'utf8')
  );
  fs.writeFileSync(SCENE_FILE, JSON.stringify(defaultScene, null, 2));
}

const LOCAL_ORIGIN = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/;
const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({
  server,
  verifyClient: ({ origin }) => !origin || LOCAL_ORIGIN.test(origin)
});

// The viewer is same-origin, so no CORS headers are sent. This guard also
// refuses cross-site writes that don't need a preflight (form posts, uploads),
// so a web page open in the browser can't drive this server.
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && !LOCAL_ORIGIN.test(origin)) return res.status(403).json({ error: 'Cross-origin request refused' });
  next();
});
app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(CODE, 'public')));
app.use('/uploads', express.static(UPLOADS_DIR));
app.use('/exports', express.static(EXPORTS_DIR));
app.use('/deliverables', express.static(path.join(ROOT, 'deliverables')));
app.use('/projects', express.static(path.join(ROOT, 'projects')));

// ── WebSocket broadcast ────────────────────────────────────────────────────
function broadcast(msg) {
  const payload = JSON.stringify(msg);
  wss.clients.forEach(client => {
    if (client.readyState === WebSocket.OPEN) client.send(payload);
  });
}

wss.on('connection', ws => {
  // Send current scene immediately on connect
  try {
    const scene = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8'));
    ws.send(JSON.stringify({ type: 'scene_update', scene }));
  } catch (e) { /* ignore */ }
  ws.send(JSON.stringify({ type: 'status', message: 'Connected to 3D Agent server' }));
});

// ── Watch scene file for changes (Claude writes → viewer reacts) ───────────
const watcher = chokidar.watch(SCENE_FILE, { persistent: true, awaitWriteFinish: { stabilityThreshold: 100 } });
watcher.on('change', () => {
  try {
    const scene = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8'));
    broadcast({ type: 'scene_update', scene });
    console.log(`[scene] Updated – ${scene.objects?.length ?? 0} objects`);
  } catch (e) {
    broadcast({ type: 'error', message: `Scene parse error: ${e.message}` });
  }
});

// ── REST API ───────────────────────────────────────────────────────────────
app.get('/api/scene', (req, res) => {
  res.sendFile(SCENE_FILE);
});

app.post('/api/scene', (req, res) => {
  try {
    fs.writeFileSync(SCENE_FILE, JSON.stringify(req.body, null, 2));
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.patch('/api/scene/object/:id', (req, res) => {
  try {
    const scene = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8'));
    const idx = scene.objects.findIndex(o => o.id === req.params.id);
    if (idx === -1) return res.status(404).json({ error: 'Object not found' });
    scene.objects[idx] = { ...scene.objects[idx], ...req.body };
    fs.writeFileSync(SCENE_FILE, JSON.stringify(scene, null, 2));
    res.json({ success: true, object: scene.objects[idx] });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.delete('/api/scene/object/:id', (req, res) => {
  try {
    const scene = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8'));
    scene.objects = scene.objects.filter(o => o.id !== req.params.id);
    fs.writeFileSync(SCENE_FILE, JSON.stringify(scene, null, 2));
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── File upload (drag-and-drop from viewer) ────────────────────────────────
const storage = multer.diskStorage({
  destination: UPLOADS_DIR,
  filename: (req, file, cb) => cb(null, Date.now() + '_' + file.originalname)
});
const upload = multer({ storage, limits: { fileSize: 100 * 1024 * 1024 } });

app.post('/api/upload', upload.single('file'), (req, res) => {
  const url = `/uploads/${req.file.filename}`;
  const originalName = req.file.originalname;
  const ext = path.extname(originalName).toLowerCase().slice(1);
  res.json({ success: true, url, filename: originalName, format: ext });
});

// ── Export endpoint ────────────────────────────────────────────────────────
app.post('/api/export', (req, res) => {
  try {
    const { data, encoding } = req.body;
    const filename = path.basename(String(req.body.filename || ''));
    if (!filename || filename.startsWith('.')) return res.status(400).json({ error: 'Invalid filename' });
    const outPath = path.join(EXPORTS_DIR, filename);
    if (encoding === 'base64') {
      fs.writeFileSync(outPath, Buffer.from(data, 'base64'));
    } else {
      fs.writeFileSync(outPath, data, 'utf8');
    }
    res.json({ success: true, url: `/exports/${filename}` });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Analysis endpoint (returns printability metrics) ─────────────────────
app.post('/api/analyze', (req, res) => {
  // Thin wrapper – actual analysis done in browser via Three.js geometry
  // This endpoint can be extended for server-side tools (OpenSCAD, Meshy, etc.)
  res.json({ status: 'ok', message: 'Use client-side analysis tools in the viewer' });
});

// ── Project bundle (.3dap) ────────────────────────────────────────────────

// Project slugs become directory names, so they must be
// a single plain path segment.
function safeSlug(slug) {
  return typeof slug === 'string' && /^[a-z0-9][a-z0-9._-]*$/i.test(slug) && !slug.includes('..') ? slug : null;
}

// A project is projects/<slug>/ (written by the toolbox). deliverables/<slug>/ is the
// older hand-written layout and is still read.
function projectBase(slug) {
  for (const kind of ['projects', 'deliverables']) {
    const dir = path.join(ROOT, kind, slug);
    if (fs.existsSync(dir)) return dir;
  }
  return path.join(ROOT, 'projects', slug);
}

function listProjects() {
  const names = new Set();
  for (const kind of ['projects', 'deliverables']) {
    const dir = path.join(ROOT, kind);
    if (!fs.existsSync(dir)) continue;
    for (const d of fs.readdirSync(dir, { withFileTypes: true })) if (d.isDirectory()) names.add(d.name);
  }
  return [...names].sort();
}

function activeProject() {
  try {
    const meta = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8')).metadata || {};
    const all = listProjects();
    if (safeSlug(meta.project) && all.includes(meta.project)) return meta.project;
    const slug = (meta.name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    if (all.includes(slug)) return slug;
    return all[0] || null;
  } catch {
    return listProjects()[0] || null;
  }
}

// Every file of one type under a project, a few levels deep, as panel entries.
function collect(projectSlug, ext, format) {
  if (!projectSlug) return {};
  const base = projectBase(projectSlug);
  const found = {};
  const walk = (dir, depth) => {
    if (depth > 3 || !fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.') || entry.name === 'view' || entry.name === 'imports') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full, depth + 1);
      else if (entry.name.toLowerCase().endsWith(ext) && fs.statSync(full).size < 5 * 1024 * 1024) {
        const rel = path.relative(base, full);
        const slug = rel.replace(/[\\/]/g, '--').slice(0, -ext.length);
        found[slug] = {
          slug,
          title: entry.name.slice(0, -ext.length).replace(/^\d+-/, '').replace(/[-_]/g, ' '),
          format,
          path: rel,
          content: fs.readFileSync(full, 'utf8')
        };
      }
    }
  };
  walk(base, 0);
  return found;
}

const readDocs = (slug) => collect(slug, '.md', 'markdown');
const readDrawings = (slug) => collect(slug, '.svg', 'svg');

// Read full bundle (scene + docs + drawings)
app.get('/api/project/bundle', (req, res) => {
  try {
    const scene = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8'));
    const slug = safeSlug(req.query.project) || activeProject();
    const docs = readDocs(slug);
    const drawings = readDrawings(slug);

    res.json({
      format: '3d-agent-project',
      version: '1.0',
      metadata: {
        name: scene?.metadata?.name || 'Untitled',
        description: scene?.metadata?.description || '',
        units: scene?.metadata?.units || 'mm',
        projectSlug: slug,
        exportedAt: new Date().toISOString()
      },
      scene,
      documents: docs,
      drawings
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// List documents only (for the panel — lightweight)
app.get('/api/project/documents', (req, res) => {
  try {
    const slug = safeSlug(req.query.project) || activeProject();
    const docs = readDocs(slug);
    const drawings = readDrawings(slug);
    // Strip content for index — just metadata
    const docsIndex = Object.fromEntries(
      Object.entries(docs).map(([k, v]) => [k, { slug: v.slug, title: v.title, format: v.format, path: v.path, size: v.content.length }])
    );
    const drawingsIndex = Object.fromEntries(
      Object.entries(drawings).map(([k, v]) => [k, { slug: v.slug, title: v.title, format: v.format, path: v.path, size: v.content.length }])
    );
    res.json({ project: slug, documents: docsIndex, drawings: drawingsIndex });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Read one document or drawing
app.get('/api/project/doc/:slug', (req, res) => {
  try {
    const slug = safeSlug(req.query.project) || activeProject();
    const docs = readDocs(slug);
    const drawings = readDrawings(slug);
    const item = docs[req.params.slug] || drawings[req.params.slug];
    if (!item) return res.status(404).json({ error: 'Not found' });
    res.json(item);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Save one document
app.post('/api/project/doc/:slug', (req, res) => {
  try {
    const projectSlug = safeSlug(req.query.project) || activeProject();
    if (!projectSlug) return res.status(400).json({ error: 'No active project' });
    const projectDir = projectBase(projectSlug);
    fs.mkdirSync(projectDir, { recursive: true });
    const { content, path: relPath } = req.body;
    if (!content || !relPath) return res.status(400).json({ error: 'content and path required' });
    // Sandbox: never escape the project directory
    const target = path.resolve(projectDir, relPath);
    if (!target.startsWith(projectDir + path.sep)) return res.status(400).json({ error: 'Invalid path' });
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content, 'utf8');
    res.json({ success: true, path: relPath });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Import full bundle — overwrites scene + writes documents
app.post('/api/project/bundle', (req, res) => {
  try {
    const bundle = req.body;
    if (bundle.format !== '3d-agent-project') {
      return res.status(400).json({ error: 'Not a 3d-agent-project bundle' });
    }
    if (bundle.scene) {
      fs.writeFileSync(SCENE_FILE, JSON.stringify(bundle.scene, null, 2));
    }
    const slug = safeSlug(bundle.metadata?.projectSlug)
      || (bundle.metadata?.name || 'imported').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
      || 'imported';
    const projectDir = projectBase(slug);
    fs.mkdirSync(projectDir, { recursive: true });
    fs.mkdirSync(path.join(projectDir, 'drawings'), { recursive: true });

    for (const doc of Object.values(bundle.documents || {})) {
      const target = path.resolve(projectDir, doc.path);
      if (!target.startsWith(projectDir + path.sep)) continue;
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, doc.content, 'utf8');
    }
    for (const drg of Object.values(bundle.drawings || {})) {
      const target = path.resolve(projectDir, drg.path);
      if (!target.startsWith(projectDir + path.sep)) continue;
      fs.writeFileSync(target, drg.content, 'utf8');
    }
    res.json({ success: true, project: slug });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// List all known projects
app.get('/api/project/list', (req, res) => {
  res.json({ active: activeProject(), all: listProjects() });
});

// ── Serve index for any unknown path (SPA) ────────────────────────────────
app.get('*', (req, res) => {
  res.sendFile(path.join(CODE, 'public', 'index.html'));
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`3D Agent viewer on http://localhost:${PORT}`);
  console.log(`Data folder: ${ROOT}`);
});
