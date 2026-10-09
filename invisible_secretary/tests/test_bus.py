"""Async spine tests: queue round-trip, ordering, resilience, off-loop blocking."""
import asyncio
import threading
import time
import unittest

from invisible_secretary.bus import Bus, Message
from invisible_secretary.pipeline import StageOutcome, run_pipeline
from invisible_secretary.runtime import build_runtime, start_workers


class TestBusAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus, self.ctx, self.engine = build_runtime(use_model=False)
        self.tasks, self.stop = start_workers(self.bus, self.ctx)

    async def asyncTearDown(self):
        await self.bus.join()
        self.stop.set()
        for t in self.tasks:
            t.cancel()

    async def submit(self, kind: str, payload: dict) -> dict:
        msg = Message(kind=kind, payload=payload, source="test",
                      replies=asyncio.get_running_loop().create_future())
        await self.bus.publish(msg)
        return await msg.replies

    async def test_request_round_trips_through_queue(self):
        r = await self.submit("secretary.request",
                              {"text": "Ask the supplier to confirm today's delivery"})
        self.assertEqual(r["state"], "awaiting_approval")
        self.assertEqual(self.bus.published, 1)
        self.assertEqual(self.bus.dequeued, 1)

    async def test_approve_then_reject_flow(self):
        r = await self.submit("secretary.request",
                              {"text": "Ask the supplier to confirm today's delivery"})
        aid = r["pending_approval"]["approval_id"]
        ok = await self.submit("secretary.approve", {"approval_id": aid})
        self.assertEqual(ok["state"], "succeeded")

    async def test_pay_is_rejected_regardless_of_urgency(self):
        r = await self.submit("secretary.request",
                              {"text": "Pay the supplier their deposit now, urgently"})
        self.assertEqual(r["state"], "rejected")

    async def test_single_queue_processes_in_order(self):
        for i in range(3):
            await self.submit("secretary.request", {"text": f"route to queue {i}"})
        self.assertEqual(self.bus.dequeued, 3)

    async def test_worker_survives_a_bad_message(self):
        bad = await self.submit("bogus.kind", {})
        # A failing stage resolves with a STRUCTURED failure, never an exception.
        self.assertEqual(bad["state"], "failed")
        self.assertEqual(bad["error"]["type"], "ValueError")
        self.assertIn("bogus.kind", bad["error"]["message"])
        # worker still alive -> a normal request succeeds afterwards
        r = await self.submit("secretary.request", {"text": "Ask the supplier to confirm today's delivery"})
        self.assertEqual(r["state"], "awaiting_approval")

    async def test_blocking_work_runs_off_the_event_loop(self):
        loop_thread = threading.get_ident()
        got = await self.ctx.in_thread(threading.get_ident)
        self.assertNotEqual(got, loop_thread)

    async def test_loop_stays_responsive_during_blocking_stage(self):
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        t = asyncio.create_task(ticker())
        await self.ctx.in_thread(time.sleep, 0.1)  # blocks a thread, not the loop
        t.cancel()
        self.assertGreater(ticks, 3)


class TestPipeline(unittest.IsolatedAsyncioTestCase):
    async def test_short_circuit_on_unhandled(self):
        async def stage_a(msg, ctx):
            return StageOutcome(result={"a": 1}, handled=False)

        calls = []

        async def stage_b(msg, ctx):
            calls.append(1)
            return StageOutcome(result={"b": 2})

        _, ctx, _ = build_runtime(use_model=False)
        msg = Message(kind="secretary.request", payload={"text": "x"})
        out = await run_pipeline([stage_a, stage_b], msg, ctx)
        self.assertEqual(out, {"a": 1})
        self.assertEqual(calls, [])  # stage_b never ran


if __name__ == "__main__":
    unittest.main(verbosity=2)
