"""WorkHandoff vocabulary (no engine brands, no sos domain)."""

from __future__ import annotations

from typing import Any

WORK_KINDS = frozenset({"job", "stage", "chunk"})
RESOURCE_CLASSES = frozenset({"cpu", "gpu"})
WORK_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "canceled",
)
TERMINAL = frozenset({"succeeded", "failed", "canceled"})
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"

DEMO_ECHO = "echo"
DEMO_SLEEP = "sleep"
DEMO_DSL = "dsl"
LOCAL_DEMOS = frozenset({DEMO_ECHO, DEMO_SLEEP, DEMO_DSL})
DEFAULT_ECHO_MESSAGE = "ok"
DEFAULT_SLEEP_SECONDS = 2
MAX_SLEEP_SECONDS = 30.0

# Tiny catalog stub for demo:dsl digest only. Ids match G2 catalog
# rows (sos / reserve / sos-lite / qa-reserve). This dict is the G1
# jobs digest — not the G2 YAML catalog. Not NSM math. Not CuPy.
DSL_STUB_CATALOG: dict[str, dict[str, Any]] = {
    "qa-reserve": {"id": "qa-reserve", "kind": "catalog-stub", "math": False},
    "sos-lite": {"id": "sos-lite", "kind": "catalog-stub", "math": False},
    "reserve": {"id": "reserve", "kind": "catalog-stub", "math": False},
    "sos": {"id": "sos", "kind": "catalog-stub", "math": False},
}
DSL_CATALOG_ALL = "all"
