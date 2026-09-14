"""Files browse (G5) — dsl-gui FilesPage intention, read-first.

Tabs: specs / data / results. Specs pair with the G2 catalog.
Data and results walk in-guest fixture stubs (not a dsl-work lift,
not CuPy, not S3 Shared/Group). Writes fail closed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from dsl.catalog import CATALOG_DIR, CatalogStore
from dsl.errors import (
    InvalidFileId,
    InvalidTab,
    LocationRefused,
    SpecNotFound,
    UnknownFile,
    WriteRefused,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "fixtures"
FILE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
TABS = ("specs", "data", "results")
DATA_ROOTS = ("data_in",)
RESULT_ROOTS = ("data_expected", "data_out")
REFUSED_LOCATIONS = frozenset({"shared", "group", "user", "s3", "aws"})
ALLOWED_LOCATIONS = frozenset({"", "guest-local", "all", "fixtures", "catalog"})
TEXT_PREVIEW_BYTES = 64 * 1024
WRITE_DETAIL = (
    "files browse is read-first; fixture and catalog paths are fail-closed "
    "(no upload / move / delete / Shared / Group)"
)


def safe_file_id(file_id: str) -> str:
    name = (file_id or "").strip()
    if not FILE_ID_RE.fullmatch(name):
        raise InvalidFileId(file_id)
    return name


def safe_tab(tab: str) -> str:
    name = (tab or "").strip().lower()
    if name not in TABS:
        raise InvalidTab(tab)
    return name


def check_location(raw: str) -> None:
    location = (raw or "").strip().lower()
    if location in REFUSED_LOCATIONS:
        raise LocationRefused(location)
    if location and location not in ALLOWED_LOCATIONS:
        raise LocationRefused(location)


def refuse_write() -> None:
    raise WriteRefused(WRITE_DETAIL)


def _file_id(kind: str, entity: str, filename: str) -> str:
    return f"{kind}-{entity.lower()}-{filename}"


def _kind_and_folder(rel: Path) -> tuple[str, str]:
    parts = rel.parts
    root = parts[0] if parts else ""
    if root == "data_in":
        return "in", str(Path(*parts[:-1])) if len(parts) > 1 else root
    if root == "data_expected":
        return "expected", str(Path(*parts[:-1])) if len(parts) > 1 else root
    if root == "data_out":
        return "out", str(Path(*parts[:-1])) if len(parts) > 1 else root
    return "file", str(Path(*parts[:-1])) if len(parts) > 1 else ""


def _entity_of(rel: Path) -> str:
    parts = rel.parts
    if len(parts) >= 2:
        return parts[1]
    return ""


def _is_text(path: Path, blob: bytes) -> bool:
    if b"\x00" in blob[:1024]:
        return False
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt", ".yaml", ".yml", ".json", ".md"}:
        return True
    try:
        blob.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


@dataclass
class FileBrowser:
    """Read-first browse over catalog stubs + fixture paths."""

    catalog: CatalogStore = field(default_factory=CatalogStore)
    fixtures_dir: Path = FIXTURES_DIR
    catalog_dir: Path = CATALOG_DIR

    def tabs(self) -> dict[str, Any]:
        specs = self.list("specs")
        data = self.list("data")
        results = self.list("results")
        return {
            "tabs": [
                {
                    "id": "specs",
                    "name": "Specifications",
                    "list": "GET /v0/files/specs",
                    "count": specs["total_count"],
                    "folders": len(specs["folders"]),
                },
                {
                    "id": "data",
                    "name": "Data",
                    "list": "GET /v0/files/data",
                    "count": data["total_count"],
                    "folders": len(data["folders"]),
                },
                {
                    "id": "results",
                    "name": "Results",
                    "list": "GET /v0/files/results",
                    "count": results["total_count"],
                    "folders": len(results["folders"]),
                },
            ],
            "locations": ["guest-local"],
            "writes": "refused",
            "shared_group": False,
            "s3": False,
            "ui": "/files",
            "note": (
                "G5 files browse. Intention of getafix-seed-paul dsl-gui "
                "FilesPage — read-first, not a code lift. Specs pair with G2. "
                "Data/results walk in-guest fixture stubs. Writes fail closed. "
                "No multi-tenant S3 Shared/Group. Live run artifacts wait for G4."
            ),
        }

    def list(
        self,
        tab: str,
        folder: str = "",
        location: str = "",
    ) -> dict[str, Any]:
        check_location(location)
        name = safe_tab(tab)
        folder = (folder or "").strip().strip("/")
        if name == "specs":
            items = self._spec_items()
            backend = "catalog"
        elif name == "data":
            items = self._fixture_items("data", DATA_ROOTS)
            backend = "fixtures"
        else:
            items = self._fixture_items("results", RESULT_ROOTS)
            backend = "fixtures"
        folders = self._folders(items)
        if folder:
            items = [item for item in items if item["folder"] == folder]
            folders = []
        return {
            "tab": name,
            "folders": folders,
            "items": items,
            "total_count": len(items),
            "current_folder": folder,
            "location": "guest-local",
            "storage": {
                "stage": "guest-local",
                "backend": backend,
                "overlay": False,
            },
            "writes": "refused",
            "shared_group": False,
            "s3": False,
        }

    def get(self, tab: str, file_id: str) -> dict[str, Any]:
        name = safe_tab(tab)
        sid = safe_file_id(file_id)
        if name == "specs":
            try:
                return self._spec_detail(sid)
            except SpecNotFound as exc:
                raise UnknownFile(sid, tab=name) from exc
        roots = DATA_ROOTS if name == "data" else RESULT_ROOTS
        for item in self._fixture_items(name, roots):
            if item["id"] == sid:
                return item
        raise UnknownFile(sid, tab=name)

    def text(self, tab: str, file_id: str) -> dict[str, Any]:
        item = self.get(tab, file_id)
        path = self._disk_path(item)
        if path is None:
            content = item.get("content") or ""
            return {
                "id": item["id"],
                "tab": item["tab"],
                "path": item["path"],
                "content": content,
                "encoding": "utf-8",
                "truncated": False,
                "bytes": len(content.encode("utf-8")),
                "storage": item.get("storage"),
            }
        blob = path.read_bytes()
        size = len(blob)
        truncated = size > TEXT_PREVIEW_BYTES
        peek = blob[:TEXT_PREVIEW_BYTES]
        if not _is_text(path, peek):
            return {
                "id": item["id"],
                "tab": item["tab"],
                "path": item["path"],
                "content": None,
                "encoding": "binary",
                "truncated": truncated,
                "bytes": size,
                "storage": item.get("storage"),
            }
        return {
            "id": item["id"],
            "tab": item["tab"],
            "path": item["path"],
            "content": peek.decode("utf-8"),
            "encoding": "utf-8",
            "truncated": truncated,
            "bytes": size,
            "storage": item.get("storage"),
        }

    def download(self, tab: str, file_id: str) -> tuple[str, bytes, str]:
        item = self.get(tab, file_id)
        path = self._disk_path(item)
        if path is None:
            content = (item.get("content") or "").encode("utf-8")
            return item.get("filename") or f"{item['id']}.yaml", content, "text/yaml"
        blob = path.read_bytes()
        suffix = path.suffix.lower()
        types = {
            ".csv": "text/csv; charset=utf-8",
            ".txt": "text/plain; charset=utf-8",
            ".yaml": "text/yaml; charset=utf-8",
            ".yml": "text/yaml; charset=utf-8",
            ".json": "application/json",
        }
        return path.name, blob, types.get(suffix, "application/octet-stream")

    def _spec_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.catalog.rows():
            items.append(self._spec_item(row["id"]))
        return items

    def _spec_item(self, spec_id: str) -> dict[str, Any]:
        spec = self.catalog.get(spec_id)
        content = spec.get("content") or ""
        return {
            "type": "file",
            "id": spec["id"],
            "name": spec["name"],
            "filename": spec["file"],
            "path": f"catalog/{spec['file']}",
            "folder": "catalog",
            "tab": "specs",
            "entity": spec.get("entity"),
            "size_bytes": len(content.encode("utf-8")),
            "overlay": spec["storage"].get("overlay", False),
            "open": f"/?spec={spec['id']}",
            "updated_at": spec.get("updated_at"),
            "location": "guest-local",
            "storage": spec["storage"],
        }

    def _spec_detail(self, spec_id: str) -> dict[str, Any]:
        item = self._spec_item(spec_id)
        spec = self.catalog.get(spec_id)
        item["content"] = spec.get("content") or ""
        item["description"] = spec.get("description")
        item["seed_file"] = spec.get("seed_file")
        return item

    def _fixture_items(self, tab: str, roots: tuple[str, ...]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        base = self.fixtures_dir.resolve()
        for root_name in roots:
            root = (self.fixtures_dir / root_name).resolve()
            try:
                root.relative_to(base)
            except ValueError:
                continue
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                resolved = path.resolve()
                try:
                    resolved.relative_to(base)
                except ValueError:
                    continue
                rel = resolved.relative_to(base)
                kind, folder = _kind_and_folder(rel)
                entity = _entity_of(rel)
                stat = resolved.stat()
                items.append(
                    {
                        "type": "file",
                        "id": _file_id(kind, entity, resolved.name),
                        "name": resolved.name,
                        "filename": resolved.name,
                        "path": f"fixtures/{rel.as_posix()}",
                        "folder": folder.replace("\\", "/"),
                        "tab": tab,
                        "entity": entity,
                        "size_bytes": stat.st_size,
                        "overlay": False,
                        "updated_at": None,
                        "location": "guest-local",
                        "storage": {
                            "stage": "guest-local",
                            "backend": "fixtures",
                            "overlay": False,
                        },
                    }
                )
        return items

    def _folders(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in items:
            folder = item.get("folder") or ""
            if not folder:
                continue
            counts[folder] = counts.get(folder, 0) + 1
        out: list[dict[str, Any]] = []
        for path in sorted(counts):
            out.append(
                {
                    "type": "folder",
                    "name": path.rsplit("/", 1)[-1],
                    "path": path,
                    "file_count": counts[path],
                    "location": "guest-local",
                }
            )
        return out

    def _disk_path(self, item: dict[str, Any]) -> Path | None:
        rel = item.get("path") or ""
        if rel.startswith("catalog/"):
            candidate = (self.catalog_dir / rel[len("catalog/") :]).resolve()
            try:
                candidate.relative_to(self.catalog_dir.resolve())
            except ValueError:
                return None
            if item.get("storage", {}).get("overlay"):
                return None
            return candidate if candidate.is_file() else None
        if rel.startswith("fixtures/"):
            candidate = (self.fixtures_dir / rel[len("fixtures/") :]).resolve()
            try:
                candidate.relative_to(self.fixtures_dir.resolve())
            except ValueError:
                return None
            return candidate if candidate.is_file() else None
        return None


def location_from_query(query: dict[str, list[str]] | None) -> str:
    if not query:
        return ""
    values = query.get("location") or []
    return values[0] if values else ""


def folder_from_query(query: dict[str, list[str]] | None) -> str:
    if not query:
        return ""
    values = query.get("folder") or []
    return values[0] if values else ""
