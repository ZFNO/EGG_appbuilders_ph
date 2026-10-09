"""Tests for the local model path and the hybrid (rules + model) policy."""
import os
import unittest

from invisible_secretary import Engine
from invisible_secretary.model_adapter import HybridAdapter, RuleClassifier


class FakeModel:
    """Deterministic stand-in for the local model (no 786MB load)."""

    name = "fake-local"

    def __init__(self, table, available=True):
        self.table = table
        self._available = available

    def available(self):
        return self._available

    def classify(self, text):
        for key, out in self.table.items():
            if key in text:
                return out
        return {"intent": "unknown", "parameters": {}, "confidence": 0.0}


class TestHybridPolicy(unittest.TestCase):
    def test_agreement_boosts_confidence(self):
        m = FakeModel({"supplier": {"intent": "supplier_followup", "parameters": {},
                                    "confidence": 0.9}})
        out = HybridAdapter(m).classify("Ask the supplier to confirm today's delivery")
        self.assertEqual(out["intent"], "supplier_followup")
        self.assertGreater(out["confidence"], 0.88)
        self.assertNotIn("conflict", out)

    def test_model_fills_missing_params_only(self):
        m = FakeModel({"supplier": {"intent": "supplier_followup",
                                    "parameters": {"entity_name": "Reyes Trading"},
                                    "confidence": 0.9}})
        out = HybridAdapter(m).classify("Ask the supplier to confirm today's delivery")
        self.assertEqual(out["parameters"]["entity_name"], "Reyes Trading")
        # rule-derived value is never overwritten by the model
        self.assertEqual(out["parameters"]["entity_type"], "supplier")

    def test_disagreement_abstains(self):
        m = FakeModel({"meeting": {"intent": "supplier_followup", "parameters": {},
                                   "confidence": 0.9}})
        out = HybridAdapter(m).classify("Please move my meeting with Ana to Friday")
        self.assertEqual(out["rules_intent"], "schedule_change")
        self.assertIn("conflict", out)
        self.assertLess(out["confidence"], 0.55)

    def test_disagreement_forces_clarification(self):
        m = FakeModel({"meeting": {"intent": "supplier_followup", "parameters": {},
                                   "confidence": 0.9}})
        ev = Engine(HybridAdapter(m)).process("h1", "Please move my meeting with Ana to Friday")
        self.assertEqual(ev.state, "needs_clarification")

    def test_model_parse_error_abstains(self):
        m = FakeModel({"supplier": {"intent": "unknown", "parameters": {},
                                    "confidence": 0.0, "parse_error": True}})
        out = HybridAdapter(m).classify("Ask the supplier to confirm today's delivery")
        self.assertLess(out["confidence"], 0.55)

    def test_model_crash_does_not_break_routing(self):
        class Boom(FakeModel):
            def classify(self, text):
                raise RuntimeError("onnx blew up")
        out = HybridAdapter(Boom({})).classify("Ask the supplier to confirm today's delivery")
        self.assertEqual(out["intent"], "supplier_followup")  # rules still work
        self.assertIn("model_error", out)

    def test_rules_only_when_model_absent(self):
        out = HybridAdapter(None).classify("A customer complained about a broken order")
        self.assertEqual(out["intent"], "customer_request")
        self.assertEqual(out["model_used"], "rule-deterministic")

    def test_no_cloud_fallback(self):
        # A model that is present but unavailable must not silently become a
        # remote call; the adapter stays on rules and reports no model use.
        m = FakeModel({}, available=False)
        out = HybridAdapter(m).classify("A customer complained")
        self.assertEqual(out["model_used"], "rule-deterministic")


@unittest.skipUnless(
    __import__("invisible_secretary.local_qwen", fromlist=["QwenOnnxAdapter"])
    .QwenOnnxAdapter.discover_default(), "no local ONNX model found")
class TestRealOnnxModel(unittest.TestCase):
    """Opt-in: exercises the REAL on-device Qwen2.5-0.5B ONNX model."""

    @classmethod
    def setUpClass(cls):
        from invisible_secretary.local_qwen import QwenOnnxAdapter
        from invisible_secretary.model_adapter import QwenLocalAdapter
        cls.adapter = QwenLocalAdapter(QwenOnnxAdapter.discover_default())

    def test_classifies_a_clear_request(self):
        out = self.adapter.classify("Ask the supplier to confirm today's delivery")
        self.assertEqual(out["intent"], "supplier_followup")

    def test_output_is_bounded_to_the_intent_set(self):
        from invisible_secretary.local_qwen import INTENTS
        out = self.adapter.classify("A customer complained about a broken order")
        self.assertIn(out["intent"], INTENTS)


class TestModelRegistry(unittest.TestCase):
    def test_discovers_canonical_model(self):
        from invisible_secretary.model_registry import discover_models, CANONICAL_ROOT
        models = discover_models()
        self.assertTrue(models, "expected at least one local model")
        canon = [m for m in models if m["source"] == "canonical"]
        self.assertTrue(canon, f"no model under {CANONICAL_ROOT}")
        self.assertTrue(all(m["quant"] == "q4" for m in models))

    def test_resolve_by_id_and_path(self):
        from invisible_secretary.model_registry import discover_models, resolve_model
        m = discover_models()[0]
        self.assertEqual(resolve_model(m["id"]), m["path"])
        self.assertEqual(resolve_model(m["name"]), m["path"])
        self.assertEqual(resolve_model(m["path"]), m["path"])
        self.assertIsNone(resolve_model("does-not-exist"))

    def test_default_adapter_uses_selected_model(self):
        from invisible_secretary.factory import default_adapter
        m = __import__("invisible_secretary.model_registry", fromlist=["discover_models"]).discover_models()[0]
        ad = default_adapter(model=m["id"])
        self.assertIn("qwen-local", ad.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
