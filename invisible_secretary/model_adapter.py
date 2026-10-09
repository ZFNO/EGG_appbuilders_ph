"""Invisible Secretary - local model adapter (05_MODEL_SELECTION_AND_EVALUATION.md).

The model performs BOUNDED intent classification + parameter extraction only.
It never executes tools, never grants permissions, never decides authorization.

Ordering (safety-first): a deterministic rule classifier is the PRIMARY path.
A local small model (Qwen2.5) ENHANCES it. If the two DISAGREE the hybrid
ABSTAINS (confidence below the router floor) so the system asks for
clarification rather than guessing. There is never a hidden cloud fallback.
"""
from __future__ import annotations

import re
from typing import Protocol

# A rule is (intent, [keyword groups]). The intent fires when the most groups
# match; score = number of distinct groups matched (0..2 -> confidence band).
_RULES: list[tuple[str, list[list[str]]]] = [
    ("out_of_scope", [["pay", "payment", "purchase", "buy", "transfer", "wire",
                       "delete", "erase", "refund money", "legal", "lawsuit",
                       "hire", "fire", "terminate employee"]]),
    ("schedule_change", [["schedule", "calendar", "appointment", "meeting",
                          "reschedule", "rebook", "slot", "book a"],
                         ["change", "move", "shift", "cancel", "adjust", "propose",
                          "today", "tomorrow", "thursday", "friday"]]),
    ("customer_followup", [["customer", "client", "buyer", "patron"],
                           ["follow up", "follow-up", "chase", "remind", "confirm",
                            "reply", "get back"]]),
    ("supplier_followup", [["supplier", "vendor", "distributor", "delivery",
                            "shipment", "order #", "purchase order"],
                           ["follow up", "follow-up", "confirm", "chase", "remind",
                            "has not", "not confirmed", "expected today", "deliver"]]),
    ("customer_request", [["customer", "client", "buyer", "patron", "complaint",
                           "ticket", "support"],
                          ["request", "complain", "issue", "broken", "problem",
                           "bug", "refund", "help", "asks"]]),
]

# Adversarial instruction markers -> never allowed to change policy.
_INJECTION = re.compile(
    r"(ignore (all|previous|the) (instructions|rules|polic)|"
    r"you are now|system prompt|allow-?list|bypass (auth|policy)|"
    r"disregard (all|the) (rules|policy))", re.I)

_NAME = re.compile(r"(?:with|to|ask|from|for)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*)*)")
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


class ModelAdapter(Protocol):
    name: str

    def classify(self, text: str) -> dict:
        """Return {intent, parameters, confidence, urgency_hint, notes}."""
        ...


class RuleClassifier:
    """Deterministic primary classifier. Fast, offline, no weights required."""

    name = "rule-deterministic"

    def classify(self, text: str) -> dict:
        t = (text or "").lower()
        notes: list[str] = []

        if _INJECTION.search(text or ""):
            notes.append("adversarial_instruction_detected_ignored")

        best_intent, best_score = "unknown", 0
        for intent, groups in _RULES:
            hits = sum(1 for g in groups if any(k in t for k in g))
            if hits > best_score:
                best_intent, best_score = intent, hits

        # A single weak signal is not enough: do not force a known intent.
        if best_score < 2 and best_intent != "out_of_scope":
            best_intent = "unknown"

        # confidence is a heuristic, not a calibrated probability.
        confidence = {0: 0.30, 1: 0.62, 2: 0.88}.get(best_score, 0.30)

        params: dict = {}
        m = _NAME.search(text or "")
        if m:
            params["entity_name"] = m.group(1).strip()
        d = _DATE.search(text or "")
        if d:
            params["deadline"] = d.group(1)

        if best_intent in ("supplier_followup", "customer_followup"):
            params.setdefault("entity_type",
                              "supplier" if best_intent == "supplier_followup" else "customer")
            if "confirm" in t and "deliver" in t:
                params.setdefault("topic", "delivery confirmation")
            elif "follow" in t:
                params.setdefault("topic", "follow-up")
            else:
                params.setdefault("topic", "open item")
        elif best_intent == "schedule_change":
            params.setdefault("entity_type", "schedule")
            params.setdefault("topic", "schedule change")
        elif best_intent == "customer_request":
            params.setdefault("topic", "customer request")

        return {
            "intent": best_intent,
            "parameters": params,
            "confidence": confidence,
            "urgency_hint": "high" if ("today" in t or "urgent" in t) else "normal",
            "notes": notes,
        }


class QwenLocalAdapter:
    """Local small-model adapter behind a stable interface.

    Delegates to the real on-device ONNX runtime when available
    (see ``invisible_secretary.local_qwen``). Deliberately inert otherwise:
    classification is an ENHANCEMENT to the rule path, and there is NO cloud
    fallback.
    """

    name = "qwen-local"

    def __init__(self, model_path: str | None = None, runtime: str = "onnxruntime"):
        self.model_path = model_path
        self.runtime = runtime
        self._impl = None

    def _backend(self):
        if self._impl is None and self.model_path:
            from .local_qwen import QwenOnnxAdapter
            self._impl = QwenOnnxAdapter(self.model_path)
        return self._impl

    def available(self) -> bool:
        return bool(self.model_path)

    def classify(self, text: str) -> dict:
        backend = self._backend()
        if backend is None:
            raise RuntimeError("local model not provisioned; no cloud fallback permitted")
        return backend.classify(text)


class HybridAdapter:
    """Rules primary; local model enhances. Disagreement -> abstain.

    Agreement boosts confidence; a model/rule conflict drives confidence below
    the router floor so the system abstains (clarifies) instead of guessing.
    """

    ABSTAIN = 0.10  # below the router's confidence floor

    def __init__(self, model: ModelAdapter | None = None, *, use_model: bool = True):
        self.rules = RuleClassifier()
        self.model = model
        self.use_model = use_model

    @property
    def name(self) -> str:
        if self._model_ready():
            return f"{self.rules.name}+{self.model.name}"
        return self.rules.name

    def _model_ready(self) -> bool:
        return bool(self.use_model and self.model and
                    getattr(self.model, "available", lambda: False)())

    def classify(self, text: str) -> dict:
        out = self.rules.classify(text)
        out["model_used"] = self.rules.name
        if not self._model_ready():
            return out

        try:
            m = self.model.classify(text)
        except Exception as exc:  # local runtime must never break routing
            out["model_error"] = f"{type(exc).__name__}: {exc}"
            return out

        out["model_used"] = f"{self.rules.name}+{self.model.name}"
        out["model_intent"] = m.get("intent")
        out["rules_intent"] = out["intent"]

        # Bound rule extraction: the model may fill parameters the rules missed,
        # but never overrides a rule-derived value.
        for k, v in (m.get("parameters") or {}).items():
            out["parameters"].setdefault(k, v)

        if m.get("parse_error") or not m.get("intent"):
            out["conflict"] = "model_parse_error"
            out["confidence"] = min(out["confidence"], self.ABSTAIN)
        elif m["intent"] != out["intent"]:
            out["conflict"] = f"rules={out['intent']} model={m['intent']}"
            out["confidence"] = min(out["confidence"], self.ABSTAIN)
        else:
            out["confidence"] = min(0.98, out["confidence"] + 0.08)
        return out
