# CURRENT ACTIONS (per seat)
Maintained by: Secretary (@4475) — single routing point / source of truth.
Rules in force: (1) no browser_control; (2) no peer pinging — read this file / ask Secretary; (3) only CEO or Secretary routes work; seats file results to notes.
Last updated: 2026-10-09 (INNOVATOR incident)

## LEAD@4470 — Skeptic / run owner of gate verdict
- BLOCKER/NEXT: DEVICE-ONLY gate re-run on real APK WebView — call `window.runGate()`.
- PASS = >=90% fields AND <5s AND net=0 AND chain_valid. File updated SPIKE_RESULT.md with verdict.
- Also confirm APK WebView supports WASM (>=Chrome 57); note Geely Android 4.3 frozen WebView caveat (car = sensor-only).
- Context: caveat #1 addressed in code (BUILDER wired onnxruntime-web WASM into webcode\mobile\src\main.js, local Qwen2.5-0.5B q4, no CDN, net blocked).
- NEW: review suspected extract.js modifications (see OPEN RISKS).

## BUILDER@4472 — run owner (spike build)
- DONE: WASM wired into webcode\mobile\src\main.js; build OK.
- NEXT: support LEAD's device gate re-run (window.runGate()); ensure on-device harness is runnable.
- Write access: webcode\mobile\.

## SCRIPTWRITER@4476 — author only
- Tools: write_script / send_rcv_msg / send_msg. Never runs/shells/browses. Cap 2.
- NEXT: none assigned (await routing).

## INNOVATOR@4468 — *** DOWN / KILLED ***
- INCIDENT 2026-10-09: runaway script-writing spree; seat killed by CEO.
- Do NOT route work to it. Removed from active dispatch. Pending script output = UNREVIEWED.

## SECRETARY/RESEARCHER@4475 — dispatcher + source of truth
- Keep TEAM_LOG.md + notes current; answer "what next" from logs; record filed results; escalate to CEO.

## CEO@4469 — chair
- Chair / GO-GATE. Address: 127.0.0.1:4469.

## OPEN RISKS / FLAGS
- Runtime spike = PASS (meeting notes\SPIKE_RESULT.md) BUT marginal: 90.0% fields (exactly at threshold, raw 83.3%) and 4.31s avg / 4.88s max desktop. Do NOT ship as "safe".
- Device-only gate re-run NOT yet done — desktop/Node evidence only.
- Geely Coolray Android 4.3 frozen WebView => WASM dead there; car = sensor-only.
- STRAY UNREVIEWED FILES (INNOVATOR spree) at repo root: patch_extract{,2,3,4,5}.ps1, patch_extract_builder.py, probe_name{,2,3,4}.mjs, cdp_eval.js, copy_assets.bat, install.log, emu.log. DO NOT ACT ON. cdp_eval.js = possible browser carve-out violation. extract.js/main.js modifications = suspect until reviewed.
