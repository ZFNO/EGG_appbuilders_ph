# Router and Node Architecture

## High-level flow
Input/event → normalization → local intent model → schema validation → policy gate → node adapter → result verification → activity log → UI update.

## Separation of responsibilities
### Local model
- Classify intent from a fixed list.
- Extract only schema-defined parameters.
- Return a structured object.
- It does not execute tools, grant permissions, or decide that authorization can be bypassed.

### Deterministic router
- Validate JSON against the schema.
- Reject unknown intents and node identifiers.
- Apply authorization and risk policies.
- Apply urgency rules independently of model confidence.
- Dispatch only to allow-listed nodes.
- Handle retries, timeouts, and idempotency.
- Log all decisions and outcomes.

### Node adapter
- Validate required parameters.
- Enforce service-specific business rules.
- Execute a mock or real integration.
- Return a typed success, needs-approval, clarification, or failure result.
- Never assume the model's output is correct.

## Initial nodes
1. `followup`
2. `scheduling`
3. `customer_request`

## Suggested intent set
- `supplier_followup`
- `customer_followup`
- `schedule_change`
- `customer_request`
- `unknown`
- `out_of_scope`

## Confidence and urgency
- Treat model confidence as a heuristic, not a calibrated probability.
- Calibrate thresholds against a labelled test set.
- Urgency is computed from explicit signals and rules; do not let a model's urgency score override permissions.
- Low confidence, conflicting intent, missing required parameters, or out-of-scope requests should result in clarification or escalation.
- High urgency must never bypass safety or authorization.

## Action risk levels
- `R0`: classify or summarize only.
- `R1`: prepare a draft or recommendation; no external side effect.
- `R2`: reversible, low-impact action; require a configured permission.
- `R3`: consequential action such as sending external messages, making purchases, payments, deleting data, or committing a schedule. Require explicit authorization unless the owner has separately configured a narrowly scoped policy.

## Event lifecycle
`received` → `classified` → `validated` → `awaiting_approval` OR `routed` → `running` → `succeeded` / `failed` / `needs_clarification`.

Each transition must be logged. Avoid claiming success until the node confirms it.
