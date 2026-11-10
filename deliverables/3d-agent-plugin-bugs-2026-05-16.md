# 3D Agent plugin — bug report

**Plugin:** `3d-agent@My Uploads`
**Session date:** 2026-05-16
**User:** Tuck
**Reported from:** Cowork session designing a 2U rack drawer insert

---

## Issues (priority order)

### 1. No live preview path inside Cowork — BLOCKER

The plugin requires a Node server on `localhost:3030` started manually on the user's Mac. Cowork's bash runs in a Linux sandbox; `npm start` from there binds to sandbox-localhost, which the user's browser cannot reach. Result: user clicks preview, nothing happens.

**Fix options:**
- (a) Ship a static SVG/canvas fallback renderer that runs inside a Cowork artifact. CSP allowlist is currently Chart.js / Grid.js / Mermaid only — Three.js is blocked — so likely needs a vanilla SVG renderer that interprets `scene/current.json` directly.
- (b) Petition Anthropic to add Three.js to the Cowork CSP allowlist.
- (c) Detect Cowork mode in the `3d-start` skill and instead of attempting to launch, print the exact Mac terminal command for the user to run.
- (d) Wrap the existing viewer as a tiny Electron app the plugin can auto-launch on the host.

Recommendation: (c) short-term, (a) long-term.

---

### 2. Subagents write invalid JSON — BLOCKER

The `3d-specialist` subagent put JS arithmetic directly into JSON literals, e.g. `"position": [-171.65, 2.4 + 17.5, 63.4]` — 8 occurrences in a single scene. JSON parser fails at the first one, viewer renders nothing, no error surfaced to user.

**Fix:** mandatory JSON-validation step in the `3d-specialist` SKILL.md (also `engineer-designer`, `manager`). After every `scene/current.json` write, the agent must run `python3 -c "import json; json.load(open('scene/current.json'))"` (or equivalent Node check) and if it errors, fix and retry before reporting done.

`CLAUDE.md` rule #5 already says "Never leave malformed JSON — validate mentally before writing" — mental validation clearly isn't enough. Make it a programmatic check.

---

### 3. No streaming feedback during long agent runs

The `3d-specialist` ran for approximately 7 minutes silent. User reasonably thought the session had crashed.

**Fix:** add an "incremental progress" pattern to the subagent prompt — emit a one-line status every 60 seconds or after every major scene write. Orchestrator (parent agent / manager) surfaces those to the user.

---

### 4. Sandbox vs host path confusion in `3d-start`

The skill runs `node server.js` without checking whether it's in a Cowork sandbox. Needs environment detection — if paths look like `/sessions/*/mnt/` or shell is sandboxed, don't attempt to start; instead instruct the user to run on their Mac, with the exact command.

---

### 5. Design output quality

User reports the layout the `3d-specialist` produced has multiple problems (specifics to be enumerated by the user). Likely root cause: the subagent was given a brief from a parent agent that interpolated dimensions from a hand-drawn sketch and item photos without explicit user confirmation. Needs an "approve dimensions and item list" gate before geometry work begins.

---

### 6. Path translation tooling

The plugin needs a helper that, given a path under `/Users/tuck/Documents/...`, returns the corresponding sandbox `/sessions/.../mnt/...` path (and vice versa). Subagents currently spend time figuring this out per call.

---

## Reference artefacts

- **Broken scene** (now hand-fixed in this session): `/Users/tuck/Documents/E-Labs/Products/e_labs-claude/3D-Agent/scene/current.json` — diff against the agent's original output to see the exact arithmetic-in-JSON pattern that needs guarding against.
- **8 manual fixes applied this session:** all instances of `2.4 + 17.5` → `19.9`, and all instances of `62 + 12` → `74`.
