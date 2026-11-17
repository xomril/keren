"""Local chat UI for the prototype. stdlib only; binds to 127.0.0.1.

Demo only: the operator identity is fixed server-side (see access.py); the page
cannot choose it. Offline fake model by default; --live uses the paid API and is
capped per server run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .access import DEFAULT_OPERATOR
from .app import answer
from .env import load_env
from .model import AnthropicModel, FakeModel

INDEX = Path(__file__).parent / "static" / "index.html"
MAX_BODY, MAX_QUESTION = 4096, 500


def make_server(model, mode: str, model_name: str, port: int = 8000, max_calls: int = 50):
    lock = threading.Lock()
    state = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep questions out of logs
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _host_ok(self) -> bool:  # blocks DNS-rebinding style access
            p = self.server.server_address[1]
            return self.headers.get("Host", "") in ("127.0.0.1:%d" % p, "localhost:%d" % p)

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if self.path == "/":
                return self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/config":
                return self._json(200, {"mode": mode, "model": model_name, "operator": DEFAULT_OPERATOR,
                                        "maxQuestion": MAX_QUESTION})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/ask" or not self._host_ok():
                return self._json(403, {"error": "forbidden"})
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self._json(403, {"error": "bad origin"})
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(415, {"error": "json only"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= MAX_BODY:
                    raise ValueError
                data = json.loads(self.rfile.read(n))
                cid, q = data["customerId"], data["question"]
                if not (isinstance(cid, str) and isinstance(q, str) and q.strip() and len(cid) <= 20):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                return self._json(400, {"error": "invalid request"})
            if len(q) > MAX_QUESTION:
                return self._json(400, {"error": "question too long (max %d characters)" % MAX_QUESTION})
            if mode == "live":
                with lock:
                    if state["n"] >= max_calls:
                        return self._json(429, {"error": "live question limit reached for this server run"})
                    state["n"] += 1
            try:
                res = answer(DEFAULT_OPERATOR, cid, q, model)
            except Exception:  # never leak internals to the page
                return self._json(500, {"error": "internal error"})
            self._json(200, asdict(res))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="keren.web", description="Local chat UI (demo)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--live", action="store_true", help="use the real Anthropic API (paid, capped at 50 questions)")
    a = ap.parse_args(argv)
    if a.live:
        load_env()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set (put it in .env, see .env.example).", file=sys.stderr)
            return 2
        model, mode = AnthropicModel(), "live"
    else:
        model, mode = FakeModel(), "offline"
    srv = make_server(model, mode, model.name, a.port)
    print("Keren chat UI on http://127.0.0.1:%d  (%s, model: %s). Ctrl+C to stop." % (a.port, mode, model.name))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
