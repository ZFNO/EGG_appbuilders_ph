"""Invisible Secretary - local-first AI operations assistant (MVP).

A quiet decision layer, not a chat-first chatbot. Three layers, never blurred:
local model (bounded classification) -> deterministic router (policy) -> node
adapters (mocked, labeled as simulated).
"""
from .engine import Engine, Event
from .factory import default_adapter
from .model_adapter import HybridAdapter, QwenLocalAdapter, RuleClassifier
from .nodes import default_nodes
from .router import Router
from .schemas import (Intent, NodeName, RiskLevel, RoutingDecision, Status,
                      Urgency, ValidationError)

__all__ = [
    "Engine", "Event", "Router", "HybridAdapter", "RuleClassifier",
    "QwenLocalAdapter", "default_adapter", "default_nodes", "Intent", "NodeName", "RiskLevel",
    "Urgency", "Status", "RoutingDecision", "ValidationError",
]
