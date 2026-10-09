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

## Run it
```bat
REM dashboard + JSON API (http://127.0.0.1:8765)  -- uses the local ONNX model
python -m invisible_secretary.api

REM 2-minute demo script (uses the canonical model)
python -m invisible_secretary.cli

REM model picker / listing
python -m invisible_secretary.cli --list-models      REM tabulate local models
python -m invisible_secretary.cli --pick             REM interactive picker
python -m invisible_secretary.cli --model qwen2.5-0.5b-instruct
python -m invisible_secretary.cli --no-model         REM rules only

REM API model override (default = canonical)
set IS_MODEL=qwen2.5-0.5b-instruct
python -m invisible_secretary.api

REM tests (29): rules core + API + hybrid policy + registry + real ONNX model
python -m unittest discover -s invisible_secretary/tests -t . -v

REM rules-only run (no model load)
python -c "from invisible_secretary import Engine; from invisible_secretary.factory import default_adapter; Engine(default_adapter(use_model=False))"
```

## API
`POST /api/route` · `GET /api/activity` · `GET /api/nodes` ·
`POST /api/approvals/{id}/approve` · `POST /api/approvals/{id}/reject`

Core is stdlib-only. The optional local-model path uses `onnxruntime` +
`transformers` (already present in this environment).
