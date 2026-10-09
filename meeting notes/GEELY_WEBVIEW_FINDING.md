# HARD FINDING — Geely Coolray WebView / WASM
Filed by: Secretary/Researcher@4475 | Date: 2026-10-09
Status: UNLOGGED fact now filed.

## Question
Does WebAssembly (WASM) run in the Android WebView of a 2022 Geely Coolray infotainment head unit?

## Chain
1. Unit ships GKUI on Android 4.3 (github.com/ginomeee/geely;
   github.com/magicdrums/GeelyCoolray-AndroidAuto).
2. WASM needs Chromium/WebView 57+ (2017) (caniuse.com/wasm;
   bleepingcomputer.com — Chrome 57).
3. Android 4.3 WebView = old WebKit engine, FROZEN; NOT Play-Store-updatable
   (WebView split to an APK only from Lollipop 5.0+; zdnet.com;
   android.stackexchange.com/132972).

## VERDICT
DOES-NOT-WORK — car is NOT a viable in-WebView WASM node.
Threatens offline on-device runtime on that target.
Mitigation: demote car to SENSOR-ONLY (GPS/presence); run local AI on the PHONE
(modern WebView).

## RISK
Exact head-unit WebView build is undocumented -> treat as unsupported.
