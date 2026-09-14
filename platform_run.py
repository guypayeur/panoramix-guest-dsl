#!/usr/bin/env python3
"""Panoramix entrypoint for dsl (binds PLATFORM_LISTEN_HTTP).

Stdlib-only HTTP stub. No jobs API (G1). No editor (G3). Engines stay
in panoramix-runtime bindings. Apply digest is entrypoint paths only.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_PORT = 18380

HEALTH_PAYLOAD = {"status": "ok"}
INFO_PAYLOAD = {
    "name": "dsl",
    "unit": "dsl",
    "product": "panoramix-guest-dsl",
    "kind": "actuarial-dsl-guest",
    "contract_version": "0.5",
    "pin": "0.5",
    "status": "skeleton",
    "getafix_equivalent": False,
    "engines": "runtime-bindings-only",
    "jobs_api": False,
    "ui": False,
    "handoff": ["kind", "class", "payload_digest"],
    "north_star_done": False,
}


def parse_listen(raw: str) -> tuple[str, int]:
    """Accept port, :port, or host:port. Port-only keeps emulate loopback."""
    raw = (raw or str(DEFAULT_PORT)).strip()
    if raw.startswith(":"):
        return "0.0.0.0", int(raw[1:])
    if ":" in raw:
        host, port = raw.rsplit(":", 1)
        if host in ("", "*", "[::]"):
            host = "0.0.0.0"
        return host, int(port)
    return "127.0.0.1", int(raw)


def handle(method: str, path: str) -> tuple[int, dict[str, Any]]:
    """Dispatch GET /health and GET /v0/info. No jobs API yet."""
    method = method.upper()
    path = (path or "/").split("?", 1)[0]
    if path == "/health":
        if method != "GET":
            return 405, {"error": "method_not_allowed", "path": path}
        return 200, HEALTH_PAYLOAD
    if path == "/v0/info":
        if method != "GET":
            return 405, {"error": "method_not_allowed", "path": path}
        return 200, INFO_PAYLOAD
    return 404, {"error": "not_found", "path": path}


class DslHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        status, payload = handle("GET", self.path)
        self._send_json(status, payload)

    def do_POST(self) -> None:
        status, payload = handle("POST", self.path)
        self._send_json(status, payload)


class DslServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    raw = (
        os.environ.get("PLATFORM_LISTEN_HTTP")
        or os.environ.get("PLATFORM_LISTEN_http")
        or str(DEFAULT_PORT)
    )
    host, port = parse_listen(raw)
    httpd = DslServer((host, port), DslHandler)
    print(f"dsl listening on {host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
