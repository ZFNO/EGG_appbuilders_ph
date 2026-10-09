# Invisible Secretary — Agent Build Pack

## Purpose
Build a hackathon MVP of a local-first AI operations assistant for SME owners. The AI is a quiet decision layer, not a chatbot-first product.

## Product thesis
SME owners spend too much attention acting as the human coordination layer between employees, customers, suppliers, and business systems. The product turns incoming events and user requests into routed actions, while escalating ambiguous or consequential decisions.

## MVP boundary
Build a demonstrable vertical slice, not a full SME management suite.

### Must have
- A simple operations dashboard.
- A command input for user requests.
- A deterministic local router interface.
- Three capability nodes: follow-up, scheduling, customer request.
- An activity stream showing classification, routing, outcome, and failures.
- Approval/clarification states.
- Mock services are acceptable for the hackathon, provided the UI labels them as simulated.

### Must not have in the first version
- Autonomous arbitrary computer control.
- Unbounded multi-agent loops.
- Automatic sending, purchasing, payment, deletion, or other consequential actions without explicit authorization.
- A large CRM/ERP implementation.
- Cloud inference as a hidden fallback. Any fallback must be explicit and user-approved.

## Recommended implementation order
1. Define schemas and deterministic router.
2. Implement mocked node adapters.
3. Build dashboard and activity stream.
4. Add a model adapter for Qwen.
5. Add evaluation tests and failure handling.
6. Demonstrate one end-to-end scenario.

## Source of truth
The requirements in this pack take precedence over assumptions made by an implementation agent. If a requirement is ambiguous, choose the safest minimal behavior and document the assumption.
