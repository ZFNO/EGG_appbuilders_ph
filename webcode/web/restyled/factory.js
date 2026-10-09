// Adapter factory: rules primary + a selected on-device model, if present.
// Port of factory.py. Keeps model selection in one place. Never falls back to a
// cloud service; with no local model the deterministic rules run alone.

import { HybridAdapter, QwenLocalAdapter } from "./model_adapter.js";
import { QwenOnnxAdapter, discoverDefault } from "./local_qwen.js";

// Build the production adapter. `model` may be a picker id, folder name, or an
// explicit path; null auto-selects the canonical model (none in the browser).
export function defaultAdapter(opts = {}) {
  const useModel = opts.useModel === undefined ? true : opts.useModel;
  let model = opts.model;
  if (model === undefined || model === null) {
    model = (typeof globalThis !== "undefined" && globalThis.IS_MODEL) || null;
  }

  let chosen = null;
  if (useModel) {
    try {
      const dir = discoverDefault(model);
      if (dir) {
        const backend = new QwenOnnxAdapter(dir);
        chosen = new QwenLocalAdapter(dir, backend);
      }
    } catch (e) {
      chosen = null;
    }
  }
  return new HybridAdapter(chosen, { useModel });
}
