#!/usr/bin/env python3
"""Panoramix entrypoint for dsl (binds PLATFORM_LISTEN_HTTP).

Thin Unit artifact — same pattern as panoramix-guest-sos / httpbin: this
file imports domain from dsl/ (dsl.http). Emulate digest is still
entrypoint paths only; sibling edits under dsl/ must not be assumed to
change it. G1 jobs seam. G2 specs catalog. G3 editor. G5 files browse
at GET /files. G6 thin local auth. Engines stay in panoramix-runtime
bindings. Epic #1 remains open. Does not unlock runtime #61 / #29.
"""

from __future__ import annotations

import os

from dsl.http import DslApp, DslServer, bind_handler

DEFAULT_PORT = 18380


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


def main() -> None:
    raw = (
        os.environ.get("PLATFORM_LISTEN_HTTP")
        or os.environ.get("PLATFORM_LISTEN_http")
        or str(DEFAULT_PORT)
    )
    host, port = parse_listen(raw)
    app = DslApp()
    httpd = DslServer((host, port), bind_handler(app))
    print(f"dsl listening on {host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
