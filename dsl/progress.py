"""G13 durable progress + G15 live local-dsl admit (same env hook).

Opt-in only. Default is inert: the G1 stub runner still omits
``progress`` and still digests ``demo:dsl`` locally. When an operator
installs ``PANORAMIX_CTL_HTTP`` (loopback ctl HTTP, local-dsl verbs on
port **19217**) or ``PANORAMIX_RUNTIME_ROOT``
(``python3 -m runtime.apply dsl progress``), this guest projects
**reported** ``stage`` / ``fraction`` / ``elapsed`` onto run detail.

G15 extends the same sanctioned hook: when ``PANORAMIX_RUNTIME_ROOT``
and a host engine checkout (``PANORAMIX_DSL_WORK_ROOT`` / aliases)
are set, matching R2 catalog submits call
``python3 -m runtime.apply --binding <local-dsl|local-dsl-gpu>
dsl admit --live``. Walls / BEL are copied only when apply returns
them. Missing engine env keeps today's stub — never invent walls.

Transport stays operator/ctl-mediated. Guest does not open mesh ctl,
does not call ``runtime.apply`` unless the operator pointed
``PANORAMIX_RUNTIME_ROOT`` at a local checkout, and does not invent a
percent from fraction or walls. Recorded local-dsl progress often
ships ``fraction: null`` — that stays omitted.

Not G12 submit fields. Not Batch ECG / Watchdog. Not a dsl-work /
CuPy vendor. Epic #1 remains open. Cloud stays locked.
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
ENV_DSL_WORK_ROOT = "PANORAMIX_DSL_WORK_ROOT"
ENV_DSL_ENGINE_ROOT = "PANORAMIX_DSL_ENGINE_ROOT"
ENV_DSL_ENGINE_PYTHON = "PANORAMIX_DSL_ENGINE_PYTHON"
ENV_DSL_ENGINE_TIMEOUT = "PANORAMIX_DSL_ENGINE_TIMEOUT"
ENV_DSL_BINDING = "PANORAMIX_DSL_BINDING"
ENV_DSL_BINDING_CPU = "PANORAMIX_DSL_BINDING_CPU"
ENV_DSL_BINDING_GPU = "PANORAMIX_DSL_BINDING_GPU"

# Same checkout aliases as panoramix-runtime runtime/dsl_local.py.
CHECKOUT_ENVS = (
    ENV_DSL_WORK_ROOT,
    ENV_DSL_ENGINE_ROOT,
    "DSL_ENGINE_ROOT",
    "GETAFIX_DSL_WORK",
)

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
DEFAULT_ADMIT_TIMEOUT_SEC = 1800.0
BINDING_CPU = "bindings/local-dsl.example.yaml"
BINDING_GPU = "bindings/local-dsl-gpu.example.yaml"
ENGINE_ABSENT = "DSL_ENGINE_ABSENT"

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


def engine_checkout_from_env(env: Mapping[str, str] | None = None) -> str | None:
    """Host path to dsl-work (or repo root). None → live admit stays stub."""
    source = os.environ if env is None else env
    for key in CHECKOUT_ENVS:
        raw = str(source.get(key) or "").strip()
        if raw:
            return raw
    return None


def runtime_root_from_env(env: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    raw = str(source.get(ENV_RUNTIME_ROOT) or "").strip()
    return raw or None


def live_admit_ready(env: Mapping[str, str] | None = None) -> bool:
    """G15: runtime checkout + engine root. Missing either keeps the stub."""
    return runtime_root_from_env(env) is not None and engine_checkout_from_env(env) is not None


def binding_for_class(
    resource_class: str | None, env: Mapping[str, str] | None = None
) -> str:
    """cpu → local-dsl; gpu → local-dsl-gpu. Env may override the path."""
    source = os.environ if env is None else env
    explicit = str(source.get(ENV_DSL_BINDING) or "").strip()
    if explicit:
        return explicit
    cls = str(resource_class or "cpu").strip().lower()
    if cls == "gpu":
        return str(source.get(ENV_DSL_BINDING_GPU) or "").strip() or BINDING_GPU
    return str(source.get(ENV_DSL_BINDING_CPU) or "").strip() or BINDING_CPU


def admit_timeout_sec(env: Mapping[str, str] | None = None) -> float:
    source = os.environ if env is None else env
    raw = str(source.get(ENV_DSL_ENGINE_TIMEOUT) or "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            value = 0.0
        if value > 0:
            return value
    return DEFAULT_ADMIT_TIMEOUT_SEC


def admit_engine_absent(raw: Any) -> bool:
    """True when apply never invoked the host engine (keep stub)."""
    if raw is None:
        return True
    if isinstance(raw, dict):
        if raw.get("ok") is True and raw.get("executed") is True:
            return False
        err = str(raw.get("error") or raw.get("reason") or "")
        if raw.get("ok") is True and raw.get("executed") is not True:
            return True
    else:
        err = str(raw)
    upper = err.upper()
    return ENGINE_ABSENT in upper or "ENGINE_ABSENT" in upper


def runtime_id_from_admit(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    for key in ("id", "runtime_id", "cw_id"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    work = raw.get("work")
    if isinstance(work, dict):
        value = work.get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
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

    def admit(
        self,
        *,
        catalog: str,
        resource_class: str,
        live: bool = True,
    ) -> dict[str, Any] | None:
        """POST ``/dsl/admit`` on loopback ctl (same verb table as apply)."""
        qs = urlencode(
            {
                "catalog": catalog,
                "class": resource_class,
                "live": "1" if live else "0",
            }
        )
        url = urlunsplit(
            ("http", urlsplit(self.base_url).netloc, f"{self.prefix}/admit", qs, "")
        )
        try:
            code, stdout = self.transport("POST", url, self._headers(), None)
        except TypeError:
            try:
                code, stdout = self.transport(
                    "POST", url, self._headers(), None, timeout=admit_timeout_sec()
                )
            except Exception:
                return None
        except Exception:
            return None
        payload = _parse_json(stdout)
        if payload is None:
            return None if not (200 <= int(code) < 300) else None
        if "ok" not in payload:
            payload["ok"] = 200 <= int(code) < 300
        payload.setdefault("catalog", catalog)
        payload.setdefault("class", resource_class)
        payload.setdefault("live", bool(live))
        return payload


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
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.root = str(root)
        self.runner = runner or subprocess.run
        self.python = python or sys.executable
        self.env = dict(env) if env is not None else None

    def __call__(self, job: Any) -> dict[str, Any] | None:
        return self.progress(job)

    def _run(
        self,
        cmd: list[str],
        *,
        timeout: float,
    ) -> dict[str, Any] | None:
        try:
            proc = self.runner(
                cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except Exception:
            return None
        stdout = getattr(proc, "stdout", "") or ""
        stderr = getattr(proc, "stderr", "") or ""
        payload = _parse_json(stdout)
        if payload is not None:
            if "ok" not in payload:
                payload["ok"] = int(getattr(proc, "returncode", 1) or 0) == 0
            return payload
        if int(getattr(proc, "returncode", 1) or 0) == 0:
            return None
        text = (stderr or stdout).strip()
        return {"ok": False, "error": text or "runtime.apply failed"}

    def progress(self, job: Any) -> dict[str, Any] | None:
        work_id = work_id_for(job)
        if work_id is None:
            return None
        cmd = [self.python, "-m", "runtime.apply", "dsl", "progress", "--id", work_id]
        payload = self._run(cmd, timeout=APPLY_TIMEOUT_SEC)
        if payload is None or payload.get("ok") is False:
            return None
        return payload

    def admit(
        self,
        *,
        catalog: str,
        resource_class: str,
        live: bool = True,
    ) -> dict[str, Any] | None:
        """``runtime.apply --binding … dsl admit --live --catalog --class``."""
        binding = binding_for_class(resource_class, self.env)
        cmd = [
            self.python,
            "-m",
            "runtime.apply",
            "--binding",
            binding,
            "dsl",
            "admit",
        ]
        if live:
            cmd.append("--live")
        cmd.extend(["--catalog", catalog, "--class", resource_class])
        payload = self._run(cmd, timeout=admit_timeout_sec(self.env))
        if isinstance(payload, dict):
            payload.setdefault("binding", binding)
            payload.setdefault("catalog", catalog)
            payload.setdefault("class", resource_class)
            payload.setdefault("live", bool(live))
        return payload


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
    return LabDslApplyHook(root, runner=runner, env=source)


def admit_hook_from_env(
    env: Mapping[str, str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> LabDslApplyHook | None:
    """G15 live admit. Requires runtime root + engine checkout. Else None."""
    if not live_admit_ready(env):
        return None
    return apply_hook_from_env(env, runner=runner)


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
            "verbs": ["progress", "admit"],
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
            "verbs": ["progress", "admit"],
            "bindings": {"cpu": BINDING_CPU, "gpu": BINDING_GPU},
            "guest_to_mesh_ctl": False,
            "north_star_done": False,
            "note": (
                "Durable path via local runtime.apply dsl progress. "
                "G15 live admit uses the same hook when "
                "PANORAMIX_DSL_WORK_ROOT is also set "
                "(cpu → local-dsl, gpu → local-dsl-gpu). "
                "Omit walls/BEL when missing. Never invent percent. "
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
