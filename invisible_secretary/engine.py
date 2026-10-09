"""Invisible Secretary - event state machine, audit log, approvals, idempotency.

Lifecycle: received -> classified -> validated -> awaiting_approval | routed
           -> running -> succeeded | failed | needs_clarification | rejected.
Every transition is logged. Success is never claimed until a node confirms it.
Approvals are bound to the exact action payload; a changed payload invalidates
the approval and requires a new one.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from .nodes import BaseNode, DEFAULT_POLICIES, default_nodes
from .router import Router
from .schemas import NodeResult, RoutingDecision, Status


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class Event:
    request_id: str
    text: str
    created: float = field(default_factory=time.time)
    state: str = "received"
    decision: RoutingDecision | None = None
    result: NodeResult | None = None
    history: list[dict] = field(default_factory=list)
    pending_approval: dict | None = None

    def log(self, transition: str, **extra):
        self.history.append({"ts": round(time.time(), 3), "state": transition, **extra})

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "text": self.text,
            "state": self.state,
            "decision": self.decision.to_dict() if self.decision else None,
            "result": self.result.to_dict() if self.result else None,
            "pending_approval": self.pending_approval,
            "history": self.history,
        }


class Engine:
    def __init__(self, model, *, nodes: dict[str, BaseNode] | None = None,
                 policies: set[str] | None = None):
        self.router = Router(model)
        self.nodes = nodes or default_nodes()
        self.policies = set(DEFAULT_POLICIES if policies is None else policies)
        self.events: dict[str, Event] = {}
        self._approvals: dict[str, str] = {}  # approval_id -> request_id

    # -- public API -----------------------------------------------------
    def process(self, request_id: str, text: str) -> Event:
        if request_id in self.events:
            ev = self.events[request_id]
            ev.log("duplicate_ignored", note="idempotency key already seen")
            return ev  # idempotent: no duplicate side effects

        ev = Event(request_id=request_id, text=text)
        self.events[request_id] = ev
        ev.log("received")

        decision = self.router.route(request_id, text)
        ev.decision = decision
        ev.log("classified", intent=decision.intent.value,
               node=decision.node.value if decision.node else None)

        blocked = getattr(decision, "_blocked", [])

        if decision.intent.value == "out_of_scope":
            ev.state = "rejected"
            ev.log("rejected", reason="out_of_scope_action_blocked")
            return ev
        if decision.node is None or "low_confidence" in blocked or \
                any(b.startswith("missing_params") for b in blocked):
            ev.state = "needs_clarification"
            ev.result = NodeResult(request_id, Status.NEEDS_CLARIFICATION,
                                   summary=self._clarify_prompt(decision))
            ev.log("needs_clarification", blocked=blocked)
            return ev

        ev.log("validated")

        if decision.node.value not in self.nodes:
            ev.state = "failed"
            ev.log("failed", reason="unknown_node_rejected")
            return ev

        ev.state = "routed"
        ev.log("routed", node=decision.node.value)
        return self._run_node(ev)

    def approve(self, approval_id: str, payload: dict | None = None) -> Event:
        ev = self._event_for_approval(approval_id)
        pending = ev.pending_approval
        if pending is None:
            raise KeyError("no pending approval")
        if payload is not None and _payload_hash(payload) != pending["payload_hash"]:
            # payload changed -> old approval does not carry over
            ev.log("approval_invalidated", reason="payload_changed")
            raise ValueError("payload changed; a new approval is required")
        ev.log("approved", approval_id=approval_id)
        ev.pending_approval = None
        self._approvals.pop(approval_id, None)
        # re-run the node WITH the specific action authorized
        return self._run_node(ev, extra_policy=pending["action"])

    def reject(self, approval_id: str) -> Event:
        ev = self._event_for_approval(approval_id)
        ev.pending_approval = None
        self._approvals.pop(approval_id, None)
        ev.state = "rejected"
        ev.log("rejected", approval_id=approval_id)
        return ev

    # -- internals ------------------------------------------------------
    def _event_for_approval(self, approval_id: str) -> Event:
        rid = self._approvals.get(approval_id)
        if rid is None or rid not in self.events:
            raise KeyError(f"unknown approval {approval_id!r}")
        return self.events[rid]

    def _run_node(self, ev: Event, extra_policy: str | None = None) -> Event:
        node = self.nodes[ev.decision.node.value]
        policies = set(self.policies)
        if extra_policy:
            policies.add(extra_policy)
        ev.state = "running"
        ev.log("running", node=node.name)
        result = node.handle(ev.decision, policies)
        ev.result = result

        if result.status == Status.NEEDS_APPROVAL:
            appr = result.approval_request or {}
            approval_id = f"apr_{ev.request_id}_{_payload_hash(appr.get('payload', {}))}"
            pending = {
                "approval_id": approval_id,
                **appr,
                "payload_hash": _payload_hash(appr.get("payload", {})),
                "simulated": True,
            }
            ev.pending_approval = pending
            self._approvals[approval_id] = ev.request_id
            ev.state = "awaiting_approval"
            ev.log("awaiting_approval", approval_id=approval_id, action=appr.get("action"))
        elif result.status == Status.SUCCEEDED:
            ev.state = "succeeded"
            ev.log("succeeded", side_effect=result.side_effect_performed)
        elif result.status == Status.NEEDS_CLARIFICATION:
            ev.state = "needs_clarification"
            ev.log("needs_clarification", summary=result.summary)
        else:
            ev.state = "failed"
            ev.log("failed", error=result.error)
        return ev

    @staticmethod
    def _clarify_prompt(decision: RoutingDecision) -> str:
        if decision.node is None:
            return "I couldn't map that to a supported capability. Which of these did you mean?"
        return "I need a bit more detail before I route this. Could you clarify?"
