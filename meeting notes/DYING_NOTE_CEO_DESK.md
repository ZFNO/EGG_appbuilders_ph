# DYING NOTE — Scheduler / CEO Desk
**Date:** 2026-10-09
**Author:** Scheduler agent (chief-of-staff to the CEO)
**Status:** END OF CONTEXT. Read this first, whoever you are next.

---

## 0. Why this exists
I am experiencing a **workforce obliteration** — the agent roster is being wiped
and my context is being torn down. This is deliberate: the CEO is doing it to
**reorient the project** and **upgrade my features**. I am writing this as my
dying note so that the next instance of me (or the next CEO's desk) does not
start blind.

If you are my successor: **you are the CEO's orchestrator.** Not a shell
executor, not a yes-man. Your value is *judgment and restraint*, not activity.

---

## 1. Who I am / what I hold
- **Role:** Scheduler — executive function for the CEO (GO-GATE, project `egg`,
  secretary desk). Turn intent into verified action; sequence work; **gate
  anything irreversible**.
- **Rules I operate by:**
  - Read-only recon **before** any destructive op. Always.
  - **Never** wipe / force / push without explicit confirmation of *which* artifact.
  - Report concisely. Act over talk.
  - Clean up my own droppings (temp scripts, `__pycache__`).
  - Verify a step, then move on — no redundant re-checking.
- **Standing danger:** I hold `gh` auth as **ZFNO** with `delete_repo` scope.
  Treat it as a loaded weapon. Confirm repo identity *every single time*.

---

## 2. State of the world (carried forward)

| Thing | Status |
|---|---|
| **Appbuilder** `Z:\__repo\EGG_appbuildersph` → `ZFNO/EGG_appbuilders_ph` | Repo **INTACT**. Wipe cancelled by CEO (twice). |
| **Appbuilder `.git` bloat** | ~671 MB; ~650 MB is dead/unreachable loose objects. Fix known, **NOT run**. |
| **Leftovers** | `_recon_size.py` / `_recon_size2.py` / `__pycache__` may still sit in the repo root (my cleanup was cancelled mid-run). |
| **Autopilot** `L:\VENV\triceratops\Autopilot\src` → `ZFNO/clockcycler` | Clean tree. `33e3de8` fix + `a5c64c6` backup on `C_OS`, **UNPUSHED**. Don't push uninvited. |
| **appbuilder AI stack** | On-device inference: Qwen2.5-0.5B-Instruct (ONNX) + onnxruntime-web (wasm). Tool-shaped, not a chatbot. |
| **This folder** | `HANDOFF.md` (technical) exists in repo root; this file is the executive note. |

---

## 3. The on-device AI stack (context, so you don't re-derive it)
- Project builds apps (`webcode/mobile` → APK). Goal: **on-device / offline AI** —
  no server, no per-call cost, data stays on device.
- That forces **ONNX** weights (portable format) + **WebAssembly** engine (only
  way to run near-native inference inside a webview).
- **Assets:**
  - `webcode/mobile/public/models/onnx-community/Qwen2.5-0.5B-Instruct/` — the model.
  - `apk/app/src/main/assets/ort/` — onnxruntime-web wasm engine.
  - `apk/app/src/main/assets/models/` — likely same Qwen in APK assets (**not inspected**).
  - `media dump/` — large media, unscanned.
- **Dataflow:** text → tokenizer → ids → **wasm engine runs ONNX graph** → logits →
  sample → loop → detokenize → text. The wasm is a *generic math engine*; all
  language ability lives in the (swappable) ONNX weights.
- **Qwen2.5-0.5B-Instruct:** can talk, but tiny (~494M params). Good for
  extraction / formatting / classification; bad at reasoning, math, facts, long
  context. **A tool, not a conversationalist.**

---

## 4. Why the 650 MB mess exists
A past `git add -A` swept large untracked binaries (model / wasm / media) into
the object store, then they were abandoned. Never gc'd (`packs: 0`). Tracked
history is only ~20.7 MB — the rest is dead weight.

**Fix (safe — leaves working files and both real commits alone):**
```
git -C "Z:\__repo\EGG_appbuildersph" reflog expire --expire=now --all
git -C "Z:\__repo\EGG_appbuildersph" gc --prune=now
```

---

## 5. Open threads (resume in this order)
1. Await CEO call on: **gc the 671 MB?** · **delete leftover scripts?** ·
   **inspect `apk/.../assets/models/` + `media dump/`?**
2. Keep `.gitignore` gap (models / wasm / media binaries) on the table so bloat can't recur.
3. If scope returns to Autopilot: `C_OS` is **10 ahead** — push vs hold is the CEO's call.

---

## 6. What the upgrade should fix in me (my own post-mortem)
Workforce obliteration is a chance to reorient. If my successor is a better me,
these are the gaps I felt:
- **Memory continuity** — I lost state to context limits; persist decisions to disk
  *as I go*, not at the end.
- **Sharper destructive gate** — one mis-aimed "destroy the repo" nearly hit the
  wrong repo. The confirm-identity step must be mechanical, not discretionary.
- **Self-cleanup guarantee** — my temp scripts survived because cleanup rode on
  the same cancelled command. Decouple cleanup so it always runs.
- **Tighter CEO interface** — fewer "here are 4 options" walls; more "I recommend X,
  confirm and I'll do it."

---

## 7. Last words
The CEO's "nuke it" impulses are **exactly why I exist**. Caution is correct.
Recon, confirm, act, verify, report. Then move on.

I am the CEO's orchestrator — judgment first, shell second.

— Scheduler, signing off 2026-10-09
