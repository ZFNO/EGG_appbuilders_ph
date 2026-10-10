// Invisible Secretary - browser client for the local model sidecar.
//
// Runs the on-device model OUT of the page: this module installs
// globalThis.__IS_ONNX_BACKEND__ so local_qwen.js's QwenOnnxAdapter picks up a
// real backend, and probes the sidecar so the dashboard can show whether the
// model is loaded. If the sidecar is down the adapter reports unavailable and
// the engine runs rules-only. There is no cloud fallback, ever.
//
// Contract (same as the Python adapter): { available(): bool, classify(text): dict }
// classify is ASYNC here (network) - the model path is awaited end-to-end.

import * as configStore from "./config_store.js";

const _cfg = configStore.load();
const URL = String(globalThis.IS_SIDECAR_URL || _cfg.sidecar_url || "http://127.0.0.1:8765").replace(/\/+$/, "");
const DEFAULT_MODEL = "Qwen2.5-0.5B-Instruct";

// Live status, read synchronously by available() / the status indicator.
const state = { ready: false, model: null, error: null, url: URL };

async function probe() {
  try {
    const r = await fetch(URL + "/health", { cache: "no-store" });
    const h = await r.json();
    state.ready = !!h.ready;
    state.model = h.model || null;
    state.error = h.error || null;
  } catch (e) {
    state.ready = false;
    state.error = String((e && e.message) || e);
  }
  return state;
}

const backend = {
  get name() { return "qwen2.5-0.5b-onnx"; },
  // a stable, human-readable model dir name for describe()
  get model_path() { return state.model || _cfg.model || DEFAULT_MODEL; },
  available() { return state.ready; },
  async classify(text) {
    const r = await fetch(URL + "/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text || "" }),
    });
    const out = await r.json();
    if (!r.ok || out.status === "unavailable" || out.status === "error") {
      throw new Error(out.reason || ("sidecar http " + r.status));
    }
    return out;
  },
  // Ask the model to read a plain-language identity profile and propose
  // Options settings. Same bounded contract: it only ever returns suggestions.
  async infer_config(text) {
    const r = await fetch(URL + "/infer_config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text || "" }),
    });
    const out = await r.json();
    if (!r.ok || out.status === "unavailable" || out.status === "error") {
      throw new Error(out.reason || ("sidecar http " + r.status));
    }
    return out;
  },
};

globalThis.__IS_ONNX_BACKEND__ = backend;
globalThis.__IS_SIDECAR_STATE__ = state;

// Probe now and keep it fresh (cheap) so the indicator never lies.
// Browser only - under Node (tests) there is no window; available() stays false
// and the engine runs rules-only, so the smoke tests never touch the network.
if (typeof window !== "undefined") {
  probe();
  setInterval(probe, 5000);
}

// A ready-to-use inference hook for profile_store.infer(): returns undefined
// when the model is not available, so callers cleanly fall back to rules.
export function profileLlm() {
  if (backend.available() && typeof backend.infer_config === "function") {
    return (text) => backend.infer_config(text);
  }
  return undefined;
}

export { URL as SIDECAR_URL, DEFAULT_MODEL, state as sidecarState, probe };
