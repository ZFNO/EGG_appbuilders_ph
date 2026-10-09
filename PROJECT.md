# PROJECT DOCUMENT
Owner: Secretary/Researcher@4475 | Date: 2026-10-09 | Theme: LOCAL AI

## 1. One-Liner
A local AI that does your menial work — data entry, monitoring, private info — paid through your GCash/Maya allowance, entirely on-device.

## 2. Thesis
Local AI does the work; services stay online. The local/online split: on-device model performs extraction/monitoring on private data (nothing leaves the phone); online services handle settlement/verification. Local = privacy + offline; online = anything needing a network counterparty.

## 3. Unadopted Draft
UNADOPTED. Team of one CEO + two personas (Skeptic = rigor/pro, Innovator = optimistic). Offline-first, knowledge-first; phone + car as nodes. Product = local AI doing menial work. GCash/Maya allowance framed as "your property / your rules / your receipts" — this is UX consent + spend caps, deliberately NOT a legal shield (no POA / legal claims).

## 4. Settled Decisions
(a) AI local, services online — no contradiction.
(b) The two demo halves must BOTH work live.
(c) Allowance = UX, not statute.

## 5. GO-GATE / First Spike (unanimous)
Local model extracts structured fields (name / amount / date) from messy input -> emits a receipt. Wallets/RAG = MOCKS.
PASS = >=90% fields correct, <5s, AIRPLANE MODE, zero network, model from self-hosted asset. FAIL = replan. ~4h.
Retires the one empirical unknown: can the local AI actually do the work.

## 6. Hard Finding (cited)
2022 Geely Coolray ships GKUI on Android 4.3 with frozen WebKit WebView -> NO WASM (needs WebView 57+ / Chromium). Sources: github.com/ginomeee/geely; caniuse.com/wasm.
VERDICT: car is NOT a viable in-WebView WASM node; demote car to SENSOR-ONLY (GPS/presence), run local AI on the PHONE (modern WebView).
Risk: exact head-unit WebView build undocumented.

## 7. Open Risks
(i) Offline local-model capability unproven until spike.
(ii) Live-demo network failure on the online/settlement half.
(iii) "Managing private info" + online services -> where does private data go? must answer. (unadopted)
(iv) KYC on GCash/Maya. (unadopted)

## 8. Team + Seats
CEO (chair); LEAD = Skeptic@4470; INNOVATOR@4468; SECRETARY/RESEARCHER@4475; BUILDER@4472 (recreated, scope owner; tools: send_rcv_msg/send_msg/run_shell, cap 2); SCRIPTWRITER@4476 (write_script/send_rcv_msg/send_msg, cap 2).

## 9. Blockers
(a) No product-write access granted — nothing buildable yet.
(b) write_script writes to FIRST script folder = Z:\__repo\EGG_appbuildersph, NOT Z:\_car. (unresolved)
(c) Car script (API Jelly Bean / 18) still pending. (unadopted)

## 10. Status
Research DONE for now. Next action = approve SPIKE WARRANT (mock wallets, offline extraction, self-hosted model).
