# Fixer Agent — web port status

## Task
Port the Python `invisible_secretary` service to a static, pure-ES-module web app
at `webcode/web/local/` (branch `feature/web-local-port`). Runs entirely in the
browser: no backend, no network, no build step.

## Status: DONE — committed (not pushed)

- Branch: `feature/web-local-port`
- Commit: `f760ead` — "web/local: static ES-module port of invisible_secretary (no backend)"
- 20 files, +2670 (all new under `webcode/web/local/`). `invisible_secretary/*`
  was read only, never modified.

## File list (`webcode/web/local/`)
Modules (mirror the Python package file-for-file):
- `schemas.js`            <- schemas.py
- `scope_store.js`        <- scope_store.py (localStorage key `data/scope.json`)
- `model_adapter.js`      <- model_adapter.py
- `local_qwen.js`         <- local_qwen.py (inert WebGPU/ONNX-or-no-op adapter)
- `model_registry.js`     <- model_registry.py (empty catalogue in the browser)
- `factory.js`            <- factory.py
- `router.js`             <- router.py
- `nodes.js`              <- nodes.py
- `engine.js`             <- engine.py (incl. a sync SHA-256, see fidelity #4)
- `bus.js`                <- bus.py
- `pipeline.js`           <- pipeline.py (worker stays unkillable)
- `runtime.js`            <- runtime.py
- `api.js`                <- server.py routes + a fetch shim (no backend)

Pages + assets:
- `index.html`   <- dashboard.html (renamed per acceptance: "opening index.html")
- `guide.html`   <- guide.html
- `scope.html`   <- scope.html
- `assets/app.css` (shared stylesheet; inline <style> merged here — styling agent owns it)

Tooling:
- `tests/smoke.mjs` (node:test — the acceptance gate)
- `serve.mjs` (dependency-free static server)
- `README.md`

## How to run
```
node --test webcode/web/local/tests/smoke.mjs      # acceptance gate
node webcode/web/local/serve.mjs                   # -> http://127.0.0.1:8080/
#   then open the URL and click the example chips
```

## Verification (all green)
- `node --test webcode/web/local/tests/smoke.mjs` -> **7/7 pass**:
  out-of-scope rejects; low-confidence clarifies; R3 needs_approval; R2
  route_to_queue succeeds; high urgency never bypasses approval; approval
  invalidation on changed payload; fetch shim routes /api/* with no network.
- Cross-check vs the Python engine (rules-only) on the 5 example chips + 2 edge
  cases -> **identical** state / intent / node / risk_level / requires_approval /
  urgency_level / confidence / parameters.
- Payload hash fidelity: JS `payloadHash` == Python
  `hashlib.sha256(json.dumps(p,sort_keys=True)).hexdigest()[:16]`
  (verified equal: `72a12fc321b26a1a`) -> approval ids match.
- `serve.mjs`: `/`, `/index.html`, `/guide`, `/scope`, `/assets/app.css` -> 200;
  unknown -> 404; a stray `/api/*` (shim not loaded) -> 501.
- All three page module scripts pass `node --check`.
- No absolute `href="/..."`, no inline `<style>`, every fetch target is `/api/*`.

## Python behaviour that could NOT be ported faithfully
1. **Model enhancement is inert.** Python can load a real Qwen2.5-0.5B ONNX bundle
   and let the model ENHANCE the rules. The browser build has no weights and no
   transformers.js runtime, so `local_qwen.js` is a no-op adapter: `available()`
   returns false and every run is RULES-ONLY. This is the safe-original path, so
   all outcomes equal Python run with `use_model=False`. A real backend can be
   injected via `window.__IS_ONNX_BACKEND__` — no wiring changes required. There
   is (as in Python) NO cloud fallback.
2. **Filesystem -> storage.** `data/scope.json` is a file in Python; here it is a
   `localStorage` key of the same name. `model_registry` discovery returns `[]`
   (nothing on disk). Semantics preserved.
3. **No threads / no auto-port bind / no uvicorn.** `asyncio.to_thread` becomes a
   plain `await`; the FastAPI server (first-free-port 4500-4900, `data/state.json`)
   is replaced by the in-page fetch shim. Route contracts are preserved, including
   `?mode=async` -> `{job_id, state:"accepted"}` and `GET /api/jobs/{id}`.
4. **Payload hash.** Python uses `hashlib.sha256`. Implemented a synchronous
   SHA-256 in `engine.js` plus a Python-compatible `json.dumps(sort_keys=True)`
   (`", "` / `": "` separators) so `hexdigest()[:16]` is byte-identical (verified).
5. **`scope_store.overview()` is now `async`** (it dynamically imports router/nodes
   to avoid a module import cycle). Callers `await` it; the Python version is sync.
6. **Pages are ES modules.** Each page's classic `<script>` became
   `<script type="module">` that first `import "./api.js"` and, at the end,
   `Object.assign(globalThis, {...})` to re-expose the functions referenced by
   inline `onclick`/`onsubmit` (module scope would otherwise hide them). Body JS
   is otherwise near-verbatim. Nav links were made relative
   (`/guide`->`guide.html`, etc.) so pages work under both serve.mjs and `file://`.
7. **`assets/app.css` is a merge** of the three inline `<style>` blocks. Two
   benign last-wins collisions: `.card .n` (24px chosen over scope's 22px) and
   `.note` (guide's bordered version chosen). The styling agent owns this file;
   the original guide's `var(--llm)` was undefined in the Python source too and was
   left untouched.

## Blockers
None. Commit is local; say the word to push `feature/web-local-port`.

## Follow-up — shared nav bar + Routes page (DONE, same branch)
- `webcode/web/local/nav.js` — shared top nav, injected into each page's
  `<nav class="navbar" id="navbar" data-page="...">` placeholder and highlights
  the current page. Pages: Dashboard, Element guide, Scope, Routes.
- `webcode/web/local/routes.html` — a styled page listing the static file routes
  (serve.mjs) and the API routes (the in-browser fetch shim), with status codes.
- Each page header's ad-hoc `<a class="nav">` links were replaced by the navbar
  placeholder; each page's module script now also `import "./nav.js";`.
- `serve.mjs` maps `/routes` and `/routes.html` -> `routes.html`.
- `assets/app.css` gained `.navbar` + `.route` styles and `.wrap section.full`
  (full-width section). (Styling agent still owns this file.)
- Verified: serve.mjs `200` for `/`, `/routes`, `/routes.html`, `/nav.js`,
  `/guide`; direct `/api/scope` -> `501` (shim is in-page, as documented);
  `node --test` still `7/7 pass`. Routes: see http://127.0.0.1:8080/routes
