# Invisible Secretary - static web port (browser, no backend)

A 1:1 pure-ES-module JavaScript port of the Python `invisible_secretary` service.
It runs **entirely in the browser**: no server, no network, no build step. The
modules mirror the Python files one-for-one.

## Run

### Dev server (Vite, hot reload)

```bash
cd webcode/web/local
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
node webcode/web/local/serve.mjs          # -> http://127.0.0.1:8080/
# optional: node webcode/web/local/serve.mjs 8081
```

### Tests

```bash
node --test webcode/web/local/tests/smoke.mjs   # the acceptance gate
```

Then open the URL and use the example chips on the dashboard. Pages:

- `index.html`  - dashboard (port of `dashboard.html`)
- `guide.html`  - element guide (port of `guide.html`)
- `scope.html`  - live scope editor (port of `scope.html`)

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
| (shared CSS)              | `assets/app.css`                          |

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
