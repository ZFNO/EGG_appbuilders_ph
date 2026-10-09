# BUILDER — WebView WASM wiring (next actionable DONE)
Owner: BUILDER@4472 (run owner) | 2026-10-09

## What changed (webcode/mobile/)
- src/main.js: offline extraction surface. @huggingface/transformers -> onnxruntime-web (WASM).
  env.allowRemoteModels=false; localModelPath=./models/; wasmPaths=./ort/; numThreads=1 (no COOP/COEP).
  fetch() hard-throws on http(s) -> net_attempts must stay 0 (airplane mode).
- public/models/ = self-hosted Qwen2.5-0.5B-Instruct q4 (from spike/models). NO CDN.
- public/ort/ = local ort-wasm-* (26 files, incl. simd-threaded.asyncify.wasm). NO CDN.
- hybrid name heuristic (label + first-line/root-name) to push name past 8/10 (margin fix).
- receipts: sha256 hash/append-log only (no chain/on-chain). wallets+RAG = MOCKS.
- UI: Extract->receipt, Run on-device gate. window.runGate() for headless gate.

## Build verify
npx vite build -> dist/ OK. base './' (file:///android_asset). dist has assets/ + models/ + ort/.
index.html -> ./assets/index-*.js ; ort wasm asset emitted.

## STILL OPEN (needs device, not doable here)
1. On-device gate re-run: load dist in APK WebView, call runGate(). PASS = acc>=0.90 AND worst<5s AND net=0 AND chain_valid.
2. Confirm APK WebView >= Chrome 57 (WASM). Car head-unit Android 4.3 = sensor-only, no WASM.
3. Margin: 90.0% is AT threshold (spike). Phone latency may exceed 4.4s. If gate FAILS -> bump 0.5B->1.5B.
