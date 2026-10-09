# Fixer Agent — invisible_secretary async-pipeline defect

## Status: FIXED & green

## What changed

### 1) `invisible_secretary/pipeline.py` — clean final build (debug scaffolding removed)
Worker is now bulletproof; a failing stage can never kill it:

- New helper `failure_payload(exc)` -> `{"state": "failed", "error": {"type": ..., "message": ...}}`.
- New helper `_run_one(bus, stages, ctx)` dequeues exactly one message and:
  - inner `try/except Exception` -> resolves the reply future with the STRUCTURED
    payload. It NEVER calls `msg.fail()` / `set_exception` on the future.
  - strips the traceback (`exc.__traceback__ = None`) BEFORE the payload/exception
    is handed off, so no frame of the worker coroutine is reachable from anything a
    caller (e.g. `unittest.assertRaises` -> `with_traceback(None)` / frame clearing)
    can close. That frame-clearing is what delivered `GeneratorExit` at the next
    `await bus.get()` and killed the single worker.
  - `finally: bus.task_done()` keeps the queue's join() bookkeeping correct.
- `worker(...)` keeps the `while not stop.is_set()` loop and ADDS a defensive outer
  guard: `except asyncio.CancelledError: break` (shutdown-by-cancel) and
  `except BaseException` -> log + `await asyncio.sleep(0)` + continue. Nothing can
  escape the loop.
- Timeout-poll removal retained: plain `await bus.get()` (no `wait_for`).
- No debug prints (`=== escaping worker exception ===` gone); module docstring is clean.

### 2) `invisible_secretary/tests/test_bus.py::TestBusAsync::test_worker_survives_a_bad_message`
- Dropped `assertRaises(ValueError)`.
- Now asserts the STRUCTURED failure: `state == "failed"`,
  `error.type == "ValueError"`, `'bogus.kind'` in `error.message`.
- Then asserts a following `secretary.request` resolves `state == "awaiting_approval"`
  (proves the worker is still consuming).

### 3) `temp/throwaway_scripts/_repro.py` (throwaway, updated to the new contract)
Previously reproduced the hang; now asserts the fixed behaviour so it doubles as a
standalone regression check: bad msg -> structured failure, `tasks[0].done() is False`,
next good msg -> `awaiting_approval`.

## Commands run & results

- Pre-fix repro: `python temp/throwaway_scripts/_repro.py`
  -> **HANGS**; stderr shows `=== escaping worker exception ===` + `GeneratorExit`
     at `pipeline.py ... await bus.get()` (bug confirmed).
- Post-fix repro: same command
  -> `bad -> {'state': 'failed', 'error': {'type': 'ValueError', 'message': "unknown message kind 'bogus.kind'"}}`
     `after bad, worker done? False`
     `second: awaiting_approval`
     `OK: worker survived, later message handled`  (exit 0)
- Full suite: `python -m unittest discover -s invisible_secretary/tests -v`
  -> **Ran 42 tests ... OK** (0.256s for test_bus alone; 17.7s total).
     Server tests `test_server.py` 6/6 green. `test_bus` 8/8 green.

## Acceptance check
- Bad message -> structured failure, worker keeps consuming: **YES**
- Subsequent good message resolves with a state: **YES**
- No `cannot reuse already awaited coroutine`, no `GeneratorExit`, no hang: **YES**
- Full suite green: **YES** (42 OK)

## Blockers
None.

## Notes / hygiene
- Only files under `Z:\__repo\egg` were touched. No browser control used. No messages sent.
- Temp helper scripts created during investigation were deleted; `temp/throwaway_scripts/`
  still holds the pre-existing throwaway debug files (`_dbgworker.py`, `_t.py`,
  `_runtest.py`, and the old `pipeline.py` copy) plus the updated `_repro.py`.
  Safe to delete the whole `temp/throwaway_scripts/` folder if not wanted.

## Repo working-tree note (pre-existing, NOT from this fix)
`git status` also shows unrelated pre-existing changes I did NOT touch: modified `invisible_secretary/__init__.py`, deleted `invisible_secretary/tests/test_api.py` and several `meeting notes/*.md`, plus untracked `job_board/`, `resources/`, etc. Only `invisible_secretary/pipeline.py`, `invisible_secretary/tests/test_bus.py`, `temp/throwaway_scripts/_repro.py` and `notes/fixer_agent/STATUS.md` were written by this fix.

----
## Commit & push — 2026-10-10
- Commit 3480dd1 on branch secretary: "async remodel of invisible_secretary + bulletproof bus worker" (50 files, +1999/-505).
- Pushed to origin: b25bcbe..3480dd1  secretary -> secretary  (https://github.com/ZFNO/EGG_appbuilders_ph.git).
- Includes the pipeline worker fix + updated test_bus.py + this STATUS.md.
- Left untracked/uncommitted: temp/ (throwaway) and invisible_secretary/scope_store.py (appeared after staging).
