"""Invisible Secretary - data contracts (04_DATA_CONTRACTS.md).

Pure-stdlib validation of the router decision and node result contracts.
Nothing here executes actions or trusts free-form model output.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class ValidationError(ValueError):
    """Raised when a payload violates a data contract."""


class Intent(str, Enum):
    SUPPLIER_FOLLOWUP = "supplier_followup"
    CUSTOMER_FOLLOWUP = "customer_followup"
    SCHEDULE_CHANGE = "schedule_change"
    CUSTOMER_REQUEST = "customer_request"
    UNKNOWN = "unknown"
    OUT_OF_SCOPE = "out_of_scope"


class NodeName(str, Enum):
    FOLLOWUP = "followup"
    SCHEDULING = "scheduling"
    CUSTOMER_REQUEST = "customer_request"


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(str, Enum):
    R0 = "R0"  # classify / summarize only
    R1 = "R1"  # draft / recommendation, no external side effect
    R2 = "R2"  # reversible low-impact action, needs a configured permission
    R3 = "R3"  # consequential: send / pay / delete / commit -> explicit auth


class Status(str, Enum):
    SUCCEEDED = "succeeded"
    NEEDS_APPROVAL = "needs_approval"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"
    REJECTED = "rejected"


# Allow-listed intent -> node mapping. Single source of truth for dispatch.
INTENT_TO_NODE: dict[Intent, NodeName | None] = {
    Intent.SUPPLIER_FOLLOWUP: NodeName.FOLLOWUP,
    Intent.CUSTOMER_FOLLOWUP: NodeName.FOLLOWUP,
    Intent.SCHEDULE_CHANGE: NodeName.SCHEDULING,
    Intent.CUSTOMER_REQUEST: NodeName.CUSTOMER_REQUEST,
    Intent.UNKNOWN: None,
    Intent.OUT_OF_SCOPE: None,
}

ALLOWED_NODES = {n.value for n in NodeName}


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_decision(raw: dict) -> "RoutingDecision":
    """Validate a raw decision dict against the router decision schema."""
    if not isinstance(raw, dict):
        raise ValidationError("decision must be an object")

    request_id = raw.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValidationError("request_id: non-empty string required")

    try:
        intent = Intent(raw["intent"])
    except (KeyError, ValueError):
        raise ValidationError(f"intent: unknown value {raw.get('intent')!r}")

    node_raw = raw.get("node")
    if node_raw is not None and node_raw not in ALLOWED_NODES:
        raise ValidationError(f"node: not allow-listed: {node_raw!r}")
    expected_node = INTENT_TO_NODE[intent]
    if node_raw is not None and expected_node is not None and node_raw != expected_node.value:
        raise ValidationError(f"node: {node_raw!r} does not match allow-list for {intent.value}")

    params = raw.get("parameters", {})
    if not isinstance(params, dict):
        raise ValidationError("parameters: object required")

    urgency = raw.get("urgency", {})
    if not isinstance(urgency, dict):
        raise ValidationError("urgency: object required")
    try:
        u_level = Urgency(urgency.get("level", "normal"))
    except ValueError:
        raise ValidationError(f"urgency.level: invalid {urgency.get('level')!r}")

    conf = raw.get("confidence", 0.0)
    if not _is_num(conf) or not (0.0 <= float(conf) <= 1.0):
        raise ValidationError("confidence: number in [0,1] required")

    try:
        risk = RiskLevel(raw.get("risk_level", "R1"))
    except ValueError:
        raise ValidationError(f"risk_level: invalid {raw.get('risk_level')!r}")

    req_appr = raw.get("requires_approval", False)
    if not isinstance(req_appr, bool):
        raise ValidationError("requires_approval: boolean required")

    return RoutingDecision(
        request_id=request_id,
        intent=intent,
        node=NodeName(node_raw) if node_raw else None,
        parameters=params,
        urgency_level=u_level,
        urgency_reason=str(urgency.get("reason", "")),
        confidence=float(conf),
        risk_level=risk,
        requires_approval=req_appr,
    )


def validate_result(raw: dict) -> "NodeResult":
    if not isinstance(raw, dict):
        raise ValidationError("result must be an object")
    if not isinstance(raw.get("request_id"), str) or not raw["request_id"]:
        raise ValidationError("result.request_id: non-empty string required")
    try:
        status = Status(raw["status"])
    except (KeyError, ValueError):
        raise ValidationError(f"result.status: invalid {raw.get('status')!r}")
    side_effect = raw.get("side_effect_performed", False)
    if not isinstance(side_effect, bool):
        raise ValidationError("result.side_effect_performed: boolean required")
    return NodeResult(
        request_id=raw["request_id"],
        status=status,
        summary=str(raw.get("summary", "")),
        side_effect_performed=side_effect,
        approval_request=raw.get("approval_request"),
        error=raw.get("error"),
        simulated=bool(raw.get("simulated", True)),
    )


@dataclass
class RoutingDecision:
    request_id: str
    intent: Intent
    node: NodeName | None
    parameters: dict
    urgency_level: Urgency = Urgency.NORMAL
    urgency_reason: str = ""
    confidence: float = 0.0
    risk_level: RiskLevel = RiskLevel.R1
    requires_approval: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["intent"] = self.intent.value
        d["node"] = self.node.value if self.node else None
        d["urgency_level"] = self.urgency_level.value
        d["risk_level"] = self.risk_level.value
        return d


@dataclass
class NodeResult:
    request_id: str
    status: Status
    summary: str = ""
    side_effect_performed: bool = False
    approval_request: dict | None = None
    error: str | None = None
    simulated: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d
