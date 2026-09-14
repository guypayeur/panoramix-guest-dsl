"""Static G10 React Flow editor + G5 files page (GET / /ui /files).

Built assets live under ui/ (Vite bundle from editor/). Guest stays
runnable from platform_run.py with no npm at serve time. Rebuild:
``cd editor && npm install && npm run build``.
dsl-gui *feel*, not a getafix-seed-paul SPA lift. G8 ChatPanel overlays
the React Flow canvas (tools mutate the live graph). No CDN at runtime.
No Cognito. No Getafix.
"""

from __future__ import annotations

from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[1] / "ui"
INDEX_NAMES = ("/", "/ui", "/ui/", "/ui/index.html")
FILES_INDEX_NAMES = (
    "/files",
    "/files/",
    "/files/specs",
    "/files/data",
    "/files/results",
    "/ui/files.html",
)
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
}


def ui_available() -> bool:
    return (UI_DIR / "index.html").is_file()


def resolve_ui_path(path: str) -> Path | None:
    """Map a request path onto a file under ui/. None if not a UI route."""
    if path in INDEX_NAMES:
        candidate = UI_DIR / "index.html"
        return candidate if candidate.is_file() else None
    if path in FILES_INDEX_NAMES:
        candidate = UI_DIR / "files.html"
        return candidate if candidate.is_file() else None
    if not path.startswith("/ui/"):
        return None
    relative = path[len("/ui/") :]
    if not relative or relative.endswith("/"):
        candidate = UI_DIR / relative / "index.html"
    else:
        candidate = UI_DIR / relative
    try:
        resolved = candidate.resolve()
        resolved.relative_to(UI_DIR.resolve())
    except (OSError, ValueError):
        return None
    if resolved.is_file():
        return resolved
    return None


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
