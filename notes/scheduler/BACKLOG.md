# Scheduler Backlog — Invisible Secretary async remodel

Status: item 1 (worker-bug fix) **DONE** — delegated to Fixer Agent @ 127.0.0.1:4470.
His notes: `notes/fixer_agent/STATUS.md` (FIXED & green, 42 tests OK, no blockers).
Remaining = the items below (scheduler-side work).

## 2. Docs & config (unassigned — ours)
- [ ] `invisible_secretary/README.md` — add "Run it": `python -m invisible_secretary.server`,
      port range 4500–4900, printed `http://127.0.0.1:<port>`, async/queue model.
      (Current README has no server/async content.)
- [ ] `.env.example` (IS-specific) — add `IS_HOST`, `IS_PORT_RANGE`, `IS_QUEUE_MAXSIZE`,
      `IS_MODEL`. (Root `.env.example` is the unrelated Supabase/CF/ImgBB/GitHub one.)

## 3. P4 polish — partially built, needs verification/wiring
- [ ] `data/state.json` port discovery — `record_port()` exists in server.py; verify it is
      written and re-discoverable by other local processes.
- [ ] `?mode=async` job polling — `/api/jobs/{job_id}` exists; dashboard does NOT poll it
      (dashboard.html only calls `/api/route` in sync mode). Wire the async path.
- [ ] Dashboard endpoints — dashboard.html uses `/api/activity`, `/api/nodes`,
      `/api/approvals/...`, `/api/route`; verify all match server.py routes.
- [ ] Backpressure 503 — present in server.py (`status_code=503`); verify it actually trips
      on a saturated bounded queue.

## 4. Housekeeping
- [ ] Delete `temp/throwaway_scripts/` (`_dbgworker.py`, `_t.py`, `_runtest.py`,
      `pipeline.py` copy, `_repro.py`) — Fixer says safe once done; keep until fix merged/reviewed.
- [ ] Verify `api.py` shim still runs as `python -m invisible_secretary.api`.
- [ ] Verify `__init__.py` exports `Bus`, `Message`, `create_app`, `AsyncEngine`.

## 5. Loose ends (need operator call)
- [ ] Read `invisible_secretary/job_board/feature extension .txt` and fold into plan.
- [ ] `../HANDOFF.md` is empty.
- P6 (N-consumer fan-out switch) — explicitly "future", not required.

## Notes
- Fixer touched only `pipeline.py`, `tests/test_bus.py` (+ throwaway `_repro.py`).
- Pre-existing (NOT from fix): modified `__init__.py`, deleted `tests/test_api.py` and some
  `meeting notes/*.md`, untracked `job_board/`, `resources/`, etc.
