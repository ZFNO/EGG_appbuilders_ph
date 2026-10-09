"""Invisible Secretary - deterministic router (03_ROUTER_AND_NODE_ARCHITECTURE.md).

The router is the policy engine. It validates schema, rejects unknown
intents/nodes, computes urgency from explicit rules (never from model
confidence), applies risk/authorization policy, and dispatches ONLY to
allow-listed nodes. High urgency never bypasses authorization.
"""
from __future__ import annotations

from . import schemas
from .schemas import (Intent, NodeName, RiskLevel, RoutingDecision, Urgency,
                      ValidationError, INTENT_TO_NODE, ALLOWED_NODES)

CONFIDENCE_FLOOR = 0.80   # below this -> clarify, never guess

# Required parameters per intent (validated before dispatch).
REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "supplier_followup": ("entity_type",),
    "customer_followup": ("entity_type",),
    "schedule_change": ("topic",),
    "customer_request": ("topic",),
}

# Consequential actions by intent -> risk level when the action is committed.
_ACTION_RISK: dict[str, RiskLevel] = {
    "supplier_followup": RiskLevel.R3,   # send external message
    "customer_followup": RiskLevel.R3,   # send external message
    "schedule_change": RiskLevel.R3,     # commit a schedule change
    "customer_request": RiskLevel.R2,    # route to a queue (reversible, low impact)
}

_URGENT = ("today", "urgent", "asap", "immediately", "as soon as possible")


class Router:
    def __init__(self, model, *, confidence_floor: float = CONFIDENCE_FLOOR):
        self.model = model
        self.confidence_floor = confidence_floor
        self.audit: list[dict] = []

    # -- policy helpers -------------------------------------------------
    @staticmethod
    def _urgency(text: str, hint: str) -> tuple[Urgency, str]:
        t = (text or "").lower()
        if any(k in t for k in ("immediately", "asap", "as soon as possible")):
            return Urgency.CRITICAL, "explicit immediacy signal"
        if any(k in t for k in ("today", "urgent", "overdue", "late")):
            return Urgency.HIGH, "same-day / urgent signal"
        if hint == "high":
            return Urgency.HIGH, "model urgency hint (rule-confirmed only)"
        return Urgency.NORMAL, "no urgency signal"

    def route(self, request_id: str, text: str) -> RoutingDecision:
        model_out = self.model.classify(text)
        intent = model_out.get("intent", "unknown")
        params = dict(model_out.get("parameters", {}))
        confidence = float(model_out.get("confidence", 0.0))

        if intent not in {i.value for i in Intent}:
            intent = "unknown"

        node = INTENT_TO_NODE[Intent(intent)]
        level, reason = self._urgency(text, model_out.get("urgency_hint", "normal"))
        risk = _ACTION_RISK.get(intent, RiskLevel.R1)

        decision = RoutingDecision(
            request_id=request_id,
            intent=Intent(intent),
            node=node,
            parameters=params,
            urgency_level=level,
            urgency_reason=reason,
            confidence=confidence,
            risk_level=risk,
            requires_approval=risk in (RiskLevel.R2, RiskLevel.R3),
        )

        # --- policy gate (independent of model confidence) -------------
        blocked: list[str] = []
        if intent == "out_of_scope":
            decision.node = None
            blocked.append("out_of_scope_action")
        elif intent == "unknown":
            decision.node = None

        if decision.node is not None:
            if decision.node.value not in ALLOWED_NODES:
                decision.node = None
                blocked.append("unknown_node_rejected")
            missing = [p for p in REQUIRED_PARAMS.get(intent, ()) if p not in params]
            if missing:
                blocked.append("missing_params:" + ",".join(missing))
            if confidence < self.confidence_floor:
                blocked.append("low_confidence")

        # Re-validate the object against the contract before it leaves.
        try:
            decision = schemas.validate_decision(decision.to_dict())
        except ValidationError as exc:
            raise ValidationError(f"router produced invalid decision: {exc}") from exc

        self.audit.append({
            "request_id": request_id,
            "transition": "classified",
            "intent": decision.intent.value,
            "node": decision.node.value if decision.node else None,
            "confidence": decision.confidence,
            "urgency": decision.urgency_level.value,
            "risk_level": decision.risk_level.value,
            "requires_approval": decision.requires_approval,
            "blocked": blocked,
            "model": getattr(self.model, "name", "unknown"),
        })
        decision._blocked = blocked  # consumed by the engine
        return decision
