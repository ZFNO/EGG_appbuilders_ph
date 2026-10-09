"""Adapter factory: rules primary + a selected on-device model, if present.

Keeps model discovery/selection in one place so the CLI, API and tests all wire
up the same way. Never falls back to a cloud service; if no local model is
found (or one is explicitly deselected) the deterministic rules run alone.
"""
from __future__ import annotations

import os

from .model_adapter import HybridAdapter, QwenLocalAdapter


def default_adapter(*, use_model: bool = True, model: str | None = None) -> HybridAdapter:
    """Build the production adapter.

    ``model`` may be a picker id (e.g. ``qwen2.5-0.5b-instruct``), a folder
    name, or an explicit path; ``None`` auto-selects the canonical model.
    """
    chosen = None
    if model is None:
        model = os.environ.get("IS_MODEL") or None
    if use_model:
        try:
            from .local_qwen import QwenOnnxAdapter
            d = QwenOnnxAdapter.discover_default(model)
            if d:
                chosen = QwenLocalAdapter(d)
        except Exception:
            chosen = None
    return HybridAdapter(chosen, use_model=use_model)
