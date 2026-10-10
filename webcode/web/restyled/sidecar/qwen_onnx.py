"""Local ONNX inference for the Invisible Secretary dashboard (Qwen2.5-0.5B-Instruct q4).

Self-contained port of invisible_secretary/local_qwen.py. Runs the on-device
model through onnxruntime with a hand-rolled KV-cache greedy decoder. Fully
local: no network, no CDN, no cloud fallback. The model performs BOUNDED intent
classification only; the router remains the policy engine.

Model bundle (self-hosted, Transformers.js layout) lives UNDER this project:
    <restyled>/models/<ModelName>/{config.json, tokenizer.json, tokenizer_config.json,
                                   onnx/model_q4.onnx}
"""
from __future__ import annotations

import glob
import json
import os
import re
import time
from pathlib import Path

INTENTS = ["supplier_followup", "customer_followup", "schedule_change",
           "customer_request", "unknown", "out_of_scope"]

_SYS = ("You are a routing classifier. Read the business request and reply with "
        "ONLY a JSON object: {\"intent\": <one of " + ", ".join(INTENTS) +
        ">, \"topic\": <short phrase>, \"entity_name\": <name or null>, "
        "\"deadline\": <YYYY-MM-DD or null>}. No prose.")

# Reads a person's plain-language identity profile and proposes Options settings.
_SYS_PROFILE = ("You read a short description of how a person likes their assistant to work "
                "and reply with ONLY a JSON object: {\"confidence_floor\": <0..1>, "
                "\"use_model\": <true|false>, \"urgency_critical\": [<words>], "
                "\"urgency_high\": [<words>], \"out_of_scope_keywords\": [<words>], "
                "\"summary\": <one short line>}. Suggest values only. No prose.")

# sidecar/ -> restyled/ ; models are vendored at <restyled>/models
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = PROJECT_ROOT / "models"


def discover_models() -> list[dict]:
    """Every usable model under <restyled>/models (canonical store only)."""
    out = []
    if not MODELS_ROOT.exists():
        return out
    for tok in sorted(glob.glob(str(MODELS_ROOT / "**" / "tokenizer.json"), recursive=True)):
        d = Path(tok).parent
        onnx = sorted(glob.glob(str(d / "**" / "*.onnx"), recursive=True))
        if not onnx:
            continue
        hits = [p for p in onnx if "q4" in os.path.basename(p).lower()]
        out.append({
            "id": d.name.lower(),
            "name": d.name,
            "path": str(d),
            "quant": "q4" if hits else "fp32",
            "weights": os.path.basename(hits[0] if hits else onnx[0]),
        })
    return out


def resolve_model(token: str | None = None) -> str | None:
    """Resolve a picker id, folder name, or path to a concrete model dir."""
    if token:
        p = Path(token)
        if p.is_dir():
            return str(p.resolve())
        t = token.lower()
        for m in discover_models():
            if t in (m["id"], m["name"].lower()):
                return m["path"]
    found = discover_models()
    return found[0]["path"] if found else None


class QwenOnnxAdapter:
    name = "qwen2.5-0.5b-onnx"

    def __init__(self, model_dir: str | None = None, *, max_new_tokens: int = 48,
                 num_threads: int = 1):
        self.model_dir = model_dir
        self.max_new_tokens = max_new_tokens
        self.num_threads = num_threads
        self._sess = None
        self._tok = None
        self._nl = 24
        self._kv_heads = 2
        self._head_dim = 64
        self.last_latency_s: float | None = None

    # -- availability ---------------------------------------------------
    @staticmethod
    def discover_default(model: str | None = None) -> str | None:
        return resolve_model(model)

    def _onnx_path(self) -> str | None:
        if not self.model_dir:
            return None
        hits = glob.glob(os.path.join(self.model_dir, "**", "*.onnx"), recursive=True)
        return hits[0] if hits else None

    def available(self) -> bool:
        if not self.model_dir or not os.path.exists(os.path.join(self.model_dir, "tokenizer.json")):
            return False
        return self._onnx_path() is not None

    def _ensure_loaded(self):
        if self._sess is not None:
            return
        import numpy as np  # noqa: F401
        import onnxruntime as ort
        from transformers import AutoTokenizer

        path = self._onnx_path()
        if not path:
            raise RuntimeError("no .onnx weights found")
        so = ort.SessionOptions()
        so.intra_op_num_threads = self.num_threads
        self._sess = ort.InferenceSession(path, sess_options=so,
                                          providers=["CPUExecutionProvider"])
        self._tok = AutoTokenizer.from_pretrained(self.model_dir)
        ins = [i.name for i in self._sess.get_inputs()]
        self._nl = sum(1 for n in ins if n.endswith(".key"))

    # -- generation -----------------------------------------------------
    def _empty_past(self):
        import numpy as np
        return {f"past_key_values.{i}.{k}": np.zeros((1, self._kv_heads, 0, self._head_dim),
                                                     dtype=np.float32)
                for i in range(self._nl) for k in ("key", "value")}

    def _generate(self, messages: list[dict]) -> str:
        import numpy as np
        self._ensure_loaded()
        ids = self._tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=True)
        ids = np.array([ids], dtype=np.int64)
        attn = np.ones((1, ids.shape[1]), dtype=np.int64)
        pos = np.arange(ids.shape[1], dtype=np.int64)[None, :]
        cur = ids
        past = self._empty_past()
        out = []
        t0 = time.time()
        for _ in range(self.max_new_tokens):
            feed = {"input_ids": cur, "attention_mask": attn, "position_ids": pos}
            feed.update(past)
            res = self._sess.run(None, feed)
            nxt = int(np.argmax(res[0][0, -1]))
            if nxt == self._tok.eos_token_id:
                break
            out.append(nxt)
            past = {f"past_key_values.{i}.{k}": res[1 + i * 2 + (0 if k == "key" else 1)]
                    for i in range(self._nl) for k in ("key", "value")}
            cur = np.array([[nxt]], dtype=np.int64)
            attn = np.concatenate([attn, np.ones((1, 1), dtype=np.int64)], axis=1)
            pos = np.array([[attn.shape[1] - 1]], dtype=np.int64)
        self.last_latency_s = time.time() - t0
        return self._tok.decode(out, skip_special_tokens=True)

    @staticmethod
    def _parse(raw: str) -> dict | None:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        if obj.get("intent") not in INTENTS:
            return None
        return obj

    # -- public interface ----------------------------------------------
    def classify(self, text: str) -> dict:
        raw = self._generate([{"role": "system", "content": _SYS},
                              {"role": "user", "content": text}])
        obj = self._parse(raw)
        if obj is None:
            return {"intent": "unknown", "parameters": {}, "confidence": 0.0,
                    "urgency_hint": "normal", "model_used": self.name,
                    "raw": raw[:200], "parse_error": True}
        params = {k: v for k, v in (("entity_name", obj.get("entity_name")),
                                    ("topic", obj.get("topic")),
                                    ("deadline", obj.get("deadline"))) if v}
        if obj["intent"] in ("supplier_followup", "customer_followup"):
            params.setdefault("entity_type",
                              "supplier" if obj["intent"] == "supplier_followup" else "customer")
        return {"intent": obj["intent"], "parameters": params, "confidence": 0.9,
                "urgency_hint": "normal", "model_used": self.name,
                "latency_s": self.last_latency_s}

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    # Read a plain-language profile -> proposed Options settings (suggestions only).
    def infer_config(self, text: str) -> dict:
        raw = self._generate([{"role": "system", "content": _SYS_PROFILE},
                              {"role": "user", "content": text}])
        obj = self._parse_json(raw)
        if obj is None:
            return {"suggestions": {}, "summary": None,
                    "notes": ["model returned no JSON"], "raw": raw[:200],
                    "latency_s": self.last_latency_s}
        keys = ("use_model", "model", "confidence_floor", "urgency_critical",
                "urgency_high", "out_of_scope_keywords")
        sug = {k: obj.get(k) for k in keys if obj.get(k) is not None}
        return {"suggestions": sug, "summary": obj.get("summary"),
                "notes": ["read by " + self.name], "latency_s": self.last_latency_s}
