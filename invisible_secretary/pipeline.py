"""Processing pipeline: ordered stages run by the bus worker.

Each :class:`Message` flows through the ordered ``stages``; the first stage that
produces a result wins and ``handled=False`` short-circuits the rest. The worker
is the single consumer of the :class:`~invisible_secretary.bus.Bus` and MUST be
unkillable by a bad message: a failing stage resolves its reply future with a
*structured* failure payload (never ``set_exception``), so no traceback -- and no
reference to the worker frame -- ever escapes the loop.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .bus import Bus, Message
from .engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class StageOutcome:
    result: dict | None = None
    handled: bool = True
    meta: dict = field(default_factory=dict)


class Context:
    def __init__(self, engine: Engine):
        self.engine = engine

    async def in_thread(self, fn: Callable[..., Any], *args: Any, **kw: Any):
        return await asyncio.to_thread(fn, *args, **kw)


class Stage(Protocol):
    name: str

    async def __call__(self, msg: Message, ctx: Context) -> StageOutcome:
        ...


async def secretary_stage(msg: Message, ctx: Context) -> StageOutcome:
    eng = ctx.engine
    if msg.kind == "secretary.request":
        ev = await ctx.in_thread(eng.process, msg.id, msg.payload.get("text", ""))
    elif msg.kind == "secretary.approve":
        ev = await ctx.in_thread(eng.approve, msg.payload["approval_id"],
                                 msg.payload.get("payload"))
    elif msg.kind == "secretary.reject":
        ev = await ctx.in_thread(eng.reject, msg.payload["approval_id"])
    else:
        raise ValueError(f"unknown message kind {msg.kind!r}")
    return StageOutcome(result=ev.to_dict())


secretary_stage.name = "secretary"  # type: ignore[attr-defined]

PIPELINE: list[Stage] = [secretary_stage]
STAGE_REGISTRY: dict[str, Stage] = {secretary_stage.name: secretary_stage}  # type: ignore[attr-defined]


async def run_pipeline(stages: list[Stage], msg: Message, ctx: Context) -> dict | None:
    result: dict | None = None
    for stage in stages:
        outcome = await stage(msg, ctx)
        if outcome.result is not None:
            result = outcome.result
        if not outcome.handled:
            break
    return result


def failure_payload(exc: BaseException) -> dict:
    """Structured, JSON-serialisable failure for a stage that raised."""
    return {
        "state": "failed",
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
    }


async def _run_one(bus: Bus, stages: list[Stage], ctx: Context) -> None:
    """Dequeue and process exactly one message; never raises for a bad message."""
    msg = await bus.get()
    try:
        try:
            result = await run_pipeline(stages, msg, ctx)
        except Exception as exc:  # a failing stage must not kill the worker
            payload = failure_payload(exc)
            # Drop the traceback *before* the object is handed anywhere else:
            # a live traceback holds a frame of THIS coroutine, and a caller
            # that clears frames (e.g. unittest.assertRaises) would otherwise
            # close that frame and deliver GeneratorExit here, killing us.
            exc.__traceback__ = None
            msg.resolve(payload)
        else:
            msg.resolve(result)
    finally:
        bus.task_done()


async def worker(bus: Bus, stages: list[Stage], ctx: Context, *,
                 stop: asyncio.Event) -> None:
    """Single consumer of the bus.

    Bullet-proof: a failing stage is turned into a structured reply, and a
    defensive outer guard ensures nothing can escape the loop and strand later
    messages. Shutdown is by cancelling the task (``CancelledError`` ends it).
    """
    while not stop.is_set():
        try:
            await _run_one(bus, stages, ctx)
        except asyncio.CancelledError:
            # Cooperative shutdown: task cancelled -> exit the loop.
            break
        except BaseException as exc:  # noqa: BLE001 - defensive by design
            # Nothing -- bad payloads, traceback-clearing callers, stray
            # GeneratorExit -- may kill the worker. Log and keep consuming.
            logger.warning("worker guard swallowed %r; continuing",
                           exc, exc_info=True)
            await asyncio.sleep(0)
