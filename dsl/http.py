"""Public HTTP surface for the DSL guest (health + jobs + specs catalog).

Served on the Unit public port. JSON errors are `{"error": ..., ...}`.
No engine URL schemes in request or response bodies. Ctl exports
``GET /v0/jobs/{id}/handoff`` (WorkHandoff projection, no nested payload)
and ``GET /v0/jobs/{id}/payload`` (canonical JSON bytes as hex/utf8).
Specs catalog is ``GET/PUT /v0/specs`` (platform.ts intention, no Getafix).
No operator UI (G3). Transport is operator/ctl-mediated: no guest→ctl
HTTP, no ``runtime.apply`` from this guest.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from dsl.catalog import CATALOG_IDS, CatalogStore
from dsl.errors import DslError, InvalidStatus
from dsl.handoff_vocab import (
    DSL_STUB_CATALOG,
    LOCAL_DEMOS,
    RESOURCE_CLASSES,
    WORK_KINDS,
    WORK_STATUSES,
)
from dsl.jobs import JobStore

MAX_BODY = 256 * 1024
HEALTH_PAYLOAD = {"status": "ok"}
INFO_PAYLOAD = {
    "name": "dsl",
    "unit": "dsl",
    "product": "panoramix-guest-dsl",
    "kind": "actuarial-dsl-guest",
    "contract_version": "0.5",
    "pin": "0.5",
    "status": "specs-catalog",
    "getafix_equivalent": False,
    "engines": "runtime-bindings-only",
    "jobs_api": True,
    "specs_api": True,
    "ui": False,
    "handoff": ["kind", "class", "payload_digest"],
    "north_star_done": False,
    "specs": {
        "ids": list(CATALOG_IDS),
        "list": "GET /v0/specs",
        "get": "GET /v0/specs/{id}",
        "yaml": "GET /v0/specs/{id}/yaml",
        "save": "PUT /v0/specs/{id}",
        "overlay": "process-local",
        "rules": ["no empty content", "no sticky Untitled"],
        "note": (
            "G2 specs catalog. Thin in-guest YAML stubs / seed-file pointers. "
            "Not a dsl-work CuPy lift. Overlay never mutates catalog files. "
            "No Getafix. No Cognito. No editor (G3). "
            "Does not close epic #1. Does not unlock runtime #61/#29."
        ),
    },
    "jobs": {
        "kinds": sorted(WORK_KINDS),
        "classes": sorted(RESOURCE_CLASSES),
        "statuses": list(WORK_STATUSES),
        "handoff": ["kind", "class", "payload_digest"],
        "local_demo": sorted(LOCAL_DEMOS),
        "dsl_catalog": sorted(DSL_STUB_CATALOG),
        "list": "GET /v0/jobs",
        "list_status": "GET /v0/jobs?status=queued|running|succeeded|failed|canceled",
        "handoff_export": "GET /v0/jobs/{id}/handoff",
        "payload_export": "GET /v0/jobs/{id}/payload",
        "pause_resume": False,
        "note": (
            "G1 opaque jobs seam (intact). Local stub only. "
            "demo:dsl digests a tiny catalog stub — not NSM/CuPy math. "
            "G2 specs API is GET/PUT /v0/specs, not this jobs body. "
            "No editor (G3). Guest emits WorkHandoff only. "
            "Does not close epic #1. Does not unlock runtime #61/#29."
        ),
    },
}

_JOB_RE = re.compile(r"^/v0/jobs/([^/]+)$")
_CANCEL_RE = re.compile(r"^/v0/jobs/([^/]+)/cancel$")
_HANDOFF_RE = re.compile(r"^/v0/jobs/([^/]+)/handoff$")
_PAYLOAD_RE = re.compile(r"^/v0/jobs/([^/]+)/payload$")
_SPEC_RE = re.compile(r"^/v0/specs/([^/]+)$")
_SPEC_YAML_RE = re.compile(r"^/v0/specs/([^/]+)/yaml$")


def parse_job_status_filter(
    query: dict[str, list[str]],
) -> frozenset[str] | None:
    """Parse ``?status=`` into known WORK_STATUSES. None means unfiltered."""
    raw: list[str] = []
    for item in query.get("status", []):
        raw.extend(part.strip() for part in item.split(","))
    wanted = [value for value in raw if value]
    if not wanted:
        return None
    unknown = [value for value in wanted if value not in WORK_STATUSES]
    if unknown:
        raise InvalidStatus(unknown[0])
    return frozenset(wanted)


@dataclass
class HttpResponse:
    status: int
    body: bytes
    content_type: str = "application/json"
    headers: dict[str, str] | None = None


def _json_response(
    status: int, payload: Any, extra_headers: dict[str, str] | None = None
) -> HttpResponse:
    body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    return HttpResponse(
        status=status,
        body=body,
        content_type="application/json",
        headers=extra_headers,
    )


def _read_json_object(body: bytes) -> dict[str, Any]:
    if not body or not body.strip():
        raise DslError("invalid_json", detail="request body is required")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DslError("invalid_json", detail=str(exc)) from exc
    if not isinstance(payload, dict):
        raise DslError("invalid_json", detail="body must be a JSON object")
    return payload


class DslApp:
    """Dispatch table used by the HTTP handler and by tests (no sockets)."""

    def __init__(
        self,
        store: JobStore | None = None,
        catalog: CatalogStore | None = None,
    ) -> None:
        self.store = store or JobStore()
        self.catalog = catalog or CatalogStore()

    def handle(self, method: str, path: str, body: bytes = b"") -> HttpResponse:
        method = method.upper()
        split = urlsplit(path)
        path = split.path or "/"
        query = parse_qs(split.query, keep_blank_values=False)
        try:
            return self._route(method, path, body, query)
        except DslError as err:
            return _json_response(err.http_status, err.to_dict())

    def _route(
        self,
        method: str,
        path: str,
        body: bytes,
        query: dict[str, list[str]] | None = None,
    ) -> HttpResponse:
        if path == "/health":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, HEALTH_PAYLOAD)
        if path == "/v0/info":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, INFO_PAYLOAD)
        specs = self._route_specs(method, path, body)
        if specs is not None:
            return specs
        if path == "/v0/jobs":
            if method == "GET":
                statuses = parse_job_status_filter(query or {})
                payload: dict[str, Any] = {
                    "jobs": [j.to_dict() for j in self.store.list(statuses=statuses)]
                }
                if statuses is not None:
                    payload["status"] = [name for name in WORK_STATUSES if name in statuses]
                return _json_response(200, payload)
            if method == "POST":
                return self._create_job(body)
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        cancel = _CANCEL_RE.match(path)
        if cancel:
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.cancel(cancel.group(1))
            return _json_response(200, job.to_dict())
        handoff = _HANDOFF_RE.match(path)
        if handoff:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.handoff(handoff.group(1)))
        payload = _PAYLOAD_RE.match(path)
        if payload:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.store.payload(payload.group(1)))
        job_match = _JOB_RE.match(path)
        if job_match:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            job = self.store.get(job_match.group(1))
            return _json_response(200, job.to_dict())
        return _json_response(404, {"error": "not_found", "path": path})

    def _route_specs(
        self, method: str, path: str, body: bytes
    ) -> HttpResponse | None:
        if path == "/v0/specs":
            if method == "GET":
                return _json_response(200, self.catalog.list())
            if method == "POST":
                self.catalog.refuse_create()
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        if path == "/v0/specs/folders":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.catalog.folders())
        yaml_match = _SPEC_YAML_RE.match(path)
        if yaml_match:
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.catalog.yaml(yaml_match.group(1)))
        spec_match = _SPEC_RE.match(path)
        if spec_match:
            spec_id = spec_match.group(1)
            if method == "GET":
                return _json_response(200, self.catalog.get(spec_id))
            if method == "PUT":
                payload = _read_json_object(body)
                saved = self.catalog.save(spec_id, payload)
                return _json_response(200, saved)
            if method == "DELETE":
                self.catalog.refuse_delete(spec_id)
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        return None

    def _create_job(self, body: bytes) -> HttpResponse:
        payload = _read_json_object(body)
        job = self.store.submit(payload)
        return _json_response(
            201,
            job.to_dict(),
            extra_headers={"Location": f"/v0/jobs/{job.id}"},
        )


class DslServer(ThreadingHTTPServer):
    allow_reuse_address = True


def bind_handler(app: DslApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_PUT(self) -> None:
            self._dispatch("PUT")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

        def _dispatch(self, method: str) -> None:
            length_raw = self.headers.get("Content-Length") or "0"
            try:
                length = int(length_raw)
            except ValueError:
                self._write(
                    _json_response(400, {"error": "invalid_json", "detail": "bad Content-Length"})
                )
                return
            if length < 0 or length > MAX_BODY:
                self._write(_json_response(413, {"error": "payload_too_large"}))
                return
            body = self.rfile.read(length) if length else b""
            self._write(app.handle(method, self.path, body))

        def _write(self, resp: HttpResponse) -> None:
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(resp.body)))
            self.send_header("Connection", "close")
            if resp.headers:
                for key, value in resp.headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(resp.body)

    return Handler
