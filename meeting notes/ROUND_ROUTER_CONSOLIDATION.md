# LEAD CONSOLIDATION — Round: Router Concierge
Date: 2026-10-09
Filed by: Secretary/Researcher
Status: AGENDized — filed for the record

## R1 — Router concierge, LOCAL AI (<=12 lines)
AGREED: Router = tiered confidence bands (high = auto-act / mid = ask one-tap / low = escalate).
Non-LLM carriers (embeddings+ANN, classifiers, FSM) do the triggering <200ms offline; SLM only on escalate.
Receipts = audit/trust layer on every auto-act.
Fully offline, no cloud key.
This is the "invisible" definition — not a bolted-on feature.

## RESEARCHER FACTS (cited)
- Ollama CANNOT run in Android WebView (native Go sidecar; only via Termux).
- WebView-native offline = llama.cpp/wllama (WASM) or Transformers.js.
- Mobile ANN: sqlite-vec / hnswlib / vectorlite; full RAG <50MB, sub-200ms.
- Tiered/probability routing is mature: RouteNLP tiered routing; Conformal Cascade; conformal LLM routing; calibrated abstention.
- Caveat: raw LLM confidence is miscalibrated -> needs conformal calibration.

## CONFLICTS
(a) CEO brief says "Ollama models" — INFEASIBLE in our WebView surface; must substitute wllama/Transformers.js.
(b) Innovator wants crypto receipts as differentiator vs Builder: on-chain OUT, hash/append-log receipts IN (chain adds no 20h judge value).

## BIGGEST RISK
Runtime, not design — on-device SLM reliability/perf (WebGPU/WebView) unverified; probability tiers need real signal/volume we lack.

## BUILDABILITY
Builder = SPEC ONLY under current warrant; ALL executable code blocked by missing product-write access.

## GO-GATE
CONDITIONAL / BLOCKED. Design GO. Build NO until CEO either:
(1) grants product write access to Builder/Lead, or
(2) expands Lead warrant to run the runtime spike.
Until then: no demo.
Definition of done unchanged: offline, no-CDN model load, verified on-device by Lead.
