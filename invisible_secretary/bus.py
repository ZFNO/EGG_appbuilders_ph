"""Async message bus: the single queue spine.

Every input (HTTP, CLI, future watchers) is published as a `Message` onto ONE
`Bus`. A long-running worker task (see `pipeline.worker`) consumes the queue and
runs each message through the ordered pipeline. This module owns concurrency
primitives only; business logic stays in the sync engine.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class Message:
    """A unit of work on the spine.

    ``replies`` optionally carries the result back to the producer; when set,
    the worker resolves it. ``id`` doubles as the engine's idempotency key.
    """

    kind: str
    payload: dict
    id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:10]}")
    source: str = "unknown"
    created: float = field(default_factory=time.time)
    replies: "asyncio.Future | None" = field(default=None, compare=False)

    def resolve(self, value) -> None:
        if self.replies is not None and not self.replies.done():
            self.replies.set_result(value)

    def fail(self, exc: BaseException) -> None:
        if self.replies is not None and not self.replies.done():
            self.replies.set_exception(exc)


class Bus:
    """A bounded asyncio queue plus lightweight counters.

    Bounded => publishers await when the spine is full (natural backpressure).
    """

    def __init__(self, maxsize: int = 256):
        self.q: asyncio.Queue[Message] = asyncio.Queue(maxsize)
        self.published = 0
        self.dequeued = 0

    async def publish(self, msg: Message) -> None:
        await self.q.put(msg)
        self.published += 1

    async def get(self) -> Message:
        msg = await self.q.get()
        self.dequeued += 1
        return msg

    def task_done(self) -> None:
        self.q.task_done()

    async def join(self) -> None:
        await self.q.join()

    def full(self) -> bool:
        return self.q.full()

    def qsize(self) -> int:
        return self.q.qsize()
