"""Invisible Secretary - dashboard + JSON API (07_API_AND_IMPLEMENTATION_PLAN.md).

Stdlib-only, local, no external deps. Suggested internal interfaces preserved:
  POST /api/route, GET /api/activity, GET /api/nodes,
  POST /api/approvals/{id}/approve, POST /api/approvals/{id}/reject
All integrations are SIMULATED and labeled as such in the UI.
"""
from __future__ import annotations

import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import scope_store
from .engine import Engine
from .factory import default_adapter

HERE = Path(__file__).parent
ENGINE = Engine(default_adapter())


def boot(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Invisible Secretary dashboard: http://{host}:{port}/  (all integrations SIMULATED)")
    return server


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep the console quiet
        pass

    def _send(self, code: int, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (HERE / "dashboard.html").read_bytes(), "text/html")
        if self.path == "/api/activity":
            return self._send(200, [e.to_dict() for e in ENGINE.events.values()])
        if self.path == "/api/nodes":
            return self._send(200, [n.health() for n in ENGINE.nodes.values()])
        if self.path == "/scope":
            return self._send(200, (HERE / "scope.html").read_bytes(), "text/html")
        if self.path == "/api/scope":
            return self._send(200, scope_store.overview())
        return self._send(404, {"error": "not_found"})

    def do_POST(self):
        body = self._json_body()
        if self.path == "/api/scope":
            kws = body.get("out_of_scope_keywords", [])
            if not isinstance(kws, list):
                return self._send(400, {"error": "out_of_scope_keywords must be a list"})
            return self._send(200, scope_store.save(kws))
        if self.path == "/api/preview":
            return self._send(200, ENGINE.preview(body.get("text", "")))
        if self.path == "/api/route":
            rid = body.get("request_id") or f"req_{uuid.uuid4().hex[:8]}"
            text = body.get("text", "")
            ev = ENGINE.process(rid, text)
            return self._send(200, ev.to_dict())
        if self.path.startswith("/api/approvals/"):
            parts = self.path.strip("/").split("/")  # api, approvals, id, action
            if len(parts) != 4:
                return self._send(400, {"error": "bad_approval_path"})
            _, _, approval_id, action = parts
            try:
                if action == "approve":
                    ev = ENGINE.approve(approval_id)
                elif action == "reject":
                    ev = ENGINE.reject(approval_id)
                else:
                    return self._send(400, {"error": "bad_action"})
            except KeyError:
                return self._send(404, {"error": "unknown_approval"})
            except ValueError as exc:
                return self._send(409, {"error": str(exc)})
            return self._send(200, ev.to_dict())
        return self._send(404, {"error": "not_found"})


if __name__ == "__main__":
    boot().serve_forever()
