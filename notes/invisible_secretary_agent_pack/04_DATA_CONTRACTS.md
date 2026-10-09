# Data Contracts

## Router decision schema
Use JSON Schema or equivalent runtime validation. Example:

```json
{
  "request_id": "req_demo_001",
  "intent": "supplier_followup",
  "node": "followup",
  "parameters": {
    "entity_type": "supplier",
    "entity_name": "Example Supplier",
    "topic": "delivery confirmation",
    "deadline": "2026-10-10"
  },
  "urgency": {
    "level": "high",
    "reason": "Delivery is expected today"
  },
  "confidence": 0.91,
  "risk_level": "R1",
  "requires_approval": true
}
```

This is illustrative data, not a live business record.

## Required validation
- `request_id`: non-empty string.
- `intent`: enum; unknown values are rejected.
- `node`: enum; must match the intent-to-node allow-list.
- `parameters`: object matching the selected intent schema.
- `urgency.level`: `low`, `normal`, `high`, or `critical`.
- `confidence`: number in [0, 1], treated as a heuristic.
- `risk_level`: enum `R0`–`R3`.
- `requires_approval`: boolean, but policy may force it to true.

## Node result schema
```json
{
  "request_id": "req_demo_001",
  "status": "needs_approval",
  "summary": "Draft supplier follow-up prepared.",
  "side_effect_performed": false,
  "approval_request": {
    "action": "send_message",
    "description": "Send the prepared message to the supplier"
  },
  "error": null
}
```

Allowed statuses: `succeeded`, `needs_approval`, `needs_clarification`, `failed`, `rejected`.

## Important rule
Never trust free-form model output as executable code, a URL, a shell command, or a permission. Parameters must be validated and passed to allow-listed functions.
