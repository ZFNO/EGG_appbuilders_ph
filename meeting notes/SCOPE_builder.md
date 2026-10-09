# BUILDER - Scope & Build Plan (v0, 20h deadline)

## Product (theme: LOCAL AI)
Offline on-device AI companion for EGG AppBuilders PH: semantic search + Q&A over bundled hackathon data (1270 participants / 678 teams). Runs entirely in the mobile web bundle inside the APK WebView. Zero network at inference.

## IN (MVP)
1. On-device runtime: Transformers.js (WASM/WebGPU) embeddings; (WebLLM CUT from MVP by Lead - WebGPU unreliable/latency unverified; post-MVP stretch only). [CONFIRMED by Researcher: Transformers.js WASM embeddings; MiniLM-class ~25-90MB quantized; WebView WebGPU unreliable. env.allowRemoteModels=false + localModelPath]
2. Precomputed embedding index for participants+teams, shipped as static asset.
3. One screen: query -> ranked answers/entities (semantic search), offline.
4. Ship via existing pipeline: mobile/ -> copy_to_apk.bat -> assets/ -> file:///android_asset/index.html.
5. Offline-proven on device (airplane mode).

## OUT
- Cloud/API AI, supabase/CF backends, auth/accounts.
- Desktop web parity, multi-screen nav, native Kotlin beyond WebView.
- Scraper/data expansion; live data.

## Hard gate (spike 0-2h)
Transformers.js embedding model MUST load OFFLINE from a SELF-HOSTED local asset (no CDN fetch) inside APK WebView, WASM path. If it fails -> replan.

## Build order
1. 0-2h  Spike: Transformers.js loads in WebView, embed 50-sample, prove offline.
2. 2-7h  Data pack: source = monitor\participants_flat.json (data/ empty); copy into mobile bundle; precompute embeddings (participants+teams), quantize, self-host asset.
3. 7-13h UI: search/answer screen in mobile web.
4. 13-17h APK integration + on-device test.
5. 17-20h Hardening, demo script, README.

## Ownership
- Builder: scope, integration, ship.
- Researcher: runtime feasibility (WebView/offline).
- Innovator: feature/UX.
- Lead (Skeptic): direction, verify.

## Definition of Done
APK installs; airplane mode ON; a natural-language query returns correct participant/team results with zero network calls; no crash; <5s/query; model NEVER touches network (no CDN); demo script + README updated.



