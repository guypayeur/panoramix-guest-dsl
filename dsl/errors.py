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


class SpecNotFound(DslError):
    http_status = 404

    def __init__(self, spec_id: str) -> None:
        super().__init__("unknown_spec", id=spec_id)


class InvalidSpecId(DslError):
    def __init__(self, spec_id: str) -> None:
        super().__init__("invalid_spec_id", id=spec_id)


class EmptyContent(DslError):
    def __init__(self) -> None:
        super().__init__(
            "empty_content",
            detail=(
                "content is required; overlay save never persists empty "
                "or whitespace-only YAML (seed editor rule 0.0)"
            ),
        )


class StickyUntitled(DslError):
    def __init__(self, name: str) -> None:
        super().__init__(
            "sticky_untitled",
            name=name,
            detail=(
                "'Untitled' / 'Untitled Specification' is a visual cue, "
                "not a valid save name (seed editor rule 0.2). "
                "Omit name to keep the catalog row title."
            ),
        )


class CatalogReadOnly(DslError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            "catalog_readonly",
            detail=detail
            or (
                "day-one specs are the in-guest catalog; "
                "use PUT /v0/specs/{id} for an overlay"
            ),
        )


class WriteRefused(DslError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            "write_refused",
            detail=detail
            or (
                "files browse is read-first; fixture and catalog paths "
                "are fail-closed (no upload / move / delete / Shared / Group)"
            ),
        )


class UnknownFile(DslError):
    http_status = 404

    def __init__(self, file_id: str, *, tab: str | None = None) -> None:
        fields: dict[str, Any] = {"id": file_id}
        if tab:
            fields["tab"] = tab
        super().__init__("unknown_file", **fields)


class InvalidFileId(DslError):
    def __init__(self, file_id: str) -> None:
        super().__init__("invalid_file_id", id=file_id)


class InvalidTab(DslError):
    def __init__(self, tab: str) -> None:
        super().__init__(
            "invalid_tab",
            tab=tab,
            allowed=["specs", "data", "results"],
            detail="files tabs are specs / data / results",
        )


class LocationRefused(DslError):
    def __init__(self, location: str) -> None:
        super().__init__(
            "location_refused",
            location=location,
            allowed=["guest-local"],
            detail=(
                "day-one files browse is guest-local fixtures/catalog only; "
                "no multi-tenant S3 Shared / Group / user locations"
            ),
        )


class InvalidYaml(DslError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_yaml", detail=detail)


class InvalidGraph(DslError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_graph", detail=detail)


class Unauthorized(DslError):
    http_status = 401

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            "unauthorized",
            detail=detail
            or "Authorization: Bearer <accessToken> required",
        )


class InvalidCredentials(DslError):
    http_status = 401

    def __init__(self) -> None:
        super().__init__(
            "invalid_credentials",
            detail="invalid email or password",
        )


class MissingCredentials(DslError):
    def __init__(self) -> None:
        super().__init__(
            "missing_credentials",
            detail="email and password are required",
        )


class InvalidEmail(DslError):
    def __init__(self, email: str) -> None:
        super().__init__(
            "invalid_email",
            email=email,
            detail="a valid email is required",
        )


class WeakPassword(DslError):
    def __init__(self) -> None:
        super().__init__(
            "weak_password",
            detail="password must be at least 8 characters",
        )


class AccountExists(DslError):
    http_status = 409

    def __init__(self, email: str) -> None:
        super().__init__(
            "account_exists",
            email=email,
            detail="an account with that email already exists",
        )


class ChatUnavailable(DslError):
    http_status = 503

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            "chat_unavailable",
            detail=detail
            or (
                "ANTHROPIC_API_KEY is not configured. "
                "Set DSL_CHAT_STUB=1 for documented stub mode (tests / no model)."
            ),
        )


class InvalidChat(DslError):
    def __init__(self, detail: str) -> None:
        super().__init__("invalid_chat", detail=detail)


class ChatError(DslError):
    http_status = 502

    def __init__(self, detail: str) -> None:
        super().__init__("chat_error", detail=detail)
