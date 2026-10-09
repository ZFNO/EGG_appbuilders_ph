# Invisible Secretary — Async Remodel Spec (queue-first, multi-port)

Status: **approved to build**  ·  Author: operator  ·  Date: 2026-10-10
Scope: `invisible_secretary/` (engine, router, model layer, nodes, entrypoints)

---

## 1. Goal

Make the entire project **async-first** with a single **queue spine**:

1. Every input — CLI, HTTP, future sources — becomes a **message** on **one**
   queue.
2. **One long-running asyncio worker task** consumes that queue and pushes each
   message through the pipeline.
3. The pipeline is a **list of stages**; today it has **one pipe** (the
   secretary). More pipes can be appended without touching the worker.
4. A **FastAPI/uvicorn server** binds the **first free port in 4500–4900**,
   **prints the chosen port**, and is only a *producer* onto the same queue.

Non-negotiable: the safety invariants (risk R0–R3, payload-bound approvals,
idempotency, no cloud fallback) are **unchanged** — they are re-hosted inside the
worker, not rewritten.

---

## 2. Principles / invariants

| # | Rule |
|---|------|
| P1 | **One event loop.** Orchestration is `asyncio`. Concurrency = tasks, not threads. |
| P2 | **Threads only for blocking compute.** The ONNX/Qwen call is CPU-bound and blocking; it is the *only* thing offloaded, via `asyncio.to_thread(...)`. |
| P3 | **Queue is the spine; ports are producers.** A queue is never owned by a port. Many producers → one queue → one consumer (for now). |
| P4 | **No direct calls across layers.** Callers enqueue a message; they never call `engine.process()` from a request handler. |
| P5 | **Safety unchanged.** Router policy, risk levels, approval binding, idempotency behaviour are preserved bit-for-bit. |
| P6 | **One consumer = serialized processing.** Accepted for now; N-consumer fan-out is a supported future switch. |
| P7 | **Fail-soft.** A model crash/inference error degrades to rules; it never drops or crashes the worker. |

---

## 3. Current state (baseline, all synchronous)

| Module | Role | Sync/blocking? |
|---|---|---|
| `engine.py` | `Engine.process/approve/reject`, state machine, audit, approvals | sync |
| `router.py` | `Router.route()` — validate, dispatch, urgency, policy | sync (pure) |
| `model_adapter.py` | `HybridAdapter.classify()` rules ⊕ model, abstain on conflict | sync |
| `local_qwen.py` | `QwenOnnxAdapter.classify()` — onnxruntime greedy decode | **blocks ~0.7s CPU** |
| `nodes.py` | mock node adapters, `default_nodes()` | sync (mock, fast) |
| `api.py` | stdlib `ThreadingHTTPServer`, fixed port 8765 | sync, threaded |
| `cli.py` | demo + model picker | sync |

Only `local_qwen` genuinely blocks; everything else is cheap. The remodel must
therefore offload **model inference**, not the whole engine.

---

## 4. Target architecture

```
 producers                         spine                    consumer
 ┌──────────┐                    ┌────────┐              ┌───────────────────┐
 │ CLI      │──┐                 │        │              │ worker task       │
 ├──────────┤  │   put(msg)      │  asyncio.Queue        │  (single, async)  │
 │ HTTP :45xx│──┼────────────────▶│  (maxsize=N)          │  for msg in queue │
 ├──────────┤  │                 │        │  get(msg) ──▶│   run pipeline    │
 │ future   │──┘                 └────────┘              └─────────┬─────────┘
 │ sources  │                                                        │
 └──────────┘                                    ┌───────────────────▼───────────────┐
                                                 │ pipeline: [secretary_stage, ...]  │
                                                 │   await to_thread(inference)      │
                                                 └───────────────────────────────────┘
```

- **Producers**: HTTP handlers, CLI loop, (later) file/webhook watchers.
- **Spine**: one `asyncio.Queue[Message]` created at app startup.
- **Consumer**: one `worker()` task started in the FastAPI lifespan.
- **Pipeline**: ordered stages; `secretary_stage` calls the (unchanged) engine.

---

## 5. Components & contracts

### 5.1 Message envelope (`bus.py`)
```python
@dataclass(slots=True)
class Message:
    id: str                     # == request_id (idempotency key)
    kind: str                   # "secretary.request" | future kinds
    payload: dict               # {"text": "..."}
    source: str                 # "http:4523" | "cli" | "watcher"
    created: float
    replies: asyncio.Future | None = None   # resolved with the result Event dict
```

### 5.2 Queue / Bus (`bus.py`)
```python
class Bus:
    def __init__(self, maxsize=256): self.q = asyncio.Queue(maxsize)
    async def publish(self, msg) -> None: ...      # awaits (backpressure)
    async def subscribe(self): ...                 # async iterator
```
- Bounded queue → natural backpressure; `publish` awaits when full.
- In-memory only for now; a durable backend (replay from `data/state.json`) is a
  drop-in later behind the same interface.

### 5.3 Worker (`bus.py` / `runtime.py`)
```python
async def worker(bus, pipeline, engine, stop):
    while not stop.is_set():
        msg = await bus.get()
        try:
            await run_pipeline(pipeline, msg, engine)
        except Exception as e:              # never kill the worker
            resolve_reply(msg, {"state":"failed","error":str(e)})
        finally:
            bus.task_done()
```

### 5.4 Pipeline & stages (`pipeline.py`)
- A stage: `async def stage(msg, ctx) -> StageOutcome`.
- `PIPELINE = [secretary_stage]` — the single pipe.
- `secretary_stage` is the *only* place the legacy engine is touched:
  ```python
  async def secretary_stage(msg, ctx):
      ev = await ctx.to_thread(ctx.engine.process, msg.id, msg.payload["text"])
      return StageOutcome(result=ev.to_dict())
  ```
  Note `asyncio.to_thread` — this is P2 in action; the engine stays sync inside.
- Registry `STAGE_REGISTRY: dict[str, stage]` so new pipes are named/appended.

### 5.5 Async engine facade (thin, keeps `Engine` sync)
- `Engine` is **not** rewritten async. It is called from a thread so its internal
  locks/sync code stay valid and its tests keep passing.
- Optional async sugar: `class AsyncEngine: async def process(...)` → wraps
  `to_thread(self._engine.process, ...)` for programmatic callers.

### 5.6 FastAPI server (`server.py`)
- `create_app(bus, engine)` builds routes + `lifespan` that starts `worker`.
- Endpoints (superset of old API, same paths where possible):
  | Method | Path | Behaviour |
  |---|---|---|
  | POST | `/api/route` | enqueue + **await future** → returns Event JSON (sync semantics preserved) |
  | POST | `/api/route?mode=async` | enqueue only → `202 {"job_id": ...}` |
  | GET | `/api/jobs/{id}` | poll a job's status/result |
  | POST | `/api/approvals/{id}/approve` | enqueue an approval message |
  | POST | `/api/approvals/{id}/reject` | enqueue a reject message |
  | GET | `/api/activity`, `/api/nodes` | read from engine (unchanged shape) |
  | GET | `/` | dashboard |
- **Response semantics** (fixes the "drop and forget" gap): each request attaches
  an `asyncio.Future` to its `Message`; the worker resolves it; the handler
  `await`s it. `?mode=async` skips the future for fire-and-forget callers.

### 5.7 Port allocation (`server.py`)
```python
def bind_first_free(host, lo=4500, hi=4900):
    for port in range(lo, hi + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port)); s.listen(); return s, port   # bind-first, not check-then-bind
        except OSError:
            s.close()
    raise RuntimeError("no free port in 4500-4900")
```
- uvicorn runs **on the pre-bound socket**: `server.run(sockets=[sock])`.
- Print **after** binding: `Invisible Secretary listening on http://127.0.0.1:45xx`.
- The port is also written to `data/state.json` so other local processes can
  discover it.

---

## 6. File plan

**New**
- `invisible_secretary/bus.py` — `Message`, `Bus`, `worker`, `run_pipeline`.
- `invisible_secretary/pipeline.py` — `secretary_stage`, `PIPELINE`, registry.
- `invisible_secretary/server.py` — FastAPI app, lifespan, port scan, `main()`.
- `invisible_secretary/runtime.py` — app wiring: build bus+engine+pipeline, `asyncio.run`.
- `tests/test_bus.py`, `tests/test_server.py` — async pipeline + port-scan tests.

**Modified**
- `__init__.py` — export `Bus`, `Message`, `create_app`, `AsyncEngine` (keep old exports).
- `cli.py` — interact through the bus (publish + await) instead of calling the engine directly.
- `README.md` — new "Run it" for `server.py`, ports, async model.
- `.env.example` — `IS_HOST`, `IS_PORT_RANGE`, `IS_QUEUE_MAXSIZE`, `IS_MODEL`.

**Deprecated (kept as shims)**
- `api.py` — re-export `create_app` so old `python -m invisible_secretary.api` still works.
- `factory.py` — unchanged; used by the runtime to build the adapter.

---

## 7. Concurrency, backpressure, shutdown

- **Backpressure**: bounded `Queue`. `publish()` awaits when full; HTTP handlers
  return `503 retry-after` if `mode=async` and the queue is saturated.
- **Serialization**: single worker ⇒ one job at a time. Escape hatch documented:
  spawn `IS_WORKERS=n` identical worker tasks on the same queue (engine is
  per-request idempotent by `request_id`).
- **Shutdown**: `lifespan` sets a `stop` event, `await q.join()`, cancels the
  worker, closes the socket. No in-flight message is dropped silently.

---

## 8. Configuration (env)

| Var | Default | Meaning |
|---|---|---|
| `IS_HOST` | `127.0.0.1` | bind host |
| `IS_PORT_RANGE` | `4500-4900` | scanned bind range |
| `IS_QUEUE_MAXSIZE` | `256` | spine depth |
| `IS_WORKERS` | `1` | worker tasks (future fan-out) |
| `IS_MODEL` | _(auto)_ | model id/name/path (already honoured) |

---

## 9. Migration phases (each phase leaves the app runnable)

1. **P0 — Spec** (this doc).
2. **P1 — Async core**: `bus.py` + `pipeline.py` + `runtime.py`; worker runs the
   secretary stage; unit tests drive the bus directly. Old `api.py`/`cli.py` still work.
3. **P2 — Server**: `server.py` with port scan 4500–4900 + printed port + `/api/route`.
4. **P3 — Entrypoint migration**: `cli.py` publishes via the bus; `api.py` becomes a shim.
5. **P4 — Polish**: `data/state.json` port discovery, `?mode=async` job polling, dashboard hits new endpoints, backpressure 503, README.

---

## 10. Acceptance criteria

- [ ] `python -m invisible_secretary.server` binds the first free port in 4500–4900
      and **prints** `http://127.0.0.1:<port>`.
- [ ] Two servers launched back-to-back pick **different** ports (4500, 4501…).
- [ ] `POST /api/route` returns the same Event JSON shape as today, after the
      result is produced by the **worker** (not the handler).
- [ ] All inputs traverse the single queue (assert via a bus counter / test).
- [ ] Blocking inference runs off the loop (`asyncio.to_thread`) — loop stays
      responsive (heartbeat test during a slow inference).
- [ ] Existing 29 tests still pass; new bus/server tests pass.
- [ ] Safety untouched: R3 approval + payload-hash invalidation + out-of-scope
      rejection still behave as before.

---

## 11. Non-goals (this pass)

- No persistence/durable queue (interface allows it later).
- No multi-worker fan-out by default (`IS_WORKERS=1`).
- No auth on the HTTP surface (localhost only).
- No rewrite of routing/policy/nodes — only re-hosting behind the queue.

---

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Blocking call accidentally left on the loop | single choke point: `to_thread` inside `secretary_stage`; heartbeat test guards it |
| Port check-then-bind race | bind-first loop, catch `OSError` |
| Lost results with fire-and-forget | default mode awaits a `Future`; async mode exposes `/api/jobs/{id}` |
| Behaviour drift in engine | engine untouched; wrapped, not rewritten; tests unchanged |
| Unbounded memory under load | bounded queue + 503 backpressure |
