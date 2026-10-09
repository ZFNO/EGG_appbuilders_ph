# API and Implementation Plan

## Suggested internal interfaces
- `POST /api/route`: accepts a user request or event and returns a validated routing decision plus lifecycle status.
- `GET /api/activity`: returns recent event records.
- `GET /api/nodes`: returns allow-listed nodes and their health.
- `POST /api/approvals/{id}/approve`: authorizes the exact pending action.
- `POST /api/approvals/{id}/reject`: rejects the pending action.

These are suggested interfaces; adapt to the chosen framework while preserving semantics.

## Example route request
```json
{
  "request_id": "req_demo_002",
  "source": "command",
  "text": "Ask the supplier to confirm today's delivery"
}
```

## Implementation sequence
1. Create types/enums and schema validation.
2. Implement deterministic intent-to-node mapping.
3. Implement mock node adapters.
4. Implement event state machine and audit log.
5. Build the dashboard against mock API data.
6. Add Qwen model adapter behind a stable interface.
7. Add confidence/abstention and policy tests.
8. Run the evaluation set and profile target hardware.
9. Prepare a 2-minute demo script.

## Error handling
- Invalid model output: reject and retry at most once with a constrained prompt; otherwise escalate.
- Timeout: mark failed; never report success.
- Duplicate event: use idempotency key to avoid duplicate actions.
- Missing parameter: ask a focused clarification.
- Unknown node: reject safely and log.
- Approval endpoint: bind approval to the exact action payload; if the payload changes, require new approval.
