"""Public HTTP surface for the DSL guest (health + jobs + specs + files + UI).

Served on the Unit public port. JSON errors are `{"error": ..., ...}`.
No engine URL schemes in request or response bodies. Ctl exports
``GET /v0/jobs/{id}/handoff`` (WorkHandoff projection, no nested payload)
and ``GET /v0/jobs/{id}/payload`` (canonical JSON bytes as hex/utf8).
Specs catalog is ``GET/PUT /v0/specs`` (platform.ts intention, no Getafix).
G5 files browse is ``GET /v0/files`` (specs / data / results; writes refused).
G6 thin local auth (login/register + HMAC tokens) gates mutating specs
and jobs submit. G3 editor is served at ``GET /`` and ``GET /ui``.
G5 files page is served at ``GET /files``.
G4 runs UX (editor + global submit, list, honest progress, cancel)
sits on the G1 seam. G7 is the written + smoke UX probe
(``docs/ux-journey.md``). G8 is AI chat (SSE / MCP-style tools mutate
the live graph; xAI Grok; fail closed without a key unless stub).
G10 polishes the editor with React Flow (undo/redo, minimap,
auto-layout, localStorage). Epic #1 remains open. Cloud stays locked.
Transport is operator/ctl-mediated: no guest→ctl HTTP, no
``runtime.apply`` from this guest.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from dsl.auth import LocalAuth
from dsl.catalog import CATALOG_IDS, CatalogStore
from dsl.chat import (
    KEY_ENV,
    STUB_ENV,
    TOOL_NAMES,
    ChatService,
    format_sse,
    spec_id_of,
    want_sse,
    wants_persist,
)
from dsl.errors import DslError, InvalidChat, InvalidStatus, InvalidYaml, Unauthorized
from dsl.files import FileBrowser, folder_from_query, location_from_query, refuse_write
from dsl.graph import (
    document_from_graph,
    emit_yaml,
    parse_yaml,
    validation_payload,
)
from dsl.handoff import reject_smuggle
from dsl.handoff_vocab import (
    DSL_STUB_CATALOG,
    LOCAL_DEMOS,
    RESOURCE_CLASSES,
    WORK_KINDS,
    WORK_STATUSES,
)
from dsl.jobs import JobStore
from dsl.runs import SUBMIT_LABELS
from dsl.ui import content_type_for, resolve_ui_path, ui_available

MAX_BODY = 256 * 1024
HEALTH_PAYLOAD = {"status": "ok"}
INFO_PAYLOAD = {
    "name": "dsl",
    "unit": "dsl",
    "product": "panoramix-guest-dsl",
    "kind": "actuarial-dsl-guest",
    "contract_version": "0.5",
    "pin": "0.5",
    "status": "ux-probe",
    "getafix_equivalent": False,
    "engines": "runtime-bindings-only",
    "jobs_api": True,
    "specs_api": True,
    "auth_api": True,
    "files_api": True,
    "ui": True,
    "runs_ux": True,
    "ux_journey": True,
    "chat_api": True,
    "handoff": ["kind", "class", "payload_digest"],
    "north_star_done": False,
    "auth": {
        "kind": "local-lab",
        "cognito": False,
        "mfa": False,
        "rbac": False,
        "login": "POST /v0/auth/login",
        "register": "POST /v0/auth/register",
        "me": "GET /v0/auth/me",
        "header": "Authorization: Bearer <accessToken>",
        "public": [
            "GET /health",
            "GET /v0/info",
            "GET /",
            "GET /ui",
            "GET /files",
            "POST /v0/auth/login",
            "POST /v0/auth/register",
            "GET /v0/specs",
            "GET /v0/specs/{id}",
            "GET /v0/specs/{id}/yaml",
            "GET /v0/specs/folders",
            "GET /v0/files",
            "GET /v0/files/{tab}",
            "GET /v0/files/{tab}/{id}",
            "GET /v0/files/{tab}/{id}/text",
            "POST /v0/graph/parse",
            "POST /v0/graph/export",
            "POST /v0/graph/validate",
            "GET /v0/chat",
            "GET /v0/chat/usage",
            "POST /v0/chat",
            "GET /v0/jobs",
            "GET /v0/jobs/{id}",
            "GET /v0/jobs/{id}/handoff",
            "GET /v0/jobs/{id}/payload",
        ],
        "protected": [
            "PUT /v0/specs/{id}",
            "POST /v0/specs",
            "DELETE /v0/specs/{id}",
            "POST /v0/jobs",
            "POST /v0/jobs/{id}/cancel",
            "GET /v0/auth/me",
            "POST /v0/chat persist overlay",
        ],
        "note": (
            "G6 thin local auth. Intention from getafix-seed-paul "
            "dsl-gui local-lab / dsl-backend localAuth. "
            "HMAC JWT-style tokens in-process. Not Cognito. "
            "Not MFA TOTP. Not SaaS admin RBAC. Editor uses Bearer on save "
            "and on job submit/cancel. Chat persist (saved-spec overlay) "
            "also requires Bearer. Epic #1 remains open. Cloud stays locked."
        ),
    },
    "editor": {
        "path": "/",
        "alt": "/ui",
        "files": "/files",
        "canvas": ["dataSource", "loop", "formula", "aggregation"],
        "side_panel": True,
        "yaml": True,
        "validate": ["undefined_var", "missing_filename"],
        "catalog_open": True,
        "save_auth": "Bearer",
        "persistence": "localStorage + overlay PUT",
        "react_flow": True,
        "equivalent_canvas": False,
        "undo_redo": True,
        "minimap": True,
        "auto_layout": True,
        "multi_select": True,
        "theme": "light+dark",
        "build": "editor/ (Vite + @xyflow/react); committed ui/app.js",
        "note": (
            "G10 React Flow polish on the G3 editor. Intention of "
            "getafix-seed-paul dsl-gui feel (canvas + YAML I/O + validate "
            "+ undo/redo + minimap + auto-layout), not a SPA lift. "
            "G5 files browse is /files. G4 adds submit from this chrome. "
            "G8 adds the ChatPanel (tools mutate the live canvas). "
            "Epic #1 remains open. Cloud stays locked."
        ),
    },
    "chat": {
        "path": "POST /v0/chat",
        "status": "GET /v0/chat",
        "usage": "GET /v0/chat/usage",
        "sse": True,
        "tools": list(TOOL_NAMES),
        "fail_closed": True,
        "provider": "xai",
        "family": "grok",
        "stub_env": STUB_ENV,
        "key_env": KEY_ENV,
        "key_file": "~/.xai",
        "persist_auth": "Bearer",
        "cognito": False,
        "getafix": False,
        "spot": False,
        "note": (
            "G8 AI chat. Intention of getafix-seed-paul dsl-gui ChatPanel "
            "+ dsl-backend POST /api/chat (SSE / MCP-style tools). "
            "Live provider is xAI Grok (Chat Completions, stdlib urllib). "
            "Not a SPA lift. Not Cognito. Not a Getafix fold. "
            "Fail closed without XAI_API_KEY / GROK_API_KEY / "
            "DSL_CHAT_API_KEY, XAI_API_KEY_FILE, or ~/.xai unless "
            "DSL_CHAT_STUB=1. Live-graph mutate is public like "
            "parse/validate; overlay persist needs G6 Bearer. "
            "north_star_done stays false. "
            "Epic #1 remains open. Cloud stays locked."
        ),
    },
    "files": {
        "tabs": ["specs", "data", "results"],
        "list": "GET /v0/files",
        "tab": "GET /v0/files/{tab}",
        "get": "GET /v0/files/{tab}/{id}",
        "text": "GET /v0/files/{tab}/{id}/text",
        "ui": "/files",
        "writes": "refused",
        "locations": ["guest-local"],
        "shared_group": False,
        "s3": False,
        "note": (
            "G5 files browse. Intention of getafix-seed-paul dsl-gui "
            "FilesPage — read-first, not a code lift. Specs pair with G2. "
            "Data/results walk fixture stubs under fixtures/. "
            "Writes fail closed. No multi-tenant S3 Shared/Group. "
            "Live run submit is G4 (this surface). Epic #1 remains open. "
            "Cloud stays locked."
        ),
    },
    "specs": {
        "ids": list(CATALOG_IDS),
        "list": "GET /v0/specs",
        "get": "GET /v0/specs/{id}",
        "yaml": "GET /v0/specs/{id}/yaml",
        "save": "PUT /v0/specs/{id}",
        "overlay": "process-local",
        "auth": "PUT/POST/DELETE require Bearer",
        "rules": ["no empty content", "no sticky Untitled"],
        "note": (
            "G2 specs catalog. G11 serves seed-shaped domain YAML graphs. "
            "Not a dsl-work CuPy / engine lift. Overlay never mutates catalog files. "
            "No Getafix. No Cognito. PUT overlay requires G6 local auth. "
            "G3 editor opens catalog rows and saves overlays. "
            "Epic #1 remains open. Cloud stays locked."
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
        "submit_auth": True,
        "pause_resume": False,
        "submit_labels": list(SUBMIT_LABELS),
        "spot": False,
        "progress": "omit-when-missing",
        "cancel_stub": True,
        "cancel_durable": False,
        "note": (
            "G1 opaque jobs seam (intact). Local stub only. "
            "demo:dsl digests a tiny catalog stub — not NSM/CuPy math. "
            "G2 specs API is GET/PUT /v0/specs, not this jobs body. "
            "POST submit/cancel require G6 local auth. GET stays public. "
            "G4 UI submits through this seam (cpu/gpu/both labels). "
            "G7 smoke-walks this path. Guest emits WorkHandoff only. "
            "Epic #1 remains open. Cloud stays locked."
        ),
    },
    "runs": {
        "submit": ["editor", "global"],
        "labels": list(SUBMIT_LABELS),
        "spot": False,
        "list": "GET /v0/jobs",
        "list_status": "GET /v0/jobs?status=queued|running|succeeded|failed|canceled",
        "detail": "GET /v0/jobs/{id}",
        "progress": "omit-when-missing",
        "cancel_stub": True,
        "cancel_durable": False,
        "note": (
            "G4 runs UX. dsl-gui submit/list/watch/cancel intention, "
            "not a SPA lift. Labels cpu/gpu/both — no Spot theater. "
            "both fans out to two G1 jobs (class cpu and class gpu). "
            "Progress omitted when the stub has none. Cancel is the G1 "
            "stub path; durable cancel only when a hook is installed. "
            "G7 documents the representative journey. Epic #1 remains open. "
            "Cloud stays locked."
        ),
    },
    "ux": {
        "path": ["open", "edit/validate", "submit", "watch", "cancel"],
        "doc": "docs/ux-journey.md",
        "benchmark": "getafix-seed-paul dsl-gui local-lab",
        "lift": False,
        "north_star_done": False,
        "note": (
            "G7 UX journey probe + G10 React Flow polish. "
            "Representative path is smoke-tested. Editor feel is a "
            "greenfield React Flow canvas (not a dsl-gui lift). "
            "Progress omitted when missing. north_star_done stays false "
            "until epic both boxes. Epic #1 remains open. Cloud stays locked."
        ),
    },
}

_JOB_RE = re.compile(r"^/v0/jobs/([^/]+)$")
_CANCEL_RE = re.compile(r"^/v0/jobs/([^/]+)/cancel$")
_HANDOFF_RE = re.compile(r"^/v0/jobs/([^/]+)/handoff$")
_PAYLOAD_RE = re.compile(r"^/v0/jobs/([^/]+)/payload$")
_SPEC_RE = re.compile(r"^/v0/specs/([^/]+)$")
_SPEC_YAML_RE = re.compile(r"^/v0/specs/([^/]+)/yaml$")
_FILES_TAB_RE = re.compile(r"^/v0/files/(specs|data|results)$")
_FILES_ITEM_RE = re.compile(r"^/v0/files/(specs|data|results)/([^/]+)$")
_FILES_TEXT_RE = re.compile(r"^/v0/files/(specs|data|results)/([^/]+)/text$")
_FILES_DOWNLOAD_RE = re.compile(r"^/v0/files/(specs|data|results)/([^/]+)/download$")
_FILES_ANY_RE = re.compile(r"^/v0/files(?:/.*)?$")


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


def _graph_from_body(payload: dict[str, Any]):
    # Live canvas (`graph`) wins when both are sent — the YAML textarea can lag.
    graph = payload.get("graph")
    if isinstance(graph, dict) and (
        graph.get("nodes") is not None or graph.get("metadata") or graph.get("edges")
    ):
        return document_from_graph(graph)
    yaml_text = payload.get("yaml")
    if yaml_text is None:
        yaml_text = payload.get("content")
    if isinstance(yaml_text, str) and yaml_text.strip():
        return parse_yaml(yaml_text)
    if isinstance(graph, dict):
        return document_from_graph(graph)
    if any(key in payload for key in ("nodes", "metadata", "data", "execution")):
        return document_from_graph(payload)
    raise InvalidYaml("yaml or graph is required")


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
        auth: LocalAuth | None = None,
        files: FileBrowser | None = None,
        chat: ChatService | None = None,
    ) -> None:
        self.store = store or JobStore()
        self.catalog = catalog or CatalogStore()
        self.auth = auth or LocalAuth.from_env()
        self.files = files or FileBrowser(catalog=self.catalog)
        self.chat = chat if chat is not None else ChatService.from_env()

    def handle(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        method = method.upper()
        split = urlsplit(path)
        path = split.path or "/"
        query = parse_qs(split.query, keep_blank_values=False)
        headers = {str(key).lower(): value for key, value in (headers or {}).items()}
        try:
            return self._route(method, path, body, query, headers)
        except DslError as err:
            extra = {"WWW-Authenticate": "Bearer"} if isinstance(err, Unauthorized) else None
            return _json_response(err.http_status, err.to_dict(), extra)

    def _route(
        self,
        method: str,
        path: str,
        body: bytes,
        query: dict[str, list[str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        if path == "/health":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, HEALTH_PAYLOAD)
        if path == "/v0/info":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self._info())
        ui = self._route_ui(method, path)
        if ui is not None:
            return ui
        graph = self._route_graph(method, path, body)
        if graph is not None:
            return graph
        chat = self._route_chat(method, path, body, query, headers)
        if chat is not None:
            return chat
        auth = self._route_auth(method, path, body, headers)
        if auth is not None:
            return auth
        specs = self._route_specs(method, path, body, headers)
        if specs is not None:
            return specs
        files = self._route_files(method, path, query)
        if files is not None:
            return files
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
                self.auth.authenticate(headers)
                return self._create_job(body)
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        cancel = _CANCEL_RE.match(path)
        if cancel:
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            self.auth.authenticate(headers)
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

    def _info(self) -> dict[str, Any]:
        payload = dict(INFO_PAYLOAD)
        payload["ui"] = bool(INFO_PAYLOAD["ui"] and ui_available())
        durable = self.store.has_durable_cancel()
        jobs = dict(INFO_PAYLOAD["jobs"])
        jobs["cancel_durable"] = durable
        runs = dict(INFO_PAYLOAD["runs"])
        runs["cancel_durable"] = durable
        payload["jobs"] = jobs
        payload["runs"] = runs
        payload["runs_ux"] = True
        payload["ux_journey"] = True
        payload["chat_api"] = True
        payload["north_star_done"] = False
        return payload

    def _route_ui(self, method: str, path: str) -> HttpResponse | None:
        target = resolve_ui_path(path)
        if target is None:
            return None
        if method != "GET":
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        return HttpResponse(
            status=200,
            body=target.read_bytes(),
            content_type=content_type_for(target),
        )

    def _route_graph(self, method: str, path: str, body: bytes) -> HttpResponse | None:
        if path not in ("/v0/graph/parse", "/v0/graph/export", "/v0/graph/validate"):
            return None
        if method != "POST":
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        payload = _read_json_object(body)
        reject_smuggle(payload)
        doc = _graph_from_body(payload)
        if path.endswith("/parse"):
            yaml_text = emit_yaml(doc)
            return _json_response(
                200,
                {"graph": doc.to_dict(), "yaml": yaml_text, "stub": doc.is_stub},
            )
        if path.endswith("/export"):
            return _json_response(
                200,
                {"yaml": emit_yaml(doc), "stub": doc.is_stub},
            )
        return _json_response(200, validation_payload(doc))

    def _route_chat(
        self,
        method: str,
        path: str,
        body: bytes,
        query: dict[str, list[str]] | None,
        headers: dict[str, str] | None,
    ) -> HttpResponse | None:
        if path == "/v0/chat/usage":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            return _json_response(200, self.chat.usage())
        if path != "/v0/chat":
            return None
        if method == "GET":
            return _json_response(200, self.chat.status())
        if method != "POST":
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        payload = _read_json_object(body)
        reject_smuggle(
            {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "message",
                    "conversationHistory",
                    "history",
                }
            }
        )
        persist = wants_persist(payload)
        spec_id = spec_id_of(payload)
        if persist:
            self.auth.authenticate(headers)
            if not spec_id:
                raise InvalidChat("spec_id is required to persist an overlay")
        turn = self.chat.run(payload)
        if persist:
            yaml_text = self.chat.persist_yaml(turn.graph)
            saved = self.catalog.save(spec_id, {"content": yaml_text})
            turn.persisted = saved
        if want_sse(headers, query):
            return HttpResponse(
                status=200,
                body=format_sse(turn.events),
                content_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        return _json_response(200, turn.to_dict())

    def _route_auth(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str] | None,
    ) -> HttpResponse | None:
        if path == "/v0/auth/login":
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            payload = _read_json_object(body)
            email = payload.get("email") if isinstance(payload.get("email"), str) else ""
            password = payload.get("password") if isinstance(payload.get("password"), str) else ""
            return _json_response(200, self.auth.login(email, password))
        if path == "/v0/auth/register":
            if method != "POST":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            payload = _read_json_object(body)
            email = payload.get("email") if isinstance(payload.get("email"), str) else ""
            password = payload.get("password") if isinstance(payload.get("password"), str) else ""
            name = payload.get("name") if isinstance(payload.get("name"), str) else ""
            return _json_response(201, self.auth.register(email, password, name))
        if path == "/v0/auth/me":
            if method != "GET":
                return _json_response(405, {"error": "method_not_allowed", "path": path})
            user = self.auth.authenticate(headers)
            return _json_response(200, {"user": user.to_dict()})
        return None

    def _route_specs(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str] | None,
    ) -> HttpResponse | None:
        if path == "/v0/specs":
            if method == "GET":
                return _json_response(200, self.catalog.list())
            if method == "POST":
                self.auth.authenticate(headers)
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
                self.auth.authenticate(headers)
                payload = _read_json_object(body)
                saved = self.catalog.save(spec_id, payload)
                return _json_response(200, saved)
            if method == "DELETE":
                self.auth.authenticate(headers)
                self.catalog.refuse_delete(spec_id)
            return _json_response(405, {"error": "method_not_allowed", "path": path})
        return None

    def _route_files(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]] | None,
    ) -> HttpResponse | None:
        if not _FILES_ANY_RE.match(path):
            return None
        if method != "GET":
            refuse_write()
        if path == "/v0/files":
            return _json_response(200, self.files.tabs())
        tab_match = _FILES_TAB_RE.match(path)
        if tab_match:
            return _json_response(
                200,
                self.files.list(
                    tab_match.group(1),
                    folder=folder_from_query(query),
                    location=location_from_query(query),
                ),
            )
        text_match = _FILES_TEXT_RE.match(path)
        if text_match:
            return _json_response(
                200, self.files.text(text_match.group(1), text_match.group(2))
            )
        download = _FILES_DOWNLOAD_RE.match(path)
        if download:
            filename, blob, content_type = self.files.download(
                download.group(1), download.group(2)
            )
            return HttpResponse(
                status=200,
                body=blob,
                content_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
        item_match = _FILES_ITEM_RE.match(path)
        if item_match:
            return _json_response(
                200, self.files.get(item_match.group(1), item_match.group(2))
            )
        return _json_response(404, {"error": "not_found", "path": path})

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
            headers = {key.lower(): value for key, value in self.headers.items()}
            self._write(app.handle(method, self.path, body, headers))

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
