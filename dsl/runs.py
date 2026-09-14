"""G4 runs UX helpers on top of the G1 jobs seam.

Submit labels are cpu / gpu / both (dsl-gui local-lab intention).
``both`` fans out to two G1 WorkHandoff jobs (class cpu and class gpu).
``both`` is not a seam class. No Spot / On-Demand theater.

Progress is honest: omit when missing; never invent percent or batches.
Cancel is the G1 stub path. A durable hook is optional and unused unless
the operator installs one. Epic #1 remains open.
"""

from __future__ import annotations

from typing import Any

from dsl.errors import InvalidClass
from dsl.handoff_vocab import RESOURCE_CLASSES

SUBMIT_LABELS = ("cpu", "gpu", "both")
# Fields a later durable hook may report. Stub runner never fills these.
PROGRESS_KEYS = ("percent", "completed", "total", "message", "step", "steps")


def classes_for_label(label: str) -> tuple[str, ...]:
    """Expand a UI submit label onto G1 resource classes.

    ``cpu`` / ``gpu`` stay one seam class. ``both`` is two jobs, not a
    third class on WorkHandoff.
    """
    raw = str(label or "").strip().lower()
    if raw == "cpu":
        return ("cpu",)
    if raw == "gpu":
        return ("gpu",)
    if raw == "both":
        return ("cpu", "gpu")
    raise InvalidClass(
        raw,
        detail=(
            "submit labels are cpu, gpu, or both "
            "(both fans out to cpu+gpu; seam class stays cpu|gpu)"
        ),
    )


def submit_bodies_for_label(label: str, base: dict[str, Any]) -> list[dict[str, Any]]:
    """Fan a UI submit into G1 bodies (one POST /v0/jobs per class)."""
    if not isinstance(base, dict):
        raise InvalidClass("", detail="submit body must be a JSON object")
    bodies: list[dict[str, Any]] = []
    for cls in classes_for_label(label):
        body = dict(base)
        body["class"] = cls
        bodies.append(body)
    return bodies


def honest_progress(raw: Any) -> dict[str, Any] | None:
    """Project progress only when real fields are present.

    Missing, empty, or non-mapping input is omitted (None). Numeric
    fields are copied only when the hook provided them — never defaulted
    to 0 / 100. The stub runner must not call this with invented values.
    """
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, Any] = {}
    if "percent" in raw and raw["percent"] is not None:
        pct = raw["percent"]
        if isinstance(pct, bool) or not isinstance(pct, (int, float)):
            pass
        else:
            out["percent"] = float(pct)
    if "completed" in raw and raw["completed"] is not None:
        done = raw["completed"]
        if isinstance(done, bool) or not isinstance(done, (int, float)):
            pass
        else:
            out["completed"] = int(done)
    if "total" in raw and raw["total"] is not None:
        total = raw["total"]
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            pass
        else:
            out["total"] = int(total)
    if "step" in raw and raw["step"] is not None:
        step = raw["step"]
        if isinstance(step, bool) or not isinstance(step, (int, float)):
            pass
        else:
            out["step"] = int(step)
    if "steps" in raw and raw["steps"] is not None:
        steps = raw["steps"]
        if isinstance(steps, bool) or not isinstance(steps, (int, float)):
            pass
        else:
            out["steps"] = int(steps)
    message = raw.get("message")
    if isinstance(message, str) and message.strip():
        out["message"] = message.strip()
    return out or None


def seam_classes() -> tuple[str, ...]:
    return tuple(sorted(RESOURCE_CLASSES))
