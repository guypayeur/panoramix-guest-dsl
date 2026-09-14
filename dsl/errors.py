"""Domain errors with stable JSON ``error`` codes."""

from __future__ import annotations

from typing import Any

from dsl.handoff_vocab import LOCAL_DEMOS, RESOURCE_CLASSES, WORK_KINDS, WORK_STATUSES


class DslError(Exception):
    """Domain error with a stable JSON `error` code."""

    http_status = 400

    def __init__(self, error: str, **fields: Any) -> None:
        self.error = error
        self.fields = fields
        super().__init__(error)

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error, **self.fields}


class EngineSmuggle(DslError):
    def __init__(self, detail: str) -> None:
        super().__init__("engine_smuggle", detail=detail)


class InvalidHandoff(DslError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_handoff", detail=detail)


class InvalidKind(DslError):
    def __init__(self, kind: str, *, detail: str | None = None) -> None:
        fields: dict[str, Any] = {"kind": kind, "allowed": sorted(WORK_KINDS)}
        if detail:
            fields["detail"] = detail
        super().__init__("invalid_kind", **fields)


class InvalidClass(DslError):
    def __init__(self, resource_class: str, *, detail: str | None = None) -> None:
        fields: dict[str, Any] = {
            "class": resource_class,
            "allowed": sorted(RESOURCE_CLASSES),
        }
        if detail:
            fields["detail"] = detail
        super().__init__("invalid_class", **fields)


class InvalidDigest(DslError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_digest", detail=detail)


class InvalidDemo(DslError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            "invalid_demo",
            detail=detail,
            allowed=sorted(LOCAL_DEMOS),
        )


class InvalidStatus(DslError):
    def __init__(self, status: str) -> None:
        super().__init__(
            "invalid_status",
            status=status,
            allowed=list(WORK_STATUSES),
            detail=(
                "Job list filter uses real job.status only "
                "(queued/running/succeeded/failed/canceled). "
                "Unknown values such as accepted or cancelled are rejected. "
                "paused/held are not on this stub (no durable hook)."
            ),
        )


class JobNotFound(DslError):
    http_status = 404

    def __init__(self, job_id: str) -> None:
        super().__init__("not_found", id=job_id)


class PayloadUnknown(DslError):
    http_status = 404

    def __init__(self, job_id: str) -> None:
        super().__init__(
            "payload_unknown",
            id=job_id,
            detail=(
                "opaque submit recorded payload_digest only; "
                "demo shortcuts store canonical JSON bytes for ctl export"
            ),
        )


class AlreadyTerminal(DslError):
    http_status = 409

    def __init__(self, job_id: str, status: str) -> None:
        super().__init__("already_terminal", id=job_id, status=status)
