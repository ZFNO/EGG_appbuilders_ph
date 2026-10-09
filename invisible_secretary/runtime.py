"""Runtime wiring: assemble bus + engine + pipeline, and start worker tasks.

Kept in one place so ``server.py``, ``cli.py`` and tests build the same object
graph. Includes a thin ``AsyncEngine`` facade for programmatic async callers.
"""
from __future__ import annotations

import asyncio

from .bus import Bus
from .engine import Engine
from .factory import default_adapter
from .pipeline import PIPELINE, Context, Stage, worker


def build_engine(*, use_model: bool = True, model: str | None = None) -> Engine:
    return Engine(default_adapter(use_model=use_model, model=model))


def build_runtime(*, use_model: bool = True, model: str | None = None,
                  maxsize: int = 256) -> tuple[Bus, Context, Engine]:
    """Return (bus, context, engine) -- the spine and its shared state."""
    engine = build_engine(use_model=use_model, model=model)
    return Bus(maxsize), Context(engine), engine


def start_workers(bus: Bus, ctx: Context, *, stages: list[Stage] | None = None,
                  workers: int = 1,
                  stop: asyncio.Event | None = None) -> tuple[list[asyncio.Task], asyncio.Event]:
    """Spawn worker task(s) on the spine. Fan-out via ``workers`` (default 1)."""
    stages = stages or PIPELINE
    stop = stop or asyncio.Event()
    tasks = [asyncio.create_task(worker(bus, stages, ctx, stop=stop))
             for _ in range(max(1, workers))]
    return tasks, stop


class AsyncEngine:
    """Thin async facade over the sync engine (offloads each call to a thread)."""

    def __init__(self, engine: Engine):
        self._engine = engine

    async def process(self, request_id: str, text: str):
        return await asyncio.to_thread(self._engine.process, request_id, text)

    async def approve(self, approval_id: str, payload: dict | None = None):
        return await asyncio.to_thread(self._engine.approve, approval_id, payload)

    async def reject(self, approval_id: str):
        return await asyncio.to_thread(self._engine.reject, approval_id)
