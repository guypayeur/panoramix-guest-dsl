"""G13 durable progress hook — surface runtime fields, never invent.

Opt-in only. Default is inert: the G1 stub runner still omits
``progress``. When an operator installs ``PANORAMIX_CTL_HTTP``
(loopback ctl HTTP, local-dsl verbs on port **19217**) or
``PANORAMIX_RUNTIME_ROOT`` (``python3 -m runtime.apply dsl progress``),
this guest projects **reported** ``stage`` / ``fraction`` / ``elapsed``
onto run detail.

Transport stays operator/ctl-mediated. Guest does not open mesh ctl,
does not call ``runtime.apply`` unless the operator pointed
``PANORAMIX_RUNTIME_ROOT`` at a local checkout, and does not invent a
percent from fraction or walls. Recorded local-dsl progress often
ships ``fraction: null`` — that stays omitted.

Not G12 submit fields. Not Batch ECG / Watchdog. Epic #1 remains
open. Cloud stays locked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from dsl.runs import honest_progress

ENV_CTL_HTTP = "PANORAMIX_CTL_HTTP"
ENV_CTL_BEARER = "PANORAMIX_CTL_HTTP_BEARER"
ENV_CTL_KIND = "PANORAMIX_CTL_KIND"
ENV_RUNTIME_ROOT = "PANORAMIX_RUNTIME_ROOT"

HOOK_KIND_INERT = "inert"
HOOK_KIND_CTL_HTTP = "ctl_http"
HOOK_KIND_CTL_APPLY = "ctl_apply"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CTL_KIND_DSL = "dsl"
DEFAULT_DSL_CTL_PORT = 19217
DSL_PREFIX = "/dsl"
GET_VERBS = frozenset({"status", "progress"})
POST_VERBS = frozenset({"admit", "cancel"})
CTL_HTTP_TIMEOUT_SEC = 1.5
APPLY_TIMEOUT_SEC = 2.5

HttpTransport = Callable[..., tuple[int, str]]
DurableProgress = Callable[[Any], dict[str, Any] | None]


def work_id_for(job: Any) -> str | None:
    """Prefer a hook-supplied runtime id; else the guest job id."""
    local = getattr(job, "local", None) or {}
    if isinstance(local, dict):
        for key in ("runtime_id", "cw_id", "ctl_id"):
            raw = local.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    job_id = getattr(job, "id", None)
    if isinstance(job_id, str) and job_id.strip():
        return job_id.strip()
    return None


def normalize_ctl_http_base(raw: str | None) -> str | None:
    """Return a loopback http origin, or None (fail closed)."""
    text = str(raw or "").strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme.lower() != "http":
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    host = (parsed.hostname or "").strip().lower()
    if host not in LOOPBACK_HOSTS:
        return None
    if parsed.path not in {"", "/"}:
        return None
    if parsed.query or parsed.fragment:
        return None
    port = parsed.port
    if port is not None and not (1 <= int(port) <= 65535):
        return None
    host_part = "[::1]" if host == "::1" else host
    netloc = host_part if port is None else f"{host_part}:{int(port)}"
    return urlunsplit(("http", netloc, "", "", ""))


def ctl_http_base_from_env(env: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    return normalize_ctl_http_base(source.get(ENV_CTL_HTTP))


def bearer_from_env(env: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    raw = str(source.get(ENV_CTL_BEARER) or "").strip()
    return raw or None


def resolve_ctl_kind(env: Mapping[str, str] | None = None, *, origin: str | None = None) -> str:
    source = os.environ if env is None else env
    raw = str(source.get(ENV_CTL_KIND) or "").strip().lower()
    if raw in {"dsl", "dsl-local", "local-dsl"}:
        return CTL_KIND_DSL
    if origin:
        port = urlsplit(origin).port
        if port == DEFAULT_DSL_CTL_PORT:
            return CTL_KIND_DSL
    return CTL_KIND_DSL


def urllib_request_ctl(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    *,
    timeout: float = CTL_HTTP_TIMEOUT_SEC,
) -> tuple[int, str]:
    req = Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), (resp.read() or b"").decode("utf-8")
    except HTTPError as exc:
        raw = b""
        try:
            raw = exc.read() or b""
        except OSError:
            raw = b""
        return int(exc.code), raw.decode("utf-8", errors="replace")
    except (TimeoutError, URLError, OSError, ValueError):
        return 0, ""


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


class InertProgressHook:
    """Default: no durable progress. Stub path stays omit-when-missing."""

    kind = HOOK_KIND_INERT

    def __call__(self, job: Any) -> dict[str, Any] | None:
        return self.progress(job)

    def progress(self, job: Any) -> dict[str, Any] | None:
        del job
        return None


class LabDslHttpHook:
    """Loopback ctl HTTP → ``GET /dsl/progress?id=``.

    Fail closed on non-loopback / unreachable. Does not invent
    fraction or percent. Not guest→mesh ctl.
    """

    kind = HOOK_KIND_CTL_HTTP

    def __init__(
        self,
        base_url: str,
        *,
        transport: HttpTransport | None = None,
        bearer: str | None = None,
        ctl: str = CTL_KIND_DSL,
    ) -> None:
        origin = normalize_ctl_http_base(base_url)
        if origin is None:
            raise ValueError("ctl HTTP base must be a loopback http origin")
        self.base_url = origin
        self.transport = transport or urllib_request_ctl
        self.bearer = str(bearer).strip() if bearer else None
        self.ctl = CTL_KIND_DSL if ctl in {CTL_KIND_DSL, "dsl-local", "local-dsl"} else CTL_KIND_DSL
        self.prefix = DSL_PREFIX

    def __call__(self, job: Any) -> dict[str, Any] | None:
        return self.progress(job)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.bearer:
            headers["Authorization"] = f"Bearer {self.bearer}"
        return headers

    def _invoke(self, action: str, work_id: str) -> dict[str, Any] | None:
        if action not in GET_VERBS and action not in POST_VERBS:
            return None
        method = "GET" if action in GET_VERBS else "POST"
        qs = urlencode({"id": work_id})
        url = urlunsplit(
            ("http", urlsplit(self.base_url).netloc, f"{self.prefix}/{action}", qs, "")
        )
        try:
            code, stdout = self.transport(method, url, self._headers(), None)
        except TypeError:
            try:
                code, stdout = self.transport(method, url, self._headers(), None, timeout=CTL_HTTP_TIMEOUT_SEC)
            except Exception:
                return None
        except Exception:
            return None
        if not (200 <= int(code) < 300):
            return None
        return _parse_json(stdout)

    def progress(self, job: Any) -> dict[str, Any] | None:
        work_id = work_id_for(job)
        if work_id is None:
            return None
        return self._invoke("progress", work_id)


class LabDslApplyHook:
    """Local ``python3 -m runtime.apply dsl progress --id``.

    Opt-in via ``PANORAMIX_RUNTIME_ROOT``. Fail closed on nonzero
    exit or unusable JSON. Never invents walls or percent.
    """

    kind = HOOK_KIND_CTL_APPLY

    def __init__(
        self,
        root: str,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        python: str | None = None,
    ) -> None:
        self.root = str(root)
        self.runner = runner or subprocess.run
        self.python = python or sys.executable

    def __call__(self, job: Any) -> dict[str, Any] | None:
        return self.progress(job)

    def progress(self, job: Any) -> dict[str, Any] | None:
        work_id = work_id_for(job)
        if work_id is None:
            return None
        cmd = [self.python, "-m", "runtime.apply", "dsl", "progress", "--id", work_id]
        try:
            proc = self.runner(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=APPLY_TIMEOUT_SEC,
                check=False,
            )
        except Exception:
            return None
        if int(getattr(proc, "returncode", 1) or 0) != 0:
            return None
        return _parse_json(getattr(proc, "stdout", "") or "")


def http_hook_from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: HttpTransport | None = None,
) -> LabDslHttpHook | None:
    source = os.environ if env is None else env
    base = ctl_http_base_from_env(source)
    if base is None:
        return None
    return LabDslHttpHook(
        base,
        transport=transport,
        bearer=bearer_from_env(source),
        ctl=resolve_ctl_kind(source, origin=base),
    )


def apply_hook_from_env(
    env: Mapping[str, str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> LabDslApplyHook | None:
    source = os.environ if env is None else env
    root = str(source.get(ENV_RUNTIME_ROOT) or "").strip()
    if not root:
        return None
    return LabDslApplyHook(root, runner=runner)


def progress_hook_from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: HttpTransport | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> DurableProgress | None:
    """Prefer loopback ctl HTTP; else local apply. None → inert stub."""
    http_hook = http_hook_from_env(env, transport=transport)
    if http_hook is not None:
        return http_hook
    return apply_hook_from_env(env, runner=runner)


def describe_progress_hook(hook: DurableProgress | None) -> dict[str, Any]:
    """Honest /v0/info label. No pretend when inert."""
    if hook is None or isinstance(hook, InertProgressHook):
        return {
            "kind": HOOK_KIND_INERT,
            "durable_path": False,
            "adapter": type(hook).__name__ if hook is not None else "none",
            "guest_to_mesh_ctl": False,
            "north_star_done": False,
            "note": (
                "Default hook is inert. Fail-closed without "
                "PANORAMIX_CTL_HTTP or PANORAMIX_RUNTIME_ROOT. "
                "Stub omits progress. Never invent percent."
            ),
        }
    if isinstance(hook, LabDslHttpHook):
        return {
            "kind": HOOK_KIND_CTL_HTTP,
            "durable_path": True,
            "adapter": "LabDslHttpHook",
            "ctl": hook.ctl,
            "ctl_http": hook.base_url,
            "verbs": ["progress"],
            "guest_to_mesh_ctl": False,
            "north_star_done": False,
            "note": (
                "Durable path via loopback local-dsl ctl HTTP "
                "(GET /dsl/progress). Omit when the verb reports "
                "nothing. Never invent percent. Not guest→mesh ctl."
            ),
        }
    if isinstance(hook, LabDslApplyHook):
        return {
            "kind": HOOK_KIND_CTL_APPLY,
            "durable_path": True,
            "adapter": "LabDslApplyHook",
            "ctl": "dsl",
            "verbs": ["progress"],
            "guest_to_mesh_ctl": False,
            "north_star_done": False,
            "note": (
                "Durable path via local runtime.apply dsl progress. "
                "Omit when missing. Never invent percent. "
                "Not guest→mesh ctl."
            ),
        }
    return {
        "kind": HOOK_KIND_CTL_APPLY,
        "durable_path": True,
        "adapter": type(hook).__name__,
        "guest_to_mesh_ctl": False,
        "north_star_done": False,
        "note": (
            "Injected durable progress hook. Surface stage/fraction/"
            "elapsed only when the hook reports them. Never invent percent."
        ),
    }


def project_hook_progress(raw: Any) -> dict[str, Any] | None:
    """Same honesty as ``honest_progress`` — None means omit."""
    return honest_progress(raw)
