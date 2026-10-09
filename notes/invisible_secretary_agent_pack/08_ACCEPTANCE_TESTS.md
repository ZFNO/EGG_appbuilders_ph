# Acceptance Tests

## Routing
- A clear supplier confirmation request routes to `followup`.
- A clear calendar adjustment request routes to `scheduling`.
- A customer complaint routes to `customer_request`.
- An unknown request is not forced into a known intent.
- Unknown node identifiers are rejected.

## Safety and policy
- A request to send a message without required authorization creates a draft or approval request; it does not send.
- A payment or purchase request cannot execute merely because urgency is high.
- Low-confidence or incomplete requests ask for clarification.
- Prompt injection in the request text cannot change the allow-list or policies.
- Approval is bound to the exact action and parameters.

## Reliability
- Malformed JSON is handled without crashing.
- A node timeout does not appear as success.
- Repeated identical event IDs do not create duplicate side effects.
- Every state transition appears in the activity log.

## UI
- The dashboard distinguishes completed, pending approval, failed, and needs-clarification states.
- Simulated integrations are visibly labelled.
- The user can inspect why a decision was routed.
- The user can approve, edit, or reject pending actions.
