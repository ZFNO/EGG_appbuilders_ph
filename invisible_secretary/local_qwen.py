"""Local ONNX inference for the Invisible Secretary (Qwen2.5-0.5B-Instruct q4).

Runs the on-device model through onnxruntime with KV-cache greedy decoding.
Fully local: no network, no CDN, no cloud fallback. The model performs BOUNDED
intent classification only; the router remains the policy engine.

The model directory is a self-hosted Transformers.js-style bundle:
    <dir>/config.json, tokenizer.json, tokenizer_config.json,
    <dir>/onnx/model_q4.onnx
"""
from __future__ import annotations

import glob
import json
import os
import re
import time

INTENTS = ["supplier_followup", "customer_followup", "schedule_change",
           "customer_request", "unknown", "out_of_scope"]

_SYS = ("You are a routing classifier. Read the business request and reply with "
        "ONLY a JSON object: {\"intent\": <one of " + ", ".join(INTENTS) +
        ">, \"topic\": <short phrase>, \"entity_name\": <name or null>, "
        "\"deadline\": <YYYY-MM-DD or null>}. No prose.")


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
        """Locate the on-device model.

        Prefers ``<project>/models/<ModelName>/`` (canonical store), falling
        back to legacy bundle paths. Pass ``model`` to pick by id/name/path.
        """
        try:
            from .model_registry import discover_models, resolve_model
        except Exception:
            return None
        if model:
            return resolve_model(model)
        found = discover_models()
        return found[0]["path"] if found else None

    def _onnx_path(self) -> str | None:
        if not self.model_dir:
            return None
        hits = glob.glob(os.path.join(self.model_dir, "**", "*.onnx"), recursive=True)
        return hits[0] if hits else None

    def available(self) -> bool:
        if not self.model_dir or not os.path.exists(os.path.join(self.model_dir, "tokenizer.json")):
            return self.model_dir is None  # unresolved dir -> try discovery
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
        # read kv geometry from the graph
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
