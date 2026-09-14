"""Specs catalog (G2) — platform.ts intention, no Getafix.

Day-one rows match getafix-seed-paul dsl-backend/src/platform.ts:
sos / reserve / sos-lite / qa-reserve. YAML on disk is a thin stub
or seed-file pointer — not a dsl-work / CuPy lift.

GET serves the overlay when one exists, else the catalog stub.
PUT writes a process-local overlay (gone on restart). Catalog files
are never mutated. No Cognito. No S3. No Getafix fold.

Save rules (documented; enforced here):
- no empty / whitespace-only content
- no sticky Untitled name (visual cue only; omit name to keep the row title)
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dsl.errors import (
    CatalogReadOnly,
    EmptyContent,
    InvalidSpecId,
    SpecNotFound,
    StickyUntitled,
)
from dsl.handoff import reject_smuggle

CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalog"
SPEC_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
UNTITLED_RE = re.compile(
    r"^untitled(?:\s+spec(?:ification)?)?\.?$",
    re.IGNORECASE,
)

# Same four ids as platform.ts SPEC_CATALOG (full day-one set, not a subset).
CATALOG_ROWS: tuple[dict[str, str], ...] = (
    {
        "id": "sos",
        "name": "SOS",
        "description": "Stochastic-on-Stochastic (fixtures/data_in/SOS)",
        "file": "sos.yaml",
        "entity": "SOS",
        "seed_file": "spec_sos.yaml",
    },
    {
        "id": "reserve",
        "name": "RESERVE IFRS17",
        "description": "Reserve IFRS17 (fixtures/data_in/RESERVE)",
        "file": "reserve.yaml",
        "entity": "RESERVE",
        "seed_file": "spec_reserve_ifrs17.yaml",
    },
    {
        "id": "sos-lite",
        "name": "SOS lite",
        "description": "SOS with smaller outer loops",
        "file": "sos-lite.yaml",
        "entity": "SOS",
        "seed_file": "spec_sos_lite_t_outer_101_s_outer_100.yaml",
    },
    {
        "id": "qa-reserve",
        "name": "QA RESERVE IFRS17",
        "description": "Compare data_out/RESERVE to data_expected/RESERVE",
        "file": "qa-reserve.yaml",
        "entity": "RESERVE",
        "seed_file": "qa_reserve_ifrs17.yaml",
    },
)
CATALOG_IDS = tuple(row["id"] for row in CATALOG_ROWS)


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def safe_spec_id(spec_id: str) -> str:
    name = (spec_id or "").strip()
    if not SPEC_ID_RE.fullmatch(name):
        raise InvalidSpecId(spec_id)
    return name


def is_sticky_untitled(name: str) -> bool:
    return bool(UNTITLED_RE.fullmatch((name or "").strip()))


@dataclass
class Overlay:
    content: str
    name: str | None = None
    description: str | None = None
    updated_at: str = ""
    version: int = 2


@dataclass
class CatalogStore:
    """In-memory overlay over on-disk catalog stubs. One process; gone on restart."""

    catalog_dir: Path = CATALOG_DIR
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _overlays: dict[str, Overlay] = field(default_factory=dict, repr=False)
    _clock: Callable[[], str] = field(default=utcnow, repr=False)

    def rows(self) -> list[dict[str, str]]:
        """Catalog rows whose stub file exists (platform.ts existingSpecs)."""
        out: list[dict[str, str]] = []
        for row in CATALOG_ROWS:
            if (self.catalog_dir / row["file"]).is_file():
                out.append(dict(row))
        return out

    def list(self) -> dict[str, Any]:
        items = [self._list_item(row) for row in self.rows()]
        return {
            "folders": [],
            "items": items,
            "total_count": len(items),
            "current_folder": "",
        }

    def folders(self) -> dict[str, Any]:
        return {"folders": []}

    def get(self, spec_id: str) -> dict[str, Any]:
        row, overlay, content = self._payload(spec_id)
        storage = self._storage(row, overlay)
        name = overlay.name if overlay and overlay.name else row["name"]
        description = (
            overlay.description
            if overlay and overlay.description
            else row["description"]
        )
        version = overlay.version if overlay else 1
        updated = overlay.updated_at if overlay and overlay.updated_at else None
        return {
            "id": row["id"],
            "name": name,
            "description": description,
            "file": row["file"],
            "entity": row["entity"],
            "seed_file": row["seed_file"],
            "version": version,
            "status": "published",
            "content": content,
            "storage": storage,
            "updated_at": updated,
        }

    def yaml(self, spec_id: str) -> dict[str, Any]:
        row, overlay, content = self._payload(spec_id)
        return {"yaml": content, "storage": self._storage(row, overlay)}

    def save(self, spec_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """PUT overlay. Does not mutate catalog stubs."""
        if not isinstance(body, dict):
            raise EmptyContent()
        reject_smuggle(body)
        row = self._row(spec_id)
        content = self._content_of(body)
        if not content.strip():
            raise EmptyContent()
        name = self._optional_text(body, "name")
        if name is not None and is_sticky_untitled(name):
            raise StickyUntitled(name)
        description = self._optional_text(body, "description")
        now = self._clock()
        with self._lock:
            previous = self._overlays.get(row["id"])
            version = (previous.version + 1) if previous else 2
            self._overlays[row["id"]] = Overlay(
                content=content,
                name=name,
                description=description,
                updated_at=now,
                version=version,
            )
        return self.get(row["id"])

    def refuse_create(self) -> None:
        raise CatalogReadOnly(
            "day-one specs are the in-guest catalog; POST create is refused"
        )

    def refuse_delete(self, spec_id: str) -> None:
        self._row(spec_id)
        raise CatalogReadOnly(
            "catalog rows are not deleted; clear an overlay by restarting the process"
        )

    def _row(self, spec_id: str) -> dict[str, str]:
        sid = safe_spec_id(spec_id)
        for row in self.rows():
            if row["id"] == sid:
                return row
        raise SpecNotFound(sid)

    def _stub_text(self, row: dict[str, str]) -> str:
        path = self.catalog_dir / row["file"]
        return path.read_text(encoding="utf-8")

    def _payload(self, spec_id: str) -> tuple[dict[str, str], Overlay | None, str]:
        row = self._row(spec_id)
        with self._lock:
            overlay = self._overlays.get(row["id"])
            if overlay is None:
                return row, None, self._stub_text(row)
            return row, Overlay(
                content=overlay.content,
                name=overlay.name,
                description=overlay.description,
                updated_at=overlay.updated_at,
                version=overlay.version,
            ), overlay.content

    def _list_item(self, row: dict[str, str]) -> dict[str, Any]:
        with self._lock:
            overlay = self._overlays.get(row["id"])
        name = overlay.name if overlay and overlay.name else row["name"]
        description = (
            overlay.description
            if overlay and overlay.description
            else row["description"]
        )
        return {
            "id": row["id"],
            "name": name,
            "description": description,
            "folder": "",
            "version": overlay.version if overlay else 1,
            "status": "published",
            "updated_at": overlay.updated_at if overlay else None,
            "overlay": overlay is not None,
        }

    def _storage(self, row: dict[str, str], overlay: Overlay | None) -> dict[str, Any]:
        if overlay is None:
            return {
                "stage": "guest-local",
                "backend": "catalog",
                "overlay": False,
                "path": f"catalog/{row['file']}",
            }
        return {
            "stage": "guest-local",
            "backend": "memory",
            "overlay": True,
        }

    @staticmethod
    def _content_of(body: dict[str, Any]) -> str:
        if "content" in body:
            raw = body.get("content")
        elif "yaml" in body:
            raw = body.get("yaml")
        else:
            raw = ""
        if raw is None:
            return ""
        if not isinstance(raw, str):
            raise EmptyContent()
        return raw

    @staticmethod
    def _optional_text(body: dict[str, Any], key: str) -> str | None:
        if key not in body:
            return None
        raw = body.get(key)
        if raw is None:
            return None
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        return text or None
