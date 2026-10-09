# Invisible Secretary — MVP (local-first AI operations assistant)

A quiet decision layer for SME owners, not a chat-first chatbot. It turns
incoming requests into routed actions and escalates ambiguous or consequential
decisions to the owner. **Local-first: no cloud inference, no hidden fallback.**

Built from the *Invisible Secretary — Agent Build Pack* spec (10 docs).

## Three layers (never blurred)
1. **Local model** (`local_qwen.py` + `model_adapter.py`) — bounded intent
   classification + schema-defined parameter extraction only. A deterministic
   rule classifier is the PRIMARY path; the real on-device **Qwen2.5-0.5B-Instruct
   q4 ONNX** model ENHANCES it. No tools, no permissions.
2. **Deterministic router** (`router.py`) — schema validation, allow-listed
   intent→node dispatch, urgency computed from rules (never from model
   confidence), risk/authorization policy. High urgency never bypasses auth.
3. **Node adapters** (`nodes.py`) — validate inputs, enforce business rules,
   execute a **mocked** integration, return a typed result. Consequential actions
   come back as `needs_approval` bound to the exact payload.

## On-device model (real, local)
`local_qwen.QwenOnnxAdapter` runs the bundled model through `onnxruntime`
(CPU, KV-cache greedy decode, no network):

* Model: `Qwen/Qwen2.5-0.5B-Instruct` q4 ONNX (786 MB) + `tokenizer.json`
* Canonical store: `<project>/models/<ModelName>/` — each model in its own
  folder (e.g. `models/Qwen2.5-0.5B-Instruct/`). Legacy bundle paths are still
  searched read-only, so nothing breaks if a copy lives elsewhere.
* `model_registry.discover_models()` lists every local model; the adapter,
  API and CLI all resolve through it.
* ~0.7 s per short classification on CPU.
* Output is constrained to the fixed intent set and parsed as JSON; a parse
  failure or a rule/model DISAGREEMENT makes the hybrid **abstain** (confidence
  drops below the router floor) so the system asks for clarification instead of
  guessing. A model crash never breaks routing — rules continue.

## Nodes / intents
| Intent | Node | Default risk |
|---|---|---|
| `supplier_followup`, `customer_followup` | `followup` | R3 (send) |
| `schedule_change` | `scheduling` | R3 (commit) |
| `customer_request` | `customer_request` | R2 (route to queue) |
| `unknown`, `out_of_scope` | — | clarify / reject |

## Safety spine
- Risk levels **R0–R3**; R3 (send/pay/delete/commit) requires explicit approval.
- Approvals are **bound to the exact payload hash** — a changed payload requires a new approval.
- Out-of-scope actions (pay/purchase/delete/legal) are **rejected**, even at critical urgency.
- Prompt-injection markers in the request text cannot alter the allow-list or policies.
- Every state transition is logged; success is only claimed when a node confirms it.
- All mocked integrations are labeled **SIMULATED** in the UI and API.

## Lifecycle
`received → classified → validated → awaiting_approval | routed → running → succeeded | failed | needs_clarification | rejected`


## Run it (async / queue-first)

The engine is **async-first**: every input (HTTP, CLI) is enqueued as a message
onto one bounded queue, and one long-running asyncio worker consumes it. The
FastAPI server binds the first free port in **4500-4900** and prints the URL.

```bat
REM server + dashboard + JSON API (binds first free port, prints it)
python -m invisible_secretary.server

REM 2-minute demo script (uses the canonical model)
python -m invisible_secretary.cli

REM model picker / listing
python -m invisible_secretary.cli --list-models      REM tabulate local models
python -m invisible_secretary.cli --pick             REM interactive picker
python -m invisible_secretary.cli --model qwen2.5-0.5b-instruct
python -m invisible_secretary.cli --no-model         REM rules only

REM tests (42): async bus + pipeline + server + hybrid policy + registry + real ONNX
python -m unittest discover -s invisible_secretary/tests -t . -v
```

On start the server prints e.g.
`Invisible Secretary listening on http://127.0.0.1:4500/ (all integrations SIMULATED; queue=256, workers=1)`
Two servers launched back-to-back pick **different** ports (4500, 4501, ...).
The chosen port is also recorded in `data/state.json` for local discovery.

### Configuration (env vars)

| Var | Default | Meaning |
|---|---|---|
| `IS_HOST` | `127.0.0.1` | bind host |
| `IS_PORT_RANGE` | `4500-4900` | scanned bind range (first free wins) |
| `IS_QUEUE_MAXSIZE` | `256` | bounded queue size (natural backpressure) |
| `IS_WORKERS` | `1` | consumer tasks (serialized processing) |
| `IS_MODEL` | canonical | model id/name/path to load |
| `IS_NO_MODEL` | unset | set to `1`/`true` for rules-only (no model load) |

```bat
set IS_MODEL=qwen2.5-0.5b-instruct
set IS_PORT_RANGE=4500-4510
python -m invisible_secretary.server
```

### HTTP API
`POST /api/route` (sync; `?mode=async` enqueues and returns `202 {"job_id": ...}`) ·
`GET /api/jobs/{job_id}` (poll async job) · `GET /api/activity` ·
`GET /api/nodes` · `POST /api/approvals/{id}/approve` ·
`POST /api/approvals/{id}/reject` · `GET /` (dashboard)

A saturated queue returns **503** (`retry`) on the async path.

Core is stdlib-only. The optional local-model path uses `onnxruntime` +
`transformers` (already present in this environment).
