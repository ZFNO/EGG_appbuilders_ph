// Invisible Secretary - model registry (port of model_registry.py).
//
// Python scanned the filesystem for ONNX bundles. The browser build has no
// filesystem, so discovery returns an empty catalogue and every resolve fails
// (which is exactly the "no local model found -> rules only" path). The shape of
// the returned records is preserved so callers/UI keep the same contract.

export const CANONICAL_ROOT = "models"; // was <project>/models

// Searched in order in Python (canonical store, then legacy bundles). None of
// these exist in the browser; kept for contract fidelity / future provisioning.
export const LEGACY_ROOTS = [
  "webcode/mobile/dist/models",
  "apk/app/src/main/assets/models",
  "webcode/mobile/models",
];

// Return every usable local model. Browser build: none.
export function discoverModels(_includeLegacy = true) {
  return [];
}

// Resolve a picker id, folder name, or path to a concrete model dir.
export function resolveModel(_token) {
  return null;
}
