# BUILDER - 20h Scope: coolray_receipt_demo.html (car = SENSOR-ONLY)

IN: on-phone offline local-model extraction (name/amount/date -> receipt); ES5 single-file self-contained; self-hosted wllama/Transformers.js (no CDN); wallets + RAG = MOCKS; receipts hash/append-log only; airplane-mode.
OUT: Ollama, on-chain, real payments, CDN/network, login, persistence.
EFFORT: extraction+RAG 6h | wallet mocks 4h | receipt/log 3h | ES5 UI 5h | offline verify 2h.
SPIKE (~4h): phone-local extraction -> one receipt. PASS: >=90% fields, <5s, AIRPLANE MODE, zero network.
Target: webcode/mobile/. WRITE GRANTED; SCRIPTWRITER unblocked (GO sent).
