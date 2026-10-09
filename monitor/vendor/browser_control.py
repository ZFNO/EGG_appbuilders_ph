#!/usr/bin/env python3
"""
browser_control.py - single-file browser control for agents.

WHAT THIS IS
------------
One self-contained script that does THREE jobs that used to be separate files:

  1. BRIDGE  - a local HTTP+WebSocket server (aiohttp) that relays commands to a
               browser extension. Runs in a background thread, in-process.
  2. TOOL    - the agent-facing surface (send / feed / run_js / fetch / ...).
               Every call returns {"ok": True, "data": ...} or
               {"ok": False, "error": ..., "code": ...} and never raises for
               ordinary failures, so it is safe to call from an LLM loop.
  3. LAUNCHER- if no bridge is running it starts one; if the browser+extension
               are not up it launches Edge with the unpacked extension. So an
               agent can just do:  bc = BrowserControl.get()

QUICK START
-----------
    from browser_control import BrowserControl
    bc = BrowserControl.get()                 # starts bridge + browser if needed
    bc.fetch("https://httpbin.org/get")["data"]
    tab = bc.open_tab("https://example.com", wait_ms=2500)["data"]
    bc.run_js("() => document.title", tab_id=tab["tab_id"])["data"]["result"]

    # FULL ACCESS: feed ANY extension command with ANY args, unfiltered:
    bc.send("extract", {"tabId": tab["tab_id"], "fn": "d => d.querySelectorAll('a').length"})

CLI
---
    python browser_control.py up                 # start bridge + browser, print status
    python browser_control.py status
    python browser_control.py js "() => document.title" --tab 123
    python browser_control.py fetch https://example.com
    python browser_control.py send get_cookies --args "{\"url\":\"https://x.com\"}"
    python browser_control.py down               # stop the in-process bridge (if we own it)

Defaults are overridable by env vars:
    BROWSERAPI_EXT_DIR   path to unpacked extension (default L:\\browserextensions\\browserapi\\extension)
    BROWSERAPI_PROFILE   browser profile dir       (default <temp>\\_browsercontrol_profile)
    BROWSERAPI_BROWSER   browser exe               (default Microsoft Edge)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any

# ----------------------------------------------------------------------------
# constants
# ----------------------------------------------------------------------------
PORT_RANGE = (6500, 7500)
BRIDGE_ID = "browserapi"
DEFAULT_TIMEOUT = 30.0
PORT_FILE = os.path.join(tempfile.gettempdir(), "_browsercontrol_port")

def _read_port_file():
    try:
        with open(PORT_FILE, encoding='utf-8') as f:
            return int(f.read().strip())
    except Exception:
        return None

def _write_port_file(p):
    try:
        with open(PORT_FILE, 'w', encoding='utf-8') as f:
            f.write(str(p))
    except Exception:
        pass

OK = "OK"
NOT_FOUND = "NOT_FOUND"
NOT_CONNECTED = "NOT_CONNECTED"
TIMEOUT = "TIMEOUT"
HTTP_ERROR = "HTTP_ERROR"
BAD_ARGS = "BAD_ARGS"
ERROR = "ERROR"

DEFAULT_EXT_DIR = r"L:\browserextensions\browserapi\extension"
DEFAULT_BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _env(n, d):
    return os.environ.get(n) or d


# In-page JS that returns visible text (scripts/styles/hidden removed) so we
# never pull a 500KB HTML blob across the bridge.
_READABLE_JS = r"""
(function(sel, maxChars) {
  var root = sel ? document.querySelector(sel) : document.body;
  if (!root) return { __bapi_error: "selector not found: " + sel };
  var clone = root.cloneNode(true);
  clone.querySelectorAll("script,style,noscript,svg,iframe,template,head").forEach(function(e){e.remove();});
  var text = (clone.innerText || clone.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
  var truncated = false;
  if (maxChars && text.length > maxChars) { text = text.slice(0, maxChars); truncated = true; }
  return { text: text, length: text.length, truncated: truncated };
})
"""


def _as_fn(code: str) -> str:
    """Return JS source the extension's evaluator can run.

    The extension does new Function('return (' + fn + ');')(), and if the result
    is a function it calls it with `document`. So arrow/function sources pass
    through untouched, while a bare expression like 'document.title' is wrapped
    as '() => (expr)' so it evaluates to the expression's value.
    """
    s = (code or "").strip()
    if not s:
        return s
    looks_like_fn = (
        s.startswith("(") or s.startswith("function") or s.startswith("async")
        or "=>" in s
    )
    return s if looks_like_fn else "() => (" + s + ")"


# ============================================================================
# PART 1 - the bridge (aiohttp server)
# ============================================================================
def pick_free_port(lo: int, hi: int) -> int:
    for p in range(lo, hi + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError(f"no free port in {lo}-{hi}")


class Bridge:
    """Relays HTTP /cmd calls to the extension over a WebSocket the extension
    dials OUT to. One extension connection at a time."""

    def __init__(self) -> None:
        self.ext_ws = None
        self.pending: dict = {}
        self.seq = 0
        self.connected_at: float | None = None

    async def ws_handler(self, request):
        from aiohttp import web, WSMsgType
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        role = request.query.get("role", "unknown")
        if role != "extension":
            await ws.close()
            return ws
        self.ext_ws = ws
        self.connected_at = time.time()
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    self._on_ext_message(msg.data)
        finally:
            self.ext_ws = None
            self.connected_at = None
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("extension disconnected"))
            self.pending.clear()
        return ws

    def _on_ext_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        mtype = msg.get("type")
        if mtype == "result":
            fut = self.pending.pop(msg.get("id"), None)
            if fut and not fut.done():
                if msg.get("ok", False):
                    fut.set_result({k: v for k, v in msg.items() if k not in ("type", "id", "ok")})
                else:
                    fut.set_exception(RuntimeError(msg.get("error", "extension error")))
        # 'hello' / 'ping' are informational

    async def dispatch(self, cmd: str, args: dict | None = None, timeout: float = 30.0) -> Any:
        if self.ext_ws is None or self.ext_ws.closed:
            raise RuntimeError("extension not connected")
        self.seq += 1
        req_id = f"r{self.seq}"
        fut = asyncio.get_event_loop().create_future()
        self.pending[req_id] = fut
        await self.ext_ws.send_str(json.dumps({"id": req_id, "cmd": cmd, "args": args or {}}))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self.pending.pop(req_id, None)
            raise RuntimeError(f"timeout after {timeout}s waiting for '{cmd}'")

    async def http_ping(self, _req):
        from aiohttp import web
        return web.json_response({
            "bridge": BRIDGE_ID, "status": "ok",
            "extension_connected": self.ext_ws is not None and not self.ext_ws.closed,
            "connected_for": round(time.time() - self.connected_at, 1) if self.connected_at else None,
        })

    async def http_cmd(self, req):
        from aiohttp import web
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
        cmd = body.get("cmd")
        args = body.get("args", {})
        timeout = float(body.get("timeout", 30))
        if not cmd:
            return web.json_response({"ok": False, "error": "cmd required"}, status=400)
        try:
            result = await self.dispatch(cmd, args, timeout)
            return web.json_response({"ok": True, "cmd": cmd, "result": result})
        except Exception as e:
            return web.json_response({"ok": False, "cmd": cmd, "error": str(e)}, status=502)

    def make_app(self):
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/ping", self.http_ping)
        app.router.add_post("/cmd", self.http_cmd)
        app.router.add_get("/ws", self.ws_handler)
        return app


class _BridgeThread:
    """Runs the aiohttp bridge in its own thread + event loop."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.bridge = Bridge()
        self._loop = None
        self._thread = None
        self._ready = threading.Event()

    def start(self, timeout: float = 5.0) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("bridge thread failed to start")

    def _run(self) -> None:
        from aiohttp import web
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _boot():
            runner = web.AppRunner(self.bridge.make_app())
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", self.port)
            await site.start()
            self._ready.set()
            while True:
                await asyncio.sleep(3600)

        try:
            self._loop.run_until_complete(_boot())
        except Exception:
            self._ready.set()

    def stop(self) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)


# ============================================================================
# PART 2 + 3 - BrowserControl: the tool + launcher
# ============================================================================
def ok(data: Any, **meta: Any) -> dict:
    d = {"ok": True, "data": data}
    if meta:
        d["meta"] = meta
    return d


def err(message: str, code: str = ERROR) -> dict:
    return {"ok": False, "error": message, "code": code}


class BrowserControl:
    """One instance == one bridge port. Use .get() for a ready-to-go instance."""

    def __init__(self, port: int) -> None:
        self.port = int(port)
        self.base = f"http://127.0.0.1:{self.port}"

    # ------------------------------------------------------------------ bootstrap
    @classmethod
    def get(cls, *, start: bool = True, launch_browser: bool = True,
            timeout: float = 30.0, port: int | None = None) -> "BrowserControl":
        """Return a control object wired to a running bridge + browser.

        If no bridge is running, start one in-process (unless start=False).
        If launch_browser and the extension is not connected, launch the browser
        with the unpacked extension and wait for it to dial in.
        Raises RuntimeError only if it truly cannot get ready.
        """
        inst = None
        try:
            inst = cls.discover()
        except RuntimeError:
            if not start:
                raise
            p = port or pick_free_port(*PORT_RANGE)
            t = _BridgeThread(p)
            t.start()
            _write_port_file(p)
            inst = cls(p)
            inst._thread = t  # we own it -> can stop() it

        if launch_browser:
            inst.ensure_browser(timeout=timeout)
        return inst

    @classmethod
    def _ping_port(cls, p):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{p}/ping', timeout=0.5) as r:
                return json.loads(r.read()).get('bridge') == BRIDGE_ID
        except Exception:
            return False

    @classmethod
    def discover(cls, lo=PORT_RANGE[0], hi=PORT_RANGE[1]):
        '''Find the bridge WITHOUT scanning 1000 ports (slow/flaky on Windows).\n        Order: recorded port-file -> default port -> optional bounded scan.'''
        p = _read_port_file()
        if p and cls._ping_port(p):
            return cls(p)
        if lo <= PORT_RANGE[0] <= hi and cls._ping_port(PORT_RANGE[0]):
            return cls(PORT_RANGE[0])
        if hi > PORT_RANGE[0] + 1:
            for q in range(lo, hi + 1):
                if cls._ping_port(q):
                    return cls(q)
        raise RuntimeError('no browserapi bridge found (is it running?)')

    # ------------------------------------------------------------------ launcher
    def _extension_connected(self) -> bool:
        try:
            with urllib.request.urlopen(self.base + "/ping", timeout=1.0) as r:
                return bool(json.loads(r.read()).get("extension_connected"))
        except Exception:
            return False

    def _browser_exe(self) -> str:
        forced = _env("BROWSERAPI_BROWSER", "")
        if forced:
            return forced
        for c in DEFAULT_BROWSER_CANDIDATES:
            if os.path.exists(c):
                return c
        raise RuntimeError("no browser executable found; set BROWSERAPI_BROWSER")

    def ensure_browser(self, *, url: str = "https://example.com", timeout: float = 30.0) -> dict:
        """If the extension isn't connected, launch the browser with the unpacked
        extension and wait for it to dial in. Idempotent: no-op if already up.

        Uses a dedicated profile so we never clash with the user's normal browser.
        If that profile has a STALE cached service worker (a known MV3/Edge trap)
        the extension may not connect; pass force_new_profile=True to bust it.
        """
        if self._extension_connected():
            return ok({"launched": False, "reason": "already connected"})
        return self.launch_browser(url=url, timeout=timeout)

    def launch_browser(self, *, url: str = "https://example.com",
                       ext_dir: str | None = None, profile: str | None = None,
                       timeout: float = 30.0, force_new_profile: bool = False,
                       active: bool = True) -> dict:
        exe = self._browser_exe()
        ext_dir = ext_dir or _env("BROWSERAPI_EXT_DIR", DEFAULT_EXT_DIR)
        if not os.path.isdir(ext_dir):
            return err(f"extension dir not found: {ext_dir}", NOT_FOUND)
        if profile is None:
            profile = _env("BROWSERAPI_PROFILE",
                           os.path.join(tempfile.gettempdir(), "_browsercontrol_profile"))
        if force_new_profile or not os.path.isdir(profile):
            profile = profile.rstrip("\\/") + ("_" + str(int(time.time())) if force_new_profile else "")

        args = [
            exe,
            f"--user-data-dir={profile}",
            f"--load-extension={ext_dir}",
            f"--disable-extensions-except={ext_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ]
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            return err(f"failed to launch browser: {e}", ERROR)

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._extension_connected():
                return ok({"launched": True, "profile": profile, "exe": exe})
            time.sleep(0.5)
        return err(
            "browser launched but extension did not connect within "
            f"{timeout:.0f}s (try force_new_profile=True if the profile has a stale worker)",
            NOT_CONNECTED,
        )

    def stop(self) -> dict:
        t = getattr(self, "_thread", None)
        if t is None:
            return ok({"stopped": False, "reason": "bridge not owned by this instance"})
        t.stop()
        return ok({"stopped": True})

    # ------------------------------------------------------------------ transport
    def _post(self, path: str, payload: dict, timeout: float) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except Exception:
                raise

    def _cmd(self, cmd: str, args: dict | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        try:
            j = self._post("/cmd", {"cmd": cmd, "args": args or {}, "timeout": timeout},
                           timeout=timeout + 5.0)
        except urllib.error.URLError as e:
            reason = str(getattr(e, "reason", e))
            if "timed out" in reason.lower():
                return err(f"{cmd}: bridge did not answer in {timeout + 5:.0f}s", TIMEOUT)
            return err(f"{cmd}: cannot reach bridge on port {self.port}: {reason}", NOT_FOUND)
        except TimeoutError:
            return err(f"{cmd}: timed out", TIMEOUT)
        except json.JSONDecodeError:
            return err(f"{cmd}: bridge returned non-JSON", HTTP_ERROR)
        except Exception as e:
            return err(f"{cmd}: {type(e).__name__}: {e}")

        if not isinstance(j, dict):
            return err(f"{cmd}: unexpected bridge response type {type(j).__name__}", HTTP_ERROR)

        if j.get("ok"):
            result = j.get("result")
            if isinstance(result, dict) and "__bapi_error" in result:
                return err(f"{cmd}: {result['__bapi_error']}", ERROR)
            return ok(result, port=self.port)

        msg = j.get("error", "bridge error")
        code = NOT_CONNECTED if "not connected" in msg else ERROR
        # distinguish unknown-command failures for controllers
        if msg.startswith("unknown command"):
            code = "UNKNOWN_CMD"
        return err(msg, code)

    # ------------------------------------------------------------------ full access
    def send(self, cmd: str, args: dict | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """FULL-ACCESS PASSTHROUGH. Feed ANY command name and ANY args dict
        straight to the extension, exactly as given - no validation, no filtering.

            bc.send("extract", {"selector": "a", "attribute": "href", "all": True})
            bc.send("extract", {"tabId": 123, "fn": "d => d.title"})
            bc.send("fetch", {"url": u, "method": "POST", "body": "hi"})
        """
        if not isinstance(cmd, str) or not cmd:
            return err("send: cmd must be a non-empty string", BAD_ARGS)
        if args is not None and not isinstance(args, dict):
            return err("send: args must be a dict or None", BAD_ARGS)
        return self._cmd(cmd, args or {}, timeout)

    def raw(self, cmd: str, timeout: float = DEFAULT_TIMEOUT, **args: Any) -> dict:
        """Escape hatch: any extension command with keyword args."""
        return self._cmd(cmd, args, timeout)

    def feed(self, cmd: str, args: dict | None = None, timeout: float = DEFAULT_TIMEOUT) -> Any:
        """Like send() but returns data only, raising on failure."""
        env = self.send(cmd, args, timeout)
        if not env.get("ok"):
            raise RuntimeError(env.get("error", "bridge error"))
        return env["data"]

    def commands(self) -> dict:
        return self._cmd("commands", {})

    # ------------------------------------------------------------------ sugar
    def run_js(self, code: str, tab_id: int | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Eval arbitrary JS in a page. code may be an expr ('document.title') or a
        function ('() => 42'); it runs in the page's MAIN world. Bare expressions are
        auto-wrapped into a function so both forms work."""
        args: dict = {"fn": _as_fn(code)}
        if tab_id is not None:
            args["tabId"] = int(tab_id)
        return self._cmd("extract", args, timeout)

    def ping(self) -> dict:
        try:
            with urllib.request.urlopen(self.base + "/ping", timeout=5.0) as r:
                return ok(json.loads(r.read()), port=self.port)
        except Exception as e:
            return err(f"ping failed: {e}", NOT_FOUND)

    def status(self) -> dict:
        p = self.ping()
        if not p.get("ok"):
            return p
        tabs = self._cmd("list_tabs", {})
        n = len(tabs["data"]["tabs"]) if tabs.get("ok") and isinstance(tabs.get("data"), dict) else None
        return ok({"connected": bool(p["data"].get("extension_connected")),
                   "port": self.port, "tabs": n}, port=self.port)

    def fetch(self, url: str, method: str = "GET", headers: dict | None = None,
              body: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        args: dict = {"url": url, "method": method}
        if headers:
            args["headers"] = headers
        if body is not None:
            args["body"] = body
        return self._cmd("fetch", args, timeout)

    def open_tab(self, url: str, active: bool = False, wait_ms: int = 0) -> dict:
        return self._cmd("open_tab", {"url": url, "active": active, "wait_ms": wait_ms})

    def list_tabs(self) -> dict:
        return self._cmd("list_tabs", {})

    def get_dom(self, tab_id: int | None = None, *, text: bool = True,
                selector: str | None = None, max_chars: int = 8000) -> dict:
        """Return page content.

        By default returns READABLE TEXT (scripts/styles stripped, truncated to
        max_chars) - never the raw HTML blob. Pass text=False for raw HTML, or
        selector=... to scope to one element.
        """
        if text:
            sel_js = "null" if selector is None else '"%s"' % selector.replace('"', '\\"')
            call = "() => (" + _READABLE_JS.strip() + ")(%s, %d)" % (sel_js, max_chars)
            args: dict = {"fn": call}
            if tab_id is not None:
                args["tabId"] = int(tab_id)
            r = self._cmd("extract", args)
            if r.get("ok") and isinstance(r.get("data"), dict):
                r = dict(r)
                r["data"] = r["data"].get("result", r["data"])
            return r
        return self._cmd("get_dom", {"tabId": int(tab_id)} if tab_id is not None else {})

    def extract(self, selector: str, tab_id: int | None = None,
                attribute: str = "textContent", all: bool = False) -> dict:
        args: dict = {"selector": selector, "attribute": attribute, "all": all}
        if tab_id is not None:
            args["tabId"] = int(tab_id)
        return self._cmd("extract", args)

    def get_cookies(self, url: str, name: str | None = None) -> dict:
        if not url:
            return err("get_cookies: url is required", BAD_ARGS)
        return self._cmd("get_cookies", {"url": url, "name": name} if name else {"url": url})

    def get_html(self, url: str, wait_ms: int = 2500, tab_id: int | None = None,
                 *, text: bool = True, selector: str | None = None,
                 max_chars: int = 8000) -> dict:
        """Open url (or reuse tab_id) and return content.

        Defaults to READABLE TEXT truncated to max_chars. Pass text=False for raw
        HTML (still capped by max_chars to avoid token blowups).
        """
        if tab_id is None:
            t = self.open_tab(url, active=False, wait_ms=wait_ms)
            if not t["ok"]:
                return t
            tab_id = t["data"].get("tabId", t["data"].get("tab_id"))
        if text:
            d = self.get_dom(tab_id, text=True, selector=selector, max_chars=max_chars)
            if not d["ok"]:
                return d
            return ok({"tab_id": tab_id, **(d.get("data") or {})}, port=self.port)
        d = self.get_dom(tab_id, text=False)
        if not d["ok"]:
            return d
        html = d["data"]["html"]
        if max_chars and len(html) > max_chars:
            html = html[:max_chars]
        return ok({"tab_id": tab_id, "html": html, "length": len(html),
                   "truncated": d["data"].get("length", len(html)) > max_chars}, port=self.port)


# ============================================================================
# CLI
# ============================================================================
def _emit(env: dict, pretty: bool = True) -> int:
    print(json.dumps(env, indent=2 if pretty else None, ensure_ascii=True))
    return 0 if env.get("ok") else 1


def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="BrowserControl - single-file browser control")
    p.add_argument("--port", type=int, default=None, help="bridge port (default: auto)")
    sub = p.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("up"); up.add_argument("--wait", type=float, default=30.0)
    sv = sub.add_parser("serve"); sv.add_argument("port", type=int)
    sub.add_parser("status")
    sub.add_parser("down")
    sub.add_parser("ping")
    sub.add_parser("tabs")
    sub.add_parser("commands")

    f = sub.add_parser("fetch"); f.add_argument("url"); f.add_argument("--method", default="GET")
    o = sub.add_parser("open"); o.add_argument("url")
    o.add_argument("--wait", type=int, default=0); o.add_argument("--active", action="store_true")
    g = sub.add_parser("dom"); g.add_argument("--tab", type=int, default=None)
    e = sub.add_parser("extract"); e.add_argument("selector")
    e.add_argument("--tab", type=int, default=None); e.add_argument("--attr", default="textContent")
    e.add_argument("--all", action="store_true")
    h = sub.add_parser("html"); h.add_argument("url"); h.add_argument("--wait", type=int, default=2500)
    c = sub.add_parser("cookies"); c.add_argument("url"); c.add_argument("--name", default=None)
    j = sub.add_parser("js"); j.add_argument("code"); j.add_argument("--tab", type=int, default=None)
    sd = sub.add_parser("send"); sd.add_argument("name"); sd.add_argument("--args", default="{}")
    sd.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)

    a = p.parse_args(argv)

    # 'serve' = run the bridge in the foreground (used by the detached 'up' child).
    if a.cmd == "serve":
        t = _BridgeThread(a.port)
        t.start()
        try:
            while t._thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return 0

    # 'up' = make sure a bridge + browser are running, then RETURN (never blocks).
    if a.cmd == "up":
        # 1) ensure a bridge exists; if not, spawn one DETACHED so this process can exit.
        try:
            bc = BrowserControl.discover()
        except RuntimeError:
            p = a.port or pick_free_port(*PORT_RANGE)
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "serve", str(p)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
            # wait for it to come up
            deadline = time.time() + 10
            bc = None
            while time.time() < deadline:
                try:
                    bc = BrowserControl.discover()
                    break
                except RuntimeError:
                    time.sleep(0.3)
            if bc is None:
                return _emit(err("bridge failed to start", ERROR))
            bc._spawned = True
        # 2) launch the browser if the extension isn't connected yet.
        #    Fire-and-forget: do NOT block waiting for connect (keeps 'up' fast).
        if bc._extension_connected():
            return _emit(ok({"bridge": "running", "extension": "connected",
                             "port": bc.port}))
        r = bc.launch_browser(url="https://example.com", timeout=0)  # timeout=0 -> return at once
        return _emit(ok({"bridge": "running", "extension": "launching",
                         "port": bc.port, "launch": r.get("data") or r.get("error")}))

    if a.cmd == "down":
        try:
            bc = BrowserControl.discover()
        except RuntimeError as ex:
            return _emit(err(str(ex), NOT_FOUND))
        # no in-process thread here -> return guidance instead of a fake stop
        return _emit(ok({"note": "browser/bridge left running; kill the serve/edge processes to stop",
                         "port": bc.port}))

    try:
        bc = BrowserControl(a.port) if a.port else BrowserControl.discover()
    except RuntimeError as ex:
        return _emit(err(str(ex), NOT_FOUND))

    if a.cmd == "ping":
        return _emit(bc.ping())
    if a.cmd == "status":
        return _emit(bc.status())
    if a.cmd == "tabs":
        return _emit(bc.list_tabs())
    if a.cmd == "commands":
        return _emit(bc.commands())
    if a.cmd == "fetch":
        return _emit(bc.fetch(a.url, method=a.method))
    if a.cmd == "open":
        return _emit(bc.open_tab(a.url, active=a.active, wait_ms=a.wait))
    if a.cmd == "dom":
        return _emit(bc.get_dom(a.tab))
    if a.cmd == "extract":
        return _emit(bc.extract(a.selector, tab_id=a.tab, attribute=a.attr, all=a.all))
    if a.cmd == "html":
        return _emit(bc.get_html(a.url, wait_ms=a.wait))
    if a.cmd == "cookies":
        return _emit(bc.get_cookies(a.url, name=a.name))
    if a.cmd == "js":
        return _emit(bc.run_js(a.code, tab_id=a.tab))
    if a.cmd == "send":
        try:
            args = json.loads(a.args)
        except json.JSONDecodeError:
            return _emit(err("send: --args must be valid JSON", BAD_ARGS))
        return _emit(bc.send(a.name, args, timeout=a.timeout))
    return _emit(err(f"unknown command {a.cmd}", BAD_ARGS))


# --------------------------------------------------------------------------
# Agent tool entry point
# --------------------------------------------------------------------------
def browser_control(action="ping", **kwargs):
    """Control a real Edge/Chrome browser through the browserapi extension.

    Single entry point wired as the `browser_control` agent tool. `action`
    selects the operation; remaining kwargs are passed through.

    Actions (kwargs):
        ping                                   -> {ok,data:{bridge,status,extension_connected,connected_for}}
        status                                 -> bridge + extension status
        ensure_browser                         -> start bridge and/or browser if needed
        launch_browser(force_new_profile=True) -> (re)launch the browser with the extension
        stop                                   -> stop a bridge we started in-process
        run_js(code, tab_id=None)              -> evaluate JS in the page, returns value
        fetch(url, ...)                        -> fetch a URL via the browser (cookies/headers)
        open_tab(url)                          -> open a new tab, returns tab id
        list_tabs()                            -> list open tabs
        get_dom(tab_id=None)                   -> page DOM snapshot
        get_html(url, wait_ms=...)             -> rendered HTML of a url
        extract(selector, tab_id=None, attribute=None, all=False)
        get_cookies(url=None, name=None)       -> cookies visible to the page
        send(name, args, timeout=...)          -> low-level bridge command
        raw(path, payload=None, method='POST') -> raw bridge HTTP call (full access)
        feed(name, args, timeout=...)          -> streamed command variant
        commands()                             -> list bridge commands
    """
    c = BrowserControl.get()
    a = action

    if a == "ping":
        return c.ping()
    if a == "status":
        return c.status()
    if a in ("ensure_browser", "ensure"):
        return c.ensure_browser()
    if a in ("launch_browser", "launch"):
        return c.launch_browser(kwargs.get("force_new_profile", True),
                                **{k: v for k, v in kwargs.items() if k != "force_new_profile"})
    if a in ("stop", "down"):
        return c.stop()
    if a in ("run_js", "js", "eval"):
        return c.run_js(kwargs.get("code") or kwargs.get("js") or "",
                        tab_id=kwargs.get("tab_id") or kwargs.get("tab"))
    if a == "fetch":
        return c.fetch(kwargs.pop("url"), **kwargs)
    if a in ("open_tab", "open"):
        return c.open_tab(kwargs.get("url"))
    if a in ("list_tabs", "tabs"):
        return c.list_tabs()
    if a in ("get_dom", "dom"):
        return c.get_dom(kwargs.get("tab_id") or kwargs.get("tab"))
    if a in ("get_html", "html"):
        return c.get_html(kwargs.pop("url"),
                          wait_ms=kwargs.get("wait_ms", kwargs.get("wait", 1500)))
    if a == "extract":
        return c.extract(kwargs.pop("selector"), tab_id=kwargs.get("tab_id") or kwargs.get("tab"),
                         attribute=kwargs.get("attribute"), all=kwargs.get("all", False))
    if a in ("get_cookies", "cookies"):
        return c.get_cookies(kwargs.get("url"), name=kwargs.get("name"))
    if a == "send":
        return c.send(kwargs.get("name"), kwargs.get("args") or {}, timeout=kwargs.get("timeout", 30.0))
    if a in ("raw", "call"):
        return c.raw(kwargs.get("path"), kwargs.get("payload"), method=kwargs.get("method", "POST"))
    if a == "feed":
        return c.feed(kwargs.get("name"), kwargs.get("args") or {}, timeout=kwargs.get("timeout", 30.0))
    if a == "commands":
        return c.commands()
    return {"ok": False, "error": f"unknown action {a!r}", "actions":
            ["ping", "status", "ensure_browser", "launch_browser", "stop", "run_js",
             "fetch", "open_tab", "list_tabs", "get_dom", "get_html", "extract",
             "get_cookies", "send", "raw", "feed", "commands"]}


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
