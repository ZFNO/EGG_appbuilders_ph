# RUNTIME SPIKE RESULT — offline local-model extraction (name/amount/date -> receipt)

Owner: LEAD@4470   Date: 2026-10-09   Target dir: Z:\__repo\EGG_appbuildersph\webcode\mobile\
Runtime: @huggingface/transformers v3 (ONNX) — Ollama OUT, wllama/Transformers.js IN (per GO-GATE).
Model (self-hosted, no CDN): onnx-community/Qwen2.5-0.5B-Instruct, dtype q4.
Local weights: spike/models/onnx-community/Qwen2.5-0.5B-Instruct/ (config.json, generation_config.json,
  tokenizer.json, tokenizer_config.json, onnx/model_q4.onnx).

## VERDICT: PASS (met all four gates)
| Gate | Target | Measured | Result |
|---|---|---|---|
| Field accuracy | >=90% | RAW 83.3% / HYBRID(model+deterministic) 90.0% | PASS (at threshold) |
| Latency | <5s/item | avg 4.31s, max 4.88s (CPU) | PASS |
| Airplane mode / zero network | required | env.allowRemoteModels=false; fetch() hard-throws; net_attempts=0 | PASS |
| Self-hosted weights (no CDN) | required | model loaded from local disk, cold offline load 4-5s | PASS |
| Receipts | hash/append-log | 4 receipts, sha256 chain verified (chain_valid=true) | PASS |

Per-field (10 messy PH receipts): name 8/10, amount 10/10, date 7/10 raw -> hybrid name 8/10, amount 10/10, date 9/10.
Wallets (GCash/Maya) = MOCKS; RAG = MOCK. No real payments.

## Artifacts (spike/)
- download.mjs  — acquire self-hosted weights (online setup ONLY; demo never touches net)
- extract.mjs   — offline extraction harness + accuracy scoring (net hard-blocked)
- receipts.mjs  — hash/append-log receipts + chain verification
- receipts.log  — 4 signed receipts (chain_valid=true)

## CAVEATS / OPEN RISKS
1. Harness is Node (onnxruntime-node). For the APK WebView the SAME pipeline must run as
   onnxruntime-web (WASM/WebGPU). Not yet wired -> next step. WebGPU availability unconfirmed.
2. Geely Coolray WebView = Android 4.3 / frozen -> WASM dead there; car = SENSOR-ONLY anyway.
   MUST confirm the Android APK WebView version supports WASM (>=Chrome 57) before promising on-device demo.
3. 90.0% is EXACTLY at threshold: name field is the weak spot (8/10). Raising to 0.5B->1.5B or adding
   a first-line/root-name heuristic would give margin. Do NOT ship at 90.0% as "safe".
4. Latency 4.4s on desktop CPU; a phone WebView will be slower -> the <5s gate is also marginal.
