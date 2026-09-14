"""Opaque work handoff aligned with panoramix-runtime WorkHandoff.

Hard reference: runtime/compute_work.py on panoramix-runtime main.
Guest emits WorkHandoff JSON only (kind/class/payload_digest + status/id).
Does not open guest→mesh ctl. runtime.apply is G13/G15 only when
PANORAMIX_RUNTIME_ROOT is set (not this parser).
Local echo/sleep/dsl demos synthesize the opaque shape. demo:dsl
digests a tiny catalog stub — not NSM/CuPy math. Does not close epic #1.
Does not unlock #61 / #29.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from dsl.errors import (
    EngineSmuggle,
    InvalidClass,
    InvalidDemo,
    InvalidDigest,
    InvalidHandoff,
    InvalidKind,
)
from dsl.handoff_vocab import (
    DEFAULT_ECHO_MESSAGE,
    DEFAULT_SLEEP_SECONDS,
    DEMO_DSL,
    DEMO_ECHO,
    DEMO_SLEEP,
    DSL_CATALOG_ALL,
    DSL_STUB_CATALOG,
    LOCAL_DEMOS,
    MAX_SLEEP_SECONDS,
    RESOURCE_CLASSES,
    WORK_KINDS,
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEAM_KEYS = frozenset({"kind", "class", "payload_digest"})
ECHO_DEMO_KEYS = frozenset({"demo", "message"})
SLEEP_DEMO_KEYS = frozenset({"demo", "seconds"})
DSL_DEMO_KEYS = frozenset(
    {
        "demo",
        "catalog",
        "class",
        "accounts",
        "precision",
        "overrides",
        "variable_overrides",
    }
)
HANDOFF_EXPORT_KEYS = ("id", "kind", "class", "payload_digest", "status")

# Schemes / prefixes that would smuggle an engine URL into the seam.
ENGINE_SCHEMES = (
    "ray:",
    "temporal:",
    "aws:",
    "s3:",
    "iec:",
    "podman:",
    "docker:",
    "image:",
    "firecracker:",
    "anyscale:",
    "gke:",
    "ecs:",
    "compute:",
)
ENGINE_BRAND_KEYS = frozenset(
    {
        "ray",
        "temporal",
        "aws",
        "iec",
        "iec-proto-c",
        "iec_proto_c",
        "podman",
        "docker",
        "image",
        "firecracker",
        "gke",
        "ecs",
        "s3",
        "anyscale",
        "engine",
        "engine_kind",
        "engine_url",
        "ray_address",
        "ray_namespace",
        "temporal_host",
        "temporal_namespace",
        "workflow_id",
        "task_queue",
        "cluster_url",
        "payload",
        "url",
        "uri",
        "endpoint",
        "address",
    }
)
_BRAND_KEYS_COMPACT = frozenset(k.replace("_", "") for k in ENGINE_BRAND_KEYS)


def _norm_key(key: Any) -> str:
    return str(key or "").strip().lower().replace("-", "_")


def _engine_scheme_in(text: str) -> str | None:
    raw = str(text or "")
    lower = raw.lower()
    for scheme in ENGINE_SCHEMES:
        if scheme in lower:
            return scheme
    if "://" in raw:
        return "://"
    return None


def _reject_smuggled_text(text: str, *, where: str) -> None:
    hit = _engine_scheme_in(text)
    if hit:
        raise EngineSmuggle(
            f"{where} smuggles engine URL/schema {hit!r} "
            "(guest seam is kind/class/payload_digest; engines stay in runtime bindings)"
        )


def reject_smuggle(obj: Any, *, where: str = "body") -> None:
    """Refuse engine brand keys and URL schemes anywhere in the request."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            nk = _norm_key(key)
            if nk in ENGINE_BRAND_KEYS or nk.replace("_", "") in _BRAND_KEYS_COMPACT:
                raise EngineSmuggle(
                    f"{where} field {key!r} is an engine brand/schema "
                    "(not guest-facing; engines in runtime bindings only)"
                )
            _reject_smuggled_text(str(key), where=f"{where} key")
            reject_smuggle(val, where=f"{where}.{key}")
        return
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            reject_smuggle(item, where=f"{where}[{i}]")
        return
    if isinstance(obj, str):
        _reject_smuggled_text(obj, where=where)


@dataclass(frozen=True)
class ParsedSubmit:
    """Admitted submit: opaque seam fields plus optional stored payload bytes."""

    kind: str
    resource_class: str
    payload_digest: str
    local: dict[str, Any] | None = None
    payload_bytes: bytes | None = None


def canonical_json_bytes(payload: Any) -> bytes:
    """Canonical JSON bytes (same rules as runtime digest_payload for mappings)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest_bytes(blob: bytes) -> str:
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def digest_canonical(payload: Any) -> str:
    """sha256 of canonical JSON (same separators as runtime digest_payload)."""
    return digest_bytes(canonical_json_bytes(payload))


def payload_export(digest: str, blob: bytes) -> dict[str, Any]:
    """Ctl-facing payload record. No ``payload`` key (runtime submit rejects it)."""
    return {
        "payload_digest": digest,
        "hex": blob.hex(),
        "utf8": blob.decode("utf-8"),
        "encoding": "canonical-json",
    }


def catalog_snapshot() -> dict[str, dict[str, Any]]:
    """Copy of the tiny demo:dsl catalog (stable key order for digest)."""
    return {key: dict(DSL_STUB_CATALOG[key]) for key in sorted(DSL_STUB_CATALOG)}


def _canon_seconds(seconds: float) -> int | float:
    if seconds == int(seconds):
        return int(seconds)
    return float(seconds)


def _demo_allowed_keys(demo: str) -> frozenset[str]:
    if demo == DEMO_ECHO:
        return ECHO_DEMO_KEYS
    if demo == DEMO_SLEEP:
        return SLEEP_DEMO_KEYS
    return DSL_DEMO_KEYS


def _parse_optional_class(body: dict[str, Any]) -> str:
    if "class" not in body:
        return "cpu"
    class_raw = body.get("class")
    cls = str(class_raw or "").strip().lower() if isinstance(class_raw, str) else ""
    if cls not in RESOURCE_CLASSES:
        raise InvalidClass(class_raw if isinstance(class_raw, str) else type(class_raw).__name__)
    return cls


def parse_dsl_demo(body: dict[str, Any]) -> ParsedSubmit:
    """Thin catalog-digest stub, or G12 R2-shaped digest when dialog fields land.

    Without accounts/precision/overrides the G1 stub digest is unchanged.
    With those fields the guest copies the R2 payload shape so matching
    params emit the runtime R2/R3 catalog digest. Not NSM. Not CuPy.
    """
    from dsl.runs import resolve_submit_options, submit_options_present

    catalog_raw = body.get("catalog", DSL_CATALOG_ALL)
    if not isinstance(catalog_raw, str):
        raise InvalidDemo("dsl catalog must be a string")
    catalog = catalog_raw.strip().lower()
    if catalog in {"", DSL_CATALOG_ALL, "*"}:
        work: dict[str, Any] = {"demo": DEMO_DSL, "catalog": catalog_snapshot()}
        local: dict[str, Any] = {
            "demo": DEMO_DSL,
            "catalog": DSL_CATALOG_ALL,
            "ids": sorted(DSL_STUB_CATALOG),
            "nsm": False,
            "cupy": False,
        }
    elif catalog in DSL_STUB_CATALOG:
        entry = dict(DSL_STUB_CATALOG[catalog])
        work = {"demo": DEMO_DSL, "catalog": catalog, "entry": entry}
        local = {
            "demo": DEMO_DSL,
            "catalog": catalog,
            "nsm": False,
            "cupy": False,
        }
    else:
        raise InvalidDemo(
            "dsl catalog must be all or one of "
            f"{sorted(DSL_STUB_CATALOG)} (got {catalog_raw!r})"
        )
    cls = _parse_optional_class(body)
    if submit_options_present(body):
        if catalog not in DSL_STUB_CATALOG:
            raise InvalidDemo(
                "submit dialog accounts/precision/overrides need a catalog row "
                f"(got {catalog_raw!r})"
            )
        options = resolve_submit_options(catalog, body)
        work = options.payload()
        local.update(options.to_local())
        local["catalog"] = catalog
        local["demo"] = DEMO_DSL
    blob = canonical_json_bytes(work)
    local["class"] = cls
    return ParsedSubmit(
        kind="job",
        resource_class=cls,
        payload_digest=digest_bytes(blob),
        local=local,
        payload_bytes=blob,
    )


def parse_demo(body: dict[str, Any]) -> ParsedSubmit:
    """Local-only shortcut → synthesized job + digest + stub metadata."""
    demo = body.get("demo")
    if not isinstance(demo, str) or demo.strip().lower() not in LOCAL_DEMOS:
        raise InvalidDemo(demo if isinstance(demo, str) else type(demo).__name__)
    demo = demo.strip().lower()
    extra = sorted(str(k) for k in body if str(k) not in _demo_allowed_keys(demo))
    if extra:
        raise InvalidHandoff(
            f"local demo refuses extra fields {extra} "
            "(echo: demo/message; sleep: demo/seconds; "
            "dsl: demo/catalog/class plus optional "
            "accounts/precision/overrides)"
        )
    if demo == DEMO_ECHO:
        message = body.get("message", DEFAULT_ECHO_MESSAGE)
        if not isinstance(message, str):
            raise InvalidDemo("echo message must be a string")
        canonical = {"demo": DEMO_ECHO, "message": message}
        blob = canonical_json_bytes(canonical)
        return ParsedSubmit(
            kind="job",
            resource_class="cpu",
            payload_digest=digest_bytes(blob),
            local={"demo": DEMO_ECHO, "message": message},
            payload_bytes=blob,
        )
    if demo == DEMO_SLEEP:
        seconds = body.get("seconds", DEFAULT_SLEEP_SECONDS)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise InvalidDemo("sleep seconds must be a non-negative number")
        if seconds < 0:
            raise InvalidDemo("sleep seconds must be a non-negative number")
        if seconds > MAX_SLEEP_SECONDS:
            raise InvalidDemo(f"sleep seconds must be <= {MAX_SLEEP_SECONDS:g}")
        canon_seconds = _canon_seconds(float(seconds))
        canonical = {"demo": DEMO_SLEEP, "seconds": canon_seconds}
        blob = canonical_json_bytes(canonical)
        return ParsedSubmit(
            kind="job",
            resource_class="cpu",
            payload_digest=digest_bytes(blob),
            local={"demo": DEMO_SLEEP, "seconds": canon_seconds},
            payload_bytes=blob,
        )
    return parse_dsl_demo(body)


def parse_handoff(body: dict[str, Any]) -> tuple[str, str, str]:
    """Admit an opaque WorkHandoff body. Reject extra keys and bad vocab."""
    extra = sorted(str(k) for k in body if str(k) not in SEAM_KEYS)
    if extra:
        raise InvalidHandoff(
            f"handoff refuses extra fields {extra} "
            "(guest shape is kind/class/payload_digest)"
        )
    if "kind" not in body:
        raise InvalidKind("", detail="kind is required")
    kind_raw = body.get("kind")
    kind = str(kind_raw or "").strip().lower() if isinstance(kind_raw, str) else ""
    if kind not in WORK_KINDS:
        raise InvalidKind(kind_raw if isinstance(kind_raw, str) else type(kind_raw).__name__)
    if "class" not in body:
        raise InvalidClass("", detail="class is required")
    class_raw = body.get("class")
    cls = str(class_raw or "").strip().lower() if isinstance(class_raw, str) else ""
    if cls not in RESOURCE_CLASSES:
        raise InvalidClass(class_raw if isinstance(class_raw, str) else type(class_raw).__name__)
    if "payload_digest" not in body:
        raise InvalidDigest("payload_digest is required")
    digest_raw = body.get("payload_digest")
    digest = str(digest_raw or "").strip().lower() if isinstance(digest_raw, str) else ""
    if not DIGEST_RE.fullmatch(digest):
        raise InvalidDigest("payload_digest must be sha256:<64 hex>")
    return kind, cls, digest


def parse_submit(body: dict[str, Any]) -> ParsedSubmit:
    """Route POST /v0/jobs: opaque seam or local demo shortcut."""
    if not isinstance(body, dict):
        raise InvalidHandoff("body must be a JSON object")
    reject_smuggle(body)
    if "demo" in body:
        return parse_demo(body)
    kind, cls, digest = parse_handoff(body)
    return ParsedSubmit(kind=kind, resource_class=cls, payload_digest=digest)
