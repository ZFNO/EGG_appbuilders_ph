# Invisible Secretary — System Diagram

Source-accurate as of `invisible_secretary/` (`schemas.py`, `model_adapter.py`,
`router.py`, `nodes.py`, `engine.py`, `bus.py`, `pipeline.py`).

## End-to-end flow

```
════════════════════════════════════════════════════════════════════════════════
 INVISIBLE SECRETARY — END-TO-END
════════════════════════════════════════════════════════════════════════════════

 INPUT ENTITIES (sources)                      all publish ONE `Message` onto ONE Bus
 ┌──────────────────────────────────┐
 │ HTTP  POST /api/route            │  text, request_id, source="http"
 │ CLI   cli.py                     │  text,                     source="cli"
 │ watchers (future)                │  ...                       source="watcher"
 └───────────────┬──────────────────┘
                 ▼
 ┌──────────────────────────────────┐        ┌───────────────────────────────┐
 │ Bus (bus.py)                     │───►    │ bounded asyncio.Queue         │
 │ publish(Message)                 │ (back- │ maxsize=IS_QUEUE_MAXSIZE(256) │
 │ Message{kind,payload,id,source}  │  press)│ worker(s)=IS_WORKERS(1)       │
 └──────────────────────────────────┘        └───────────────┬───────────────┘
                                                             ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ PIPELINE (pipeline.py) — single worker, ordered stages, fail-soft         │
 └───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ ENGINE (engine.py) — event state machine + idempotency(request_id)        │
 │                                                                           │
 │  received → classified → validated → routed → running                     │
 │                    │                     └──────────────────► succeeded    │
 │                    │                                          failed       │
 │                    ├─ R2/R3 ────────────────────────────► awaiting_approval
 │                    └─ low conf / missing / unknown ──────► needs_clarification
 │        out_of_scope ──────────────────────────────────────► rejected       │
 │                                                                           │
 │  APPROVAL: bound to sha256(payload)[:16]; changed payload ⇒ new approval   │
 └───────────────┬───────────────────────────────────────────────────────────┘
                 │ step 1: classify            step 2: policy
                 ▼                                    ▼
 ┌──────────────────────────────────┐   ┌──────────────────────────────────┐
 │ MODEL (model_adapter.py)         │   │ ROUTER (router.py)               │
 │ HybridAdapter                    │   │ 1 intent ∈ Intent enum           │
 │  ├─ RuleClassifier  (PRIMARY)    │   │ 2 node = INTENT_TO_NODE[intent]  │
 │  └─ QwenLocalAdapter(ENHANCE)    │   │ 3 urgency ← RULES only           │
 │                                  │   │   (never model confidence)       │
 │  output: {intent, parameters,    │   │ 4 risk  = _ACTION_RISK[intent]   │
 │           confidence,            │   │ 5 requires_approval = R2|R3      │
 │           urgency_hint, notes}   │   │ 6 schema validate_decision       │
 │                                  │   │ 7 policy gate (blocked[])        │
 │  rules vs model DISAGREE ⇒       │   │   out_of_scope/unknown → node∅   │
 │  ABSTAIN (conf < 0.80 floor) ⇒   │   │   missing_params / low_conf      │
 │  ask, never guess. No cloud.     │   │   high urgency ≠ bypass auth     │
 └──────────────────────────────────┘   └───────────────┬──────────────────┘
                                                         ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ NODES (nodes.py) — capability adapters, ALL SIMULATED (simulated=True)    │
 │  followup         → send_message           (R3, needs approval)           │
 │  scheduling       → commit_schedule_change (R3, needs approval)           │
 │  customer_request → route_to_queue         (R2, pre-authorized DEFAULT)   │
 └───────────────────────────────────────────────────────────────────────────┘
```

## Input entity types

What the classifier extracts, per intent:

```
 intent               entity_type   other bounded params        risk   node
 ───────────────────  ───────────   ─────────────────────────   ────   ───────────────
 supplier_followup    "supplier"    entity_name, topic, deadline R3    followup
 customer_followup    "customer"    entity_name, topic, deadline R3    followup
 schedule_change      "schedule"    topic, deadline             R3    scheduling
 customer_request     "customer"    topic                       R2    customer_request
 unknown              —             (none)                       R1    ∅ → clarify
 out_of_scope         —             (pay/purchase/delete/legal/  —     ∅ → rejected
                                     hire/fire)  ← hard-blocked

 generic entity slots (any intent):
   entity_name  · regex  (with|to|ask|from|for) <Capitalized…>
   deadline     · regex  YYYY-MM-DD
   topic        · short phrase (rule default or model)
 confidence bands: 2 groups matched = 0.88 · 1 = 0.62 · 0 = 0.30   (floor 0.80)
 injection guard: "ignore previous…/you are now/system prompt/bypass" → ignored, noted
```

## Invariants

- Rules are **primary**; the on-device Qwen model only **enhances**.
- On disagreement the hybrid **abstains** (confidence below the router floor); it never guesses.
- **Urgency and risk come from rules, never from model confidence.**
- High urgency never bypasses authorization.
- Nodes are allow-listed; everything consequential pauses for a **payload-hash-bound approval**.
- All integrations are **SIMULATED** and labeled as such.
