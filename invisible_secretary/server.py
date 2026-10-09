"""Async FastAPI server on an auto-selected port (4500-4900).

The server is a *producer*: each HTTP request is published onto the shared bus.
By default the handler awaits the reply future, preserving the old synchronous
response contract; ``?mode=async`` returns a job id instead. Binds the first
free port (bind-first, no check-then-bind race), prints it, and records it in
``data/state.json`` for local discovery.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .bus import Bus, Message
from .pipeline import Context
from .runtime import build_runtime, start_workers

HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parent
DEFAULT_RANGE = (4500, 4900)


def parse_range(spec: str) -> tuple[int, int]:
    lo, hi = spec.split("-")
    return int(lo), int(hi)


def bind_first_free(host: str, lo: int = DEFAULT_RANGE[0],
                    hi: int = DEFAULT_RANGE[1]) -> tuple[socket.socket, int]:
    """Bind the first free port in [lo, hi]; return (listening_socket, port)."""
    for port in range(lo, hi + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Windows SO_REUSEADDR allows re-binding an in-use port; use the
        # exclusive option there so bind-first truly detects a taken port.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            s.listen(1)
            return s, port
        except OSError:
            s.close()
    raise RuntimeError(f"no free port in {lo}-{hi}")


def record_port(port: int) -> None:
    """Best-effort publish of the chosen port for other local processes."""
    p = PROJECT_ROOT / "data" / "state.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        data["invisible_secretary"] = {"url": f"http://127.0.0.1:{port}", "port": port}
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def create_app(bus: Bus, ctx: Context, engine, *, workers: int = 1) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks, stop = start_workers(bus, ctx, workers=workers)
        try:
            yield
        finally:
            await bus.join()
            stop.set()
            for t in tasks:
                t.cancel()

    app = FastAPI(title="Invisible Secretary", lifespan=lifespan)

    async def _submit(msg: Message, *, wait: bool):
        if bus.full() and not wait:
            raise HTTPException(status_code=503, detail="queue saturated; retry")
        if wait:
            msg.replies = asyncio.get_running_loop().create_future()
        await bus.publish(msg)
        if not wait:
            return {"job_id": msg.id, "state": "accepted"}
        try:
            return await msg.replies
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return (HERE / "dashboard.html").read_text(encoding="utf-8")

    @app.get("/guide", response_class=HTMLResponse)
    async def guide():
        return (HERE / "guide.html").read_text(encoding="utf-8")

    @app.get("/api/model")
    async def model_info():
        return engine.router.model.describe()

    @app.post("/api/route")
    async def route(body: dict | None = None, mode: str = "sync"):
        body = body or {}
        kwargs = {"id": body["request_id"]} if body.get("request_id") else {}
        msg = Message(kind="secretary.request",
                      payload={"text": body.get("text", "")}, source="http", **kwargs)
        return await _submit(msg, wait=(mode != "async"))

    @app.post("/api/approvals/{approval_id}/{action}")
    async def approvals(approval_id: str, action: str, body: dict | None = None):
        if action not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="bad_action")
        payload: dict = {"approval_id": approval_id}
        if action == "approve" and body and "payload" in body:
            payload["payload"] = body["payload"]
        kind = "secretary.approve" if action == "approve" else "secretary.reject"
        return await _submit(Message(kind=kind, payload=payload, source="http"), wait=True)

    @app.get("/api/activity")
    async def activity():
        return [e.to_dict() for e in engine.events.values()]

    @app.get("/api/nodes")
    async def nodes():
        return [n.health() for n in engine.nodes.values()]

    @app.get("/api/jobs/{job_id}")
    async def job(job_id: str):
        ev = engine.events.get(job_id)
        if ev is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return ev.to_dict()

    return app


def main(host: str | None = None) -> None:
    host = host or os.environ.get("IS_HOST", "127.0.0.1")
    lo, hi = parse_range(os.environ.get("IS_PORT_RANGE", "4500-4900"))
    maxsize = int(os.environ.get("IS_QUEUE_MAXSIZE", "256"))
    workers = int(os.environ.get("IS_WORKERS", "1"))
    model = os.environ.get("IS_MODEL") or None
    use_model = os.environ.get("IS_NO_MODEL") not in ("1", "true", "True")

    bus, ctx, engine = build_runtime(use_model=use_model, model=model, maxsize=maxsize)
    app = create_app(bus, ctx, engine, workers=workers)

    info = engine.router.model.describe()
    sock, port = bind_first_free(host, lo, hi)
    record_port(port)
    print(f"Invisible Secretary listening on http://{host}:{port}/  "
          f"(all integrations SIMULATED; queue={maxsize}, workers={workers})", flush=True)
    if info["mode"] == "rules+model":
        print(f"model: {info['model']}  [{info['adapter']}]", flush=True)
        print(f"model path: {info['path']}", flush=True)
    else:
        print(f"model: none  -> rules only ({info['reason']})", flush=True)

    import uvicorn
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
