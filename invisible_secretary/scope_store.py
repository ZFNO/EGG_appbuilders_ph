"""Invisible Secretary - live scope configuration (single editable home).

Scope is not one file in the original design. It is spread across modules:

  * the intent -> node *mapping* .......... schemas.INTENT_TO_NODE
  * the dispatch *policy* ................. router.py (REQUIRED_PARAMS, risk)
  * the *keywords that decide rejection* ... model_adapter._RULES (out_of_scope)
  * the reachable *capabilities* .......... nodes.default_nodes()

This module gives the one lever that changes live behaviour - the
``out_of_scope_keywords`` list - a single persisted home (``data/scope.json``)
so the /scope page can update what is out of scope on the spot, with no code
edit. Everything else is surfaced read-only and labelled informational.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
SCOPE_FILE = HERE.parent / "data" / "scope.json"

# The seed set of rejected keywords. Mirrors the original in-code rule.
DEFAULT_OUT_OF_SCOPE: list[str] = [
    "pay", "payment", "purchase", "buy", "transfer", "wire", "delete",
    "erase", "refund money", "legal", "lawsuit", "hire", "fire",
    "terminate employee",
]

_lock = threading.RLock()


def default_scope() -> dict:
    return {"out_of_scope_keywords": list(DEFAULT_OUT_OF_SCOPE), "updated": None}


def _normalise(kws) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for k in kws or []:
        if not isinstance(k, str):
            continue
        k = k.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def load() -> dict:
    """Return the effective scope config (file over defaults), normalised."""
    with _lock:
        cfg = default_scope()
        if SCOPE_FILE.exists():
            try:
                data = json.loads(SCOPE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    cfg.update(data)
            except (OSError, json.JSONDecodeError):
                pass
        cfg["out_of_scope_keywords"] = _normalise(cfg.get("out_of_scope_keywords"))
        return cfg


def save(keywords, *, updated: str | None = None) -> dict:
    """Persist an out-of-scope keyword list and return the stored config."""
    with _lock:
        cfg = {
            "out_of_scope_keywords": _normalise(keywords),
            "updated": updated or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        SCOPE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCOPE_FILE.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        return cfg


def out_of_scope_keywords() -> list[str]:
    """The live rejection keyword list (read on every classification)."""
    return load()["out_of_scope_keywords"]


# --------------------------------------------------------------------------
# Informational catalogue (read-only mirror of code) used by the /scope page.
# --------------------------------------------------------------------------
IN_SCOPE: list[dict] = [
    {"intent": "supplier_followup", "node": "followup", "risk": "R3",
     "label": "Follow up with a supplier / vendor",
     "required_params": ["entity_type"],
     "example": "Follow up with Acme supplier - order #4471 not confirmed"},
    {"intent": "customer_followup", "node": "followup", "risk": "R3",
     "label": "Follow up with a customer / client",
     "required_params": ["entity_type"],
     "example": "Chase the customer at Bright Co about the late delivery"},
    {"intent": "schedule_change", "node": "scheduling", "risk": "R3",
     "label": "Reschedule / move a meeting",
     "required_params": ["topic"],
     "example": "Reschedule Thursday's meeting to Friday"},
    {"intent": "customer_request", "node": "customer_request", "risk": "R2",
     "label": "Triage a customer request or complaint",
     "required_params": ["topic"],
     "example": "Customer reports a broken widget, asks for help"},
]

URGENCY_KEYWORDS: dict[str, list[str]] = {
    "critical": ["immediately", "asap", "as soon as possible"],
    "high": ["today", "urgent", "overdue", "late"],
}


def overview() -> dict:
    """Assemble the full read-only scope picture for the UI."""
    from . import schemas
    from .router import _ACTION_RISK, CONFIDENCE_FLOOR

    try:
        from .nodes import default_nodes
        nodes = {n.name: n for n in default_nodes().values()}
    except Exception:  # pragma: no cover - defensive
        nodes = {}

    cfg = load()

    intents = []
    for row in IN_SCOPE:
        node = row["node"]
        n = nodes.get(node)
        intents.append({
            **row,
            "requires_approval": _ACTION_RISK.get(row["intent"], schemas.RiskLevel.R1)
            in (schemas.RiskLevel.R2, schemas.RiskLevel.R3),
            "node_description": getattr(n, "description", ""),
            "action": getattr(n, "consequential_action", None),
        })

    return {
        "out_of_scope_keywords": cfg["out_of_scope_keywords"],
        "updated": cfg.get("updated"),
        "confidence_floor": CONFIDENCE_FLOOR,
        "in_scope": intents,
        "urgency_keywords": URGENCY_KEYWORDS,
        "nodes": [
            {"node": n.name, "description": getattr(n, "description", ""),
             "action": getattr(n, "consequential_action", None),
             "health": n.health().get("health", "ok")}
            for n in nodes.values()
        ],
    }
