const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const chokidar = require('chokidar');
const multer = require('multer');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

const PORT = 3030;
const ROOT = __dirname;
const SCENE_FILE = path.join(ROOT, 'scene', 'current.json');
const UPLOADS_DIR = path.join(ROOT, 'uploads');
const EXPORTS_DIR = path.join(ROOT, 'exports');

// Bootstrap directories
for (const dir of [path.join(ROOT, 'scene'), UPLOADS_DIR, EXPORTS_DIR]) {
  fs.mkdirSync(dir, { recursive: true });
}

// Seed a default scene on first run
if (!fs.existsSync(SCENE_FILE)) {
  const defaultScene = JSON.parse(
    fs.readFileSync(path.join(ROOT, 'scene', 'default.json'), 'utf8')
  );
  fs.writeFileSync(SCENE_FILE, JSON.stringify(defaultScene, null, 2));
}

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(ROOT, 'public')));
app.use('/uploads', express.static(UPLOADS_DIR));
app.use('/exports', express.static(EXPORTS_DIR));
app.use('/deliverables', express.static(path.join(ROOT, 'deliverables')));

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
    const { filename, data, encoding } = req.body;
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

// Map of well-known document slug → relative path inside deliverables/
const DOC_FILES = {
  'design-brief':          'briefs/brief.md',
  'design-document':       'design-document.md',
  'bom':                   'BOM.md',
  'manufacturing-plan':    'manufacturing-plan.md',
  'assembly-instructions': 'assembly-instructions.md',
  'readme':                'README.md'
};

function listProjects() {
  const dir = path.join(ROOT, 'deliverables');
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter(d => d.isDirectory())
    .map(d => d.name);
}

function activeProject() {
  // Use the project name from the scene's metadata.name slug, fallback to first deliverables dir
  try {
    const scene = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8'));
    const slug = (scene?.metadata?.name || '').toLowerCase()
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    if (slug) {
      const candidate = path.join(ROOT, 'deliverables', slug);
      if (fs.existsSync(candidate)) return slug;
      // fuzzy match: pick a deliverables dir that starts with slug prefix
      const dirs = listProjects();
      const prefix = slug.split('-').slice(0, 2).join('-');
      const match = dirs.find(d => d.startsWith(prefix));
      if (match) return match;
    }
  } catch {}
  const dirs = listProjects();
  return dirs[0] || null;
}

function readDocs(projectSlug) {
  if (!projectSlug) return {};
  const projectDir = path.join(ROOT, 'deliverables', projectSlug);
  const docs = {};
  for (const [slug, rel] of Object.entries(DOC_FILES)) {
    const p = path.join(projectDir, rel);
    if (fs.existsSync(p)) {
      docs[slug] = {
        slug,
        title: rel.split('/').pop().replace(/\.md$/, ''),
        format: 'markdown',
        path: rel,
        content: fs.readFileSync(p, 'utf8')
      };
    }
  }
  return docs;
}

function readDrawings(projectSlug) {
  if (!projectSlug) return {};
  const dir = path.join(ROOT, 'deliverables', projectSlug, 'drawings');
  if (!fs.existsSync(dir)) return {};
  const drawings = {};
  for (const file of fs.readdirSync(dir).sort()) {
    if (!file.endsWith('.svg')) continue;
    const slug = file.replace(/\.svg$/, '');
    drawings[slug] = {
      slug,
      title: slug.replace(/^\d+-/, '').replace(/-/g, ' '),
      format: 'svg',
      path: `drawings/${file}`,
      content: fs.readFileSync(path.join(dir, file), 'utf8')
    };
  }
  return drawings;
}

// Read full bundle (scene + docs + drawings)
app.get('/api/project/bundle', (req, res) => {
  try {
    const scene = JSON.parse(fs.readFileSync(SCENE_FILE, 'utf8'));
    const slug = req.query.project || activeProject();
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
    const slug = req.query.project || activeProject();
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
    const slug = req.query.project || activeProject();
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
    const projectSlug = req.query.project || activeProject();
    if (!projectSlug) return res.status(400).json({ error: 'No active project' });
    const projectDir = path.join(ROOT, 'deliverables', projectSlug);
    fs.mkdirSync(projectDir, { recursive: true });
    const { content, path: relPath } = req.body;
    if (!content || !relPath) return res.status(400).json({ error: 'content and path required' });
    // Sandbox: never escape the project directory
    const target = path.resolve(projectDir, relPath);
    if (!target.startsWith(projectDir)) return res.status(400).json({ error: 'Invalid path' });
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
    const slug = bundle.metadata?.projectSlug
      || (bundle.metadata?.name || 'imported').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    const projectDir = path.join(ROOT, 'deliverables', slug);
    fs.mkdirSync(projectDir, { recursive: true });
    fs.mkdirSync(path.join(projectDir, 'drawings'), { recursive: true });

    for (const doc of Object.values(bundle.documents || {})) {
      const target = path.resolve(projectDir, doc.path);
      if (!target.startsWith(projectDir)) continue;
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, doc.content, 'utf8');
    }
    for (const drg of Object.values(bundle.drawings || {})) {
      const target = path.resolve(projectDir, drg.path);
      if (!target.startsWith(projectDir)) continue;
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
  res.sendFile(path.join(ROOT, 'public', 'index.html'));
});

server.listen(PORT, () => {
  console.log(`
╔═══════════════════════════════════════╗
║       3D Agent Server running         ║
║   http://localhost:${PORT}              ║
║                                       ║
║  Scene file: scene/current.json       ║
║  Edit it → viewer updates live        ║
╚═══════════════════════════════════════╝
`);
});
