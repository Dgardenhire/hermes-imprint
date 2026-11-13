"""Live mode for the harness: the real Letterpress backend behind a small local server, so real buttons work.

The pane (desktop/plugin.js) and every route in dashboard/plugin_api.py run as they do in Hermes. The one
stand-in is the model: a scripted writer (persona_model.py) that writes each output from the passages it
is given, tying every claim to a passage label the way a real model is asked to. Imports, kits, checks,
trace cards, decisions and every export file are real.

    /usr/bin/python3 harness/live/server.py 8790              # a fresh, empty data folder in the temp dir
    /usr/bin/python3 harness/live/server.py 8790 --data DIR   # keep a data folder between runs
    ... --voice-stub                                          # recordings are silent WAVs (never played)

Then open http://127.0.0.1:8790/harness/index.html?live=1&theme=light (or theme=dark). Persona input files
for a replay (a brand guide PDF, a Canva-style PowerPoint, token files, logos, sources) are in
harness/live/personas/.

Rules this server keeps: it listens on 127.0.0.1 only; it never imports Hermes, never runs a hermes
command, never reads or writes ~/.hermes; the data folder is a temp folder unless --data names one; there is
no network except the page's own CDN loads (React, codicons).
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import logging
import os
import re
import sys
import tempfile
import types
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

if __name__ != "__main__":
    # The plugin folder is importable inside Hermes (the loader makes it a package), and this module replaces
    # fastapi in sys.modules and points Letterpress at a temp data folder as it loads. It runs only as a script.
    raise ImportError("harness/live/server.py is a local test server: run it with python, never import it.")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _data_dir(argv: list) -> Path:
    if "--data" in argv:
        d = Path(argv[argv.index("--data") + 1]).expanduser().resolve()
    else:
        d = Path(tempfile.mkdtemp(prefix="letterpress-live-"))
    if ".hermes" in d.parts:
        raise SystemExit("Live mode never writes inside ~/.hermes. Pick another folder.")
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA = _data_dir(sys.argv)
os.environ["LETTERPRESS_DATA_DIR"] = str(DATA)
logging.basicConfig(level=logging.WARNING)

# A stand-in for the few FastAPI names plugin_api.py imports; the routes themselves are untouched.
fa = types.ModuleType("fastapi")


class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


class APIRouter:
    def __init__(self):
        self.routes = []

    def _add(self, m, p):
        def deco(fn):
            self.routes.append((m, p, fn))
            return fn
        return deco

    def get(self, p):
        return self._add("GET", p)

    def post(self, p):
        return self._add("POST", p)

    def delete(self, p):
        return self._add("DELETE", p)


class Request:
    pass


fa.APIRouter, fa.HTTPException, fa.Request = APIRouter, HTTPException, Request
sys.modules["fastapi"] = fa

spec = importlib.util.spec_from_file_location("letterpress_plugin_api_live", REPO / "dashboard" / "plugin_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
sys.path.insert(0, str(HERE))
import persona_model  # noqa: E402

api.service.LLM = persona_model.PersonaModel()
if "--voice-stub" in sys.argv:  # a silent WAV per recording, so a chapter can be shown playing; nothing is played
    import voice_stub  # noqa: E402
    api.runtime.dispatch = voice_stub.dispatch

ROUTES = []
for _m, _p, _fn in api.router.routes:
    ROUTES.append((_m, re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", _p) + "$"), _fn))


class Req:
    def __init__(self, headers, body):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self._b = body

    async def stream(self):
        yield self._b


def call(method: str, path: str, headers: dict, raw: bytes):
    for m, rx, fn in ROUTES:
        if m != method:
            continue
        mm = rx.match(path)
        if not mm:
            continue
        kw = dict(mm.groupdict())
        sig = inspect.signature(fn)
        if "request" in sig.parameters:
            kw["request"] = Req(headers, raw)
        if "body" in sig.parameters:
            kw["body"] = json.loads(raw or b"{}")
        try:
            r = fn(**kw)
            if inspect.iscoroutine(r):
                r = asyncio.run(r)
            return 200, r
        except HTTPException as e:
            return e.status_code, {"detail": e.detail}
    return 404, {"detail": "no route"}


def _local(value: str, port: int, scheme: str = "") -> bool:
    return (value or "").lower() in {f"{scheme}{h}:{port}" for h in ("127.0.0.1", "localhost")}


class Handler(SimpleHTTPRequestHandler):
    def _trusted(self) -> bool:
        """Only this machine's own pages. Listening on 127.0.0.1 keeps other computers out, not other web
        pages: any site open in the same browser can post to localhost (no preflight for a text/plain body),
        and a DNS-rebound name reaches it with a foreign Host. Both are refused here."""
        port = self.server.server_address[1]
        if not _local(self.headers.get("host"), port):
            return False
        origin = self.headers.get("origin")
        return origin is None or _local(origin, port, "http://")

    def _refuse(self):
        out = b'{"detail": "Live mode answers only its own page on 127.0.0.1."}'
        self.send_response(403)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def translate_path(self, path):
        p = unquote(path.split("?")[0]).lstrip("/")
        target = (REPO / p).resolve()
        if not target.is_relative_to(REPO) or any(part.startswith(".") for part in Path(p).parts):
            return str(REPO / "harness" / "index.html")
        return str(target)

    def log_message(self, *a):
        pass

    def _api(self, method):
        if not self._trusted():
            return self._refuse()
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        code, body = call(method, self.path.split("?")[0][len("/api"):], dict(self.headers), raw)
        out = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        if not self._trusted():
            return self._refuse()
        return super().do_GET()

    def do_POST(self):
        return self._api("POST")

    def do_DELETE(self):
        return self._api("DELETE")


def serve(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8790
    print(f"Letterpress live harness on http://127.0.0.1:{port}/harness/index.html?live=1  data: {DATA}", flush=True)
    serve(port).serve_forever()
