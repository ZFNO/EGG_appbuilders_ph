// Invisible Secretary - on-device model backend (port of local_qwen.py).
//
// In the browser there is no filesystem and no server: this module is an INERT
// WebGPU / ONNX-or-no-op adapter behind the SAME interface the Python
// QwenOnnxAdapter exposes. Until real weights are provisioned it reports
// unavailable, so model_adapter's HybridAdapter runs RULES-ONLY. There is never
// a cloud fallback - classification is an enhancement, never a requirement.
//
// A real backend IS injected at window.__IS_ONNX_BACKEND__ by sidecar_client.js
// (a localhost Python sidecar hosting the weights out-of-process). It must
// expose { available(): bool, classify(text): Promise<{intent, parameters, ...}> }.

export const INTENTS = [
  "supplier_followup", "customer_followup", "schedule_change",
  "customer_request", "unknown", "out_of_scope",
];

const SYS_PROMPT = 'You are a routing classifier. Read the business request and reply with ' +
  'ONLY a JSON object: {"intent": <one of ' + INTENTS.join(", ") +
  '>, "topic": <short phrase>, "entity_name": <name or null>, "deadline": <YYYY-MM-DD or null>}. No prose.';

// Is a WebGPU device even plausible here? (informational only - the adapter
// stays inert until weights are supplied, so routing never depends on it).
export function webgpuPlausible() {
  return typeof navigator !== "undefined" && !!navigator.gpu;
}

// Locate an on-device model. With a sidecar backend installed the model lives
// out-of-process; report its dir/name so the factory wires a real adapter. With
// no backend the static build stays rules-only (no weights, no cloud fallback).
export function discoverDefault(_model = null) {
  const injected = (typeof globalThis !== "undefined" && globalThis.__IS_ONNX_BACKEND__) || null;
  if (injected) return injected.model_path || "Qwen2.5-0.5B-Instruct";
  return null;
}

// Inert backend that satisfies the ModelAdapter interface.
export class QwenOnnxAdapter {
  constructor(modelDir = null) {
    this.name = "qwen2.5-0.5b-onnx";
    this.model_dir = modelDir;
    this._injected = (typeof globalThis !== "undefined" && globalThis.__IS_ONNX_BACKEND__) || null;
  }

  available() {
    if (this._injected && typeof this._injected.available === "function") {
      return this._injected.available();
    }
    // No weights provisioned in the static build -> rules-only.
    return false;
  }

  async classify(text) {
    if (this._injected && typeof this._injected.classify === "function") {
      return await this._injected.classify(text);
    }
    throw new Error("local model not provisioned; no cloud fallback permitted");
  }
}
