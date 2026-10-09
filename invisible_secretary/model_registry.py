"""Model registry: find and identify local ONNX models.

Canonical store is ``<project>/models/<ModelName>/`` (each model in its own
folder, holding ``tokenizer.json`` + ``onnx/*.onnx``). Legacy bundle locations
are still searched so nothing breaks if a copy lives elsewhere. No network.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

# Project root = parent of the package dir (…/egg).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = PROJECT_ROOT / "models"

# Searched in order: canonical store first, then legacy bundles (read-only).
LEGACY_ROOTS = [
    Path(r"Z:\__repo\EGG_appbuildersph\webcode\mobile\dist\models"),
    Path(r"Z:\__repo\EGG_appbuildersph\apk\app\src\main\assets\models"),
    Path(r"Z:\__repo\EGG_appbuildersph\webcode\mobile\models"),
]


def _has_model(d: Path) -> bool:
    return (d / "tokenizer.json").exists() and bool(
        glob.glob(str(d / "**" / "*.onnx"), recursive=True))


def _classify_dir(d: Path) -> dict:
    onnx = sorted(glob.glob(str(d / "**" / "*.onnx"), recursive=True))
    size = sum(os.path.getsize(p) for p in onnx)
    hits = [p for p in onnx if "q4" in os.path.basename(p).lower()]
    return {
        "id": d.name.lower(),
        "name": d.name,
        "path": str(d),
        "quant": "q4" if hits else "fp32",
        "weights": os.path.basename(hits[0]) if hits else (
            os.path.basename(onnx[0]) if onnx else None),
        "size_mb": round(size / 1e6, 1),
        "source": "canonical" if CANONICAL_ROOT in d.parents else "legacy",
    }


def discover_models(include_legacy: bool = True) -> list[dict]:
    """Return every usable local model, canonical store first, deduped by path."""
    roots = [CANONICAL_ROOT] + (LEGACY_ROOTS if include_legacy else [])
    seen, out = set(), []
    for root in roots:
        if not root.exists():
            continue
        for tok in glob.glob(str(root / "**" / "tokenizer.json"), recursive=True):
            d = Path(tok).parent.resolve()
            if str(d) in seen or not _has_model(d):
                continue
            seen.add(str(d))
            out.append(_classify_dir(d))
    return out


def resolve_model(token: str | None) -> str | None:
    """Resolve a picker id, folder name, or path to a concrete model dir."""
    if not token:
        return None
    p = Path(token)
    if p.is_dir() and _has_model(p):
        return str(p.resolve())
    t = token.lower()
    for m in discover_models():
        if t in (m["id"], m["name"].lower()):
            return m["path"]
    # last resort: a partial folder-name match in the canonical store
    for d in glob.glob(str(CANONICAL_ROOT / "*")):
        if Path(d).is_dir() and t in Path(d).name.lower() and _has_model(Path(d)):
            return str(Path(d).resolve())
    return None
