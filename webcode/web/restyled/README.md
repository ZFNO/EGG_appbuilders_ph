# Invisible Secretary - static web port (browser, no backend) -- restyled build

A 1:1 pure-ES-module JavaScript port of the Python `invisible_secretary` service.
It runs **entirely in the browser**: no server, no network, no build step. The
modules mirror the Python files one-for-one.

This folder (`webcode/web/restyled`) is a **sibling copy** of `webcode/web/local`
with a new visual theme applied. Runtime JS logic is unchanged - only the look
(HTML head, `assets/theme.css`, `assets/app.css`) was restyled.

## Run

### Dev server (Vite, hot reload)

```bash
cd webcode/web/restyled
bun install          # once
bun run dev          # -> http://localhost:8080/  (HMR on)
```

Edit any `.js` / `.css` / `.html` and the page updates live. `vite.config.js`
sets the root to this folder, lists the four pages as MPA entry points, and adds
a small `friendlyRoutes` middleware so `/`, `/guide`, `/scope` and `/routes` work
in dev just like `serve.mjs` (`appType: "mpa"` keeps unknown paths a real 404
rather than silently serving `index.html`). `bun run build` emits `dist/`.

### Zero-dependency static server (no build step)

```bash
node webcode/web/restyled/serve.mjs          # -> http://127.0.0.1:8080/
# optional: node webcode/web/restyled/serve.mjs 8081
```

### Tests

```bash
node --test webcode/web/restyled/tests/smoke.mjs
```

Then open the URL and use the example chips on the dashboard. Pages:

- `index.html`  - dashboard (port of `dashboard.html`)
- `guide.html`  - element guide (port of `guide.html`)
- `scope.html`  - live scope editor (port of `scope.html`)
- `routes.html` - route listing (static + API shim)

## Theme

The look is a bold, high-contrast, angular "menu" aesthetic: neon green on a
black base, heavy condensed UPPERCASE display headings (Anton / Bebas Neue),
wide-tracked uppercase labels (Oswald), slanted/skewed lettering
(`skewX(-3deg)`, up to `-14deg` on decorative shapes), horizontally compressed
titles (`scaleX(.90)`), hard crisp offset drop-shadows (solid colour, zero
blur), thick text strokes, a flat skewed top bar with a thick accent underline,
near-black panels, and sharp diagonal accents (corner triangles, skewed colour
slabs, 45-degree hatch backgrounds). The background is an animated, GPU-friendly
layer of slowly drifting diagonal stripes plus a gently pulsing neon-green glow;
it is disabled under `prefers-reduced-motion: reduce`.

### One place to re-theme: `assets/theme.css`

Every colour lives in a single `:root` block in **`assets/theme.css`** (loaded
before `assets/app.css`). No other stylesheet or page contains a colour literal -
all rules reference these variables, so re-skinning the whole app means editing
just that one block.

| Variable         | Role                                                       | Default                |
|------------------|------------------------------------------------------------|------------------------|
| `--bg`           | Page base colour                                           | `#050505`              |
| `--ink`          | Deepest black (input wells, code chips)                    | `#000000`              |
| `--panel`        | Near-black panel surface                                   | `#0b0d0b`              |
| `--panel-2`      | Raised panel surface (rows, results)                       | `#111511`              |
| `--line`         | Hairlines / borders                                        | `#213021`              |
| `--nav-bg`       | Translucent sticky top-bar background                      | `rgba(5,5,5,.88)`      |
| `--fg`           | Primary text                                               | `#e8ffe4`              |
| `--muted`        | Secondary text / labels                                    | `#7f8f7b`              |
| `--white`        | Pure white for display headings                            | `#ffffff`              |
| `--stroke`       | Text-stroke / hard-shadow base                             | `#000000`              |
| `--accent`       | Primary accent (neon green)                                | `#39ff14`              |
| `--accent-2`     | Secondary accent (neon green)                              | `#00ff41`              |
| `--accent-dk`    | Darker green (slabs, offset shadows)                       | `#0b7a1e`              |
| `--accent-soft`  | Faint green wash (hover fills, notes)                      | `rgba(57,255,20,.08)`  |
| `--accent-line`  | Soft green borders                                         | `rgba(57,255,20,.35)`  |
| `--accent-glow`  | Glow colour for the pulsing background                     | `rgba(57,255,20,.55)`  |
| `--shadow-hard`  | Solid offset drop-shadow colour                            | `rgba(57,255,20,.55)`  |
| `--shadow-soft`  | Soft depth shadow                                          | `rgba(0,0,0,.6)`       |
| `--scan`         | 45-degree hatch overlay on panels                          | `rgba(57,255,20,.035)` |
| `--stripe-a/_b`  | Animated diagonal-stripe colours                           | `#060706` / `#0d100d`  |
| `--ok` `--warn` `--bad` `--info` `--llm` | Status colours (`--info`/`--llm` fall back to the accent) | neon green / amber / red |
| `--skew`         | Text slant applied to headings and labels                  | `-3deg`                |
| `--skew-lg`      | Stronger slant for decorative shapes                       | `-14deg`               |
| `--compress`     | Horizontal compression for display titles                  | `scaleX(.90)`          |

To rebrand, change `--accent`, `--accent-2` and `--accent-dk` (and optionally
`--bg`/`--panel`) and the whole app follows.

## Module map (mirrors the Python package)

| Python                    | Browser                                   |
|---------------------------|-------------------------------------------|
| `schemas.py`              | `schemas.js`                              |
| `scope_store.py`          | `scope_store.js` (localStorage, not a file)|
| `model_adapter.py`        | `model_adapter.js`                        |
| `local_qwen.py`           | `local_qwen.js` (inert, rules-only)       |
| `model_registry.py`       | `model_registry.js` (empty catalogue)     |
| `factory.py`              | `factory.js`                              |
| `router.py`               | `router.js`                               |
| `nodes.py`                | `nodes.js`                                |
| `engine.py`               | `engine.js`                               |
| `bus.py`                  | `bus.js`                                  |
| `pipeline.py`             | `pipeline.js`                             |
| `runtime.py`              | `runtime.js`                              |
| `server.py` routes        | `api.js` (in-browser fetch shim)          |
| `dashboard/guide/scope.html` | `index.html` / `guide.html` / `scope.html` |
| (shared CSS)              | `assets/theme.css` + `assets/app.css`     |

## Behaviour preserved

- Deterministic **rule classifier is PRIMARY**; the local model only ENHANCES.
- On rule/model **disagreement the hybrid ABSTAINS** (confidence < floor `0.80`),
  so the router asks to **clarify** instead of guessing.
- Consequential actions (send / pay / delete / commit) return **needs_approval**
  bound to the **exact payload**; a changed payload invalidates the approval.
- **High urgency never bypasses authorization** (urgency is rule-derived).
- Only **allow-listed nodes** are dispatched.
- All integrations are **mocked** and labelled `simulated: true`.
- `localStorage` key `data/scope.json` is the live out-of-scope lever (the
  browser equivalent of the Python `data/scope.json` file); the scope page edits
  it live.
- No cloud fallback anywhere.

## API shim

`api.js` installs a `fetch` shim mapping the documented routes onto the
in-browser engine, so the page JS stays near-verbatim:

```
POST /api/route                          GET  /api/activity
POST /api/preview                        GET  /api/nodes
GET  /api/scope   POST /api/scope        GET  /api/model
POST /api/approvals/{id}/{approve|reject} GET /api/jobs/{id}
```

Nothing under `/api/` leaves the page.
