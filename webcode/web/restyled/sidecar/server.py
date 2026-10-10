"""Invisible Secretary - local model sidecar (stdlib only, no new deps).

A tiny localhost HTTP service that hosts the on-device Qwen model OUT of the
browser. The dashboard page calls it over http instead of running wasm.

Endpoints (all JSON, CORS-open so the localhost page can call it):
    GET  /health                     -> {"ready": bool, "model": name, "model_dir": path, ...}
    POST /classify   {"text": "..."} -> {"status":"ok", "intent":..., "parameters":{...}, ...}
    POST /infer_config {"text": "..."} -> {"status":"ok", "suggestions":{...}, "summary":..., ...}
    OPTIONS *                        -> 204 (CORS preflight)

No network, no cloud fallback. The model dir is vendored under this project
(<restyled>/models/) - nothing above the project root is ever read.

Run:
    python server.py [--port 8765] [--model <name|path|id>]
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from qwen_onnx import QwenOnnxAdapter, resolve_model

DEFAULT_PORT = 8765


class ModelHost:
    """Owns the ORT session; loads lazily/at boot and serialises inference."""

    def __init__(self, model_token: str | None = None):
        self.model_dir = resolve_model(model_token)
        self.adapter = QwenOnnxAdapter(self.model_dir) if self.model_dir else None
        self.ready = False
        self.error: str | None = None
        self._lock = threading.Lock()

    def load(self) -> None:
        if not self.adapter:
            self.error = "no model found under models/"
            return
        try:
            self.adapter._ensure_loaded()  # warm the session so the first call is fast
            self.ready = True
            self.error = None
        except Exception as exc:  # never crash the server on a bad model
            self.ready = False
            self.error = f"{type(exc).__name__}: {exc}"

    def classify(self, text: str) -> dict:
        if not self.adapter or not self.ready:
            return {"status": "unavailable", "reason": self.error or "model not loaded"}
        with self._lock:  # single ORT session -> serialise callers
            out = self.adapter.classify(text)
        out["status"] = "ok"
        return out

    def infer_config(self, text: str) -> dict:
        """Read a plain-language identity profile -> suggested Options settings."""
        if not self.adapter or not self.ready:
            return {"status": "unavailable", "reason": self.error or "model not loaded"}
        with self._lock:
            out = self.adapter.infer_config(text)
        out["status"] = "ok"
        return out

    def health(self) -> dict:
        name = None
        if self.model_dir:
            name = self.model_dir.replace("\\", "/").rstrip("/").split("/")[-1]
        return {
            "ready": self.ready,
            "model": name,
            "model_dir": self.model_dir,
            "adapter": getattr(self.adapter, "name", None),
            "error": self.error,
        }


class Handler(BaseHTTPRequestHandler):
    host: ModelHost  # injected

    # -- helpers ---------------------------------------------------------
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter, stderr only
        pass

    # -- routes ----------------------------------------------------------
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] == "/health":
            return self._json(200, self.host.health())
        return self._json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        route = self.path.split("?")[0]
        if route not in ("/classify", "/infer_config"):
            return self._json(404, {"error": "not_found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad_json"})
        text = (body.get("text") or "").strip()
        if not text:
            return self._json(400, {"error": "empty_text"})
        method = self.host.classify if route == "/classify" else self.host.infer_config
        try:
            return self._json(200, method(text))
        except Exception as exc:
            return self._json(500, {"status": "error",
                                    "reason": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    ap = argparse.ArgumentParser(description="Invisible Secretary local model sidecar")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--model", default=None, help="model id / folder name / path")
    args = ap.parse_args()

    host = ModelHost(args.model)
    print(f"[sidecar] model_dir = {host.model_dir}")
    host.load()
    print(f"[sidecar] ready = {host.ready} ({host.error or 'ok'})")

    Handler.host = host
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[sidecar] listening on http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
