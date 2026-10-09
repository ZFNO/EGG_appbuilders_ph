"""Invisible Secretary - capability nodes (mock adapters).

Each node validates its own inputs, enforces business rules, executes a MOCK
integration, and returns a typed result. Mocked integrations are always labeled
`simulated=True`. A node never sends, pays, deletes, or commits on its own:
consequential actions come back as `needs_approval` bound to the exact payload.
"""
from __future__ import annotations

from .schemas import NodeResult, RoutingDecision, Status

# Pre-authorized, reversible, low-impact actions the owner has explicitly
# configured. Anything consequential (send/pay/delete/commit) is NOT here and
# therefore requires fresh approval.
DEFAULT_POLICIES: set[str] = {"route_to_queue"}


class BaseNode:
    name = "base"
    description = ""
    consequential_action: str | None = None  # action name needing approval

    def __init__(self, *, healthy: bool = True):
        self.healthy = healthy

    def health(self) -> dict:
        return {"node": self.name, "health": "ok" if self.healthy else "degraded",
                "simulated": True}

    def handle(self, decision: RoutingDecision, policies: set[str] | None = None) -> NodeResult:
        policies = DEFAULT_POLICIES if policies is None else policies
        if not self.healthy:
            return NodeResult(decision.request_id, Status.FAILED,
                              summary=f"{self.name} node unavailable",
                              error="node_unhealthy")
        return self._run(decision, policies)

    def _run(self, decision: RoutingDecision, policies: set[str]) -> NodeResult:  # pragma: no cover
        raise NotImplementedError


class FollowupNode(BaseNode):
    name = "followup"
    description = "Prepare and (on approval) send a follow-up message."
    consequential_action = "send_message"

    def _run(self, decision, policies):
        p = decision.parameters
        if not p.get("entity_type"):
            return NodeResult(decision.request_id, Status.NEEDS_CLARIFICATION,
                              summary="Which party should be followed up?")
        party = p.get("entity_name", f"the {p['entity_type']}")
        topic = p.get("topic", "the open item")
        draft = (f"Hi {party}, quick follow-up on {topic}."
                 + (f" Needed by {p['deadline']}." if p.get("deadline") else ""))
        if self.consequential_action in policies:
            # Owner pre-authorized a narrow send policy (not the default).
            return NodeResult(decision.request_id, Status.SUCCEEDED,
                              summary=f"[SIMULATED] Sent follow-up to {party}.",
                              side_effect_performed=True, simulated=True)
        return NodeResult(
            decision.request_id, Status.NEEDS_APPROVAL,
            summary="Draft follow-up prepared; awaiting approval.",
            side_effect_performed=False,
            approval_request={
                "action": self.consequential_action,
                "target": party,
                "description": f"Send the prepared message to {party}",
                "payload": {"message": draft, "topic": topic},
            },
            simulated=True,
        )


class SchedulingNode(BaseNode):
    name = "scheduling"
    description = "Propose and (on approval) commit a schedule change."
    consequential_action = "commit_schedule_change"

    def _run(self, decision, policies):
        p = decision.parameters
        if not p.get("topic"):
            return NodeResult(decision.request_id, Status.NEEDS_CLARIFICATION,
                              summary="What schedule change should I propose?")
        proposal = f"{p['topic']}" + (f" by {p['deadline']}" if p.get("deadline") else "")
        if self.consequential_action in policies:
            return NodeResult(decision.request_id, Status.SUCCEEDED,
                              summary=f"[SIMULATED] Committed schedule change: {proposal}.",
                              side_effect_performed=True, simulated=True)
        return NodeResult(
            decision.request_id, Status.NEEDS_APPROVAL,
            summary="Schedule change proposed; awaiting approval.",
            side_effect_performed=False,
            approval_request={
                "action": self.consequential_action,
                "target": "calendar",
                "description": f"Commit schedule change: {proposal}",
                "payload": {"change": proposal},
            },
            simulated=True,
        )


class CustomerRequestNode(BaseNode):
    name = "customer_request"
    description = "Triage a customer request and route it to a queue."
    consequential_action = "route_to_queue"

    def _run(self, decision, policies):
        p = decision.parameters
        if not p.get("topic"):
            return NodeResult(decision.request_id, Status.NEEDS_CLARIFICATION,
                              summary="What is the customer request?")
        queue = "support.tier1"
        if self.consequential_action in policies:  # reversible, pre-authorized
            return NodeResult(decision.request_id, Status.SUCCEEDED,
                              summary=f"[SIMULATED] Routed customer request to {queue}.",
                              side_effect_performed=True, simulated=True)
        return NodeResult(
            decision.request_id, Status.NEEDS_APPROVAL,
            summary="Customer request triaged; awaiting approval to route.",
            approval_request={
                "action": self.consequential_action,
                "target": queue,
                "description": f"Route the request to {queue}",
                "payload": {"topic": p["topic"], "queue": queue},
            },
            simulated=True,
        )


def default_nodes() -> dict[str, BaseNode]:
    return {n.name: n for n in (FollowupNode(), SchedulingNode(), CustomerRequestNode())}
