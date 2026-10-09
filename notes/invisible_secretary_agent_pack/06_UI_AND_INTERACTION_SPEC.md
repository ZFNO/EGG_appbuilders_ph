# UI and Interaction Specification

## Main screen
1. Header with product name and local-runtime status.
2. Summary cards: handled actions, awaiting approval, failures.
3. “Needs your attention” queue.
4. Recent activity stream.
5. Available services/nodes and health state.
6. Command input for natural-language requests.

## Activity row
Show:
- received request/event
- predicted intent
- selected node
- urgency and explanation
- approval status
- action result
- timestamp
- failure/clarification details when applicable

## Approval card
Show the exact proposed action, target, relevant parameters, and consequence. Offer Approve, Edit, and Reject. Do not make “Approve” appear to have executed until the backend confirms it.

## Local-first indicator
Show whether inference is local. If any remote service is used, disclose it at the point of use.

## Demo data
Use visibly synthetic names and events. Never imply a mock action actually sent a message, booked a delivery, or changed a real calendar.
