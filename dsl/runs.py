"""G4 runs UX + G12 submit dialog on top of the G1 jobs seam.

Submit labels are cpu / gpu / both (dsl-gui local-lab intention).
``both`` fans out to two G1 WorkHandoff jobs (class cpu and class gpu).
``both`` is not a seam class.

G12 adds accounts (or catalog default), precision f32|f64, and optional
variable overrides. Digests stay opaque WorkHandoff. When resolved
params match a runtime R2 catalog, the guest **copies** that
``sha256:`` identity (does not import runtime). Custom accounts /
f64 / overrides produce a different digest of the same payload shape.

No Spot / On-Demand / cost-estimate theater. Progress is honest: omit
when missing; never invent percent or batches. G13 copies ``stage`` /
``fraction`` / ``elapsed`` only when a durable hook or runtime verb
actually reported them. The stub runner never fills these. Cancel is
the G1 stub path. A durable hook is optional and unused unless the
operator installs one. Epic #1 remains open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dsl.errors import InvalidAccounts, InvalidClass, InvalidOverrides, InvalidPrecision
from dsl.handoff_vocab import RESOURCE_CLASSES

SUBMIT_LABELS = ("cpu", "gpu", "both")
PRECISIONS = ("f32", "f64")
# Fields a durable hook / local-dsl progress verb may report.
# Stub runner never fills these. percent is copied only when supplied —
# never derived from fraction.
PROGRESS_KEYS = (
    "stage",
    "fraction",
    "elapsed",
    "elapsed_ms",
    "wall_elapsed_ms",
    "started_at",
    "stages_total",
    "stages_completed",
    "percent",
    "completed",
    "total",
    "message",
    "step",
    "steps",
    "catalog",
)

# Copied from panoramix-runtime runtime/dsl.py (R2). Guest copies the
# identity — it must not import runtime. Bump with docs/tests together.
R2_RESERVE_F32_DIGEST = (
    "sha256:40e50160e99ac6b0985dc85b5eec88e3b0b6b9bdf4ef18245f28e8feec8d3200"
)
R2_SOS_NESTED_DIGEST = (
    "sha256:619c607447075f12b08edb16ed52c73d9b0ca87a63a44adadd0b25c011e9b43c"
)
R2_DIGESTS = {
    "reserve-f32": R2_RESERVE_F32_DIGEST,
    "sos-nested": R2_SOS_NESTED_DIGEST,
}
R2_CATALOG_NAMES = tuple(R2_DIGESTS)

# G11 catalog defaults (sizes from catalog/*.yaml). R2 identity is the
# production-intent shape, not a YAML file hash.
_CATALOG_FALLBACK: dict[str, dict[str, Any]] = {
    "reserve": {
        "accounts": 200000,
        "precision": "f32",
        "kernel": "flat",
        "mode": "production",
        "spec": "spec_reserve_ifrs17",
        "r2": "reserve-f32",
        "scenarios": 100,
        "horizon": 1201,
        "sizes": {"ACCOUNT": 200000, "S_OUTER": 100, "T_MONTH": 1201},
    },
    "qa-reserve": {
        "accounts": 200000,
        "precision": "f32",
        "kernel": "flat",
        "mode": "production",
        "spec": "spec_reserve_ifrs17",
        "r2": "reserve-f32",
        "scenarios": 100,
        "horizon": 1201,
        "sizes": {"ACCOUNT": 200000},
    },
    "sos": {
        "accounts": 25,
        "precision": "f32",
        "kernel": "nested",
        "mode": "testing",
        "spec": "spec_sos_full",
        "r2": "sos-nested",
        "t_outer": 1201,
        "s_outer": 10,
        "t_inner": 101,
        "s_inner": 100,
        "sizes": {
            "ACCOUNT": 25,
            "T_OUTER": 1201,
            "S_OUTER": 10,
            "T_INNER": 101,
            "S_INNER": 100,
        },
    },
    "sos-lite": {
        "accounts": 25,
        "precision": "f32",
        "kernel": "nested",
        "mode": "testing",
        "spec": "spec_sos_full",
        "r2": "sos-nested",
        "t_outer": 101,
        "s_outer": 100,
        "t_inner": 101,
        "s_inner": 100,
        "sizes": {
            "ACCOUNT": 25,
            "T_OUTER": 101,
            "S_OUTER": 100,
            "T_INNER": 101,
            "S_INNER": 100,
        },
    },
}

_INLINE_SIZES_RE = re.compile(r"sizes:\s*\{([^}]+)\}")
_MULTILINE_SIZES_RE = re.compile(
    r"sizes:\s*\n((?:\s{2,}[A-Z_][A-Z0-9_]*:\s*\d+[^\n]*\n?)+)"
)
_PAIR_RE = re.compile(r"([A-Z_][A-Z0-9_]*):\s*(\d+)")
_STANDALONE_RE = re.compile(
    r"^(ACCOUNT|NB_SCENARIOS|NB_ACCOUNTS):\s*(\d+)",
    re.MULTILINE,
)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def _as_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _copy_int(out: dict[str, Any], raw: dict[str, Any], key: str) -> None:
    if key not in raw or raw[key] is None:
        return
    number = _as_number(raw[key])
    if number is None:
        return
    out[key] = int(number)


def _copy_float(out: dict[str, Any], raw: dict[str, Any], key: str) -> None:
    if key not in raw or raw[key] is None:
        return
    number = _as_number(raw[key])
    if number is None:
        return
    out[key] = float(number)


def _flatten_progress(raw: Any) -> dict[str, Any] | None:
    """Unwrap local-dsl ``progress --id`` (nested progress + optional walls)."""
    if not isinstance(raw, dict) or not raw:
        return None
    nested = raw.get("progress")
    merged = dict(raw)
    if isinstance(nested, dict):
        merged.pop("progress", None)
        for key, value in nested.items():
            merged[key] = value
    walls = merged.get("walls")
    if walls is None:
        walls = raw.get("walls")
    if isinstance(walls, dict):
        merged["walls"] = walls
        if merged.get("elapsed") is None and walls.get("wall_sec_time") is not None:
            merged["elapsed"] = walls.get("wall_sec_time")
        if merged.get("wall_elapsed_ms") is None and walls.get("wall_elapsed_ms") is not None:
            merged["wall_elapsed_ms"] = walls.get("wall_elapsed_ms")
        if merged.get("elapsed_ms") is None and walls.get("elapsed_ms") is not None:
            merged["elapsed_ms"] = walls.get("elapsed_ms")
    return merged


def _copy_stages(raw: dict[str, Any]) -> list[dict[str, Any]] | None:
    stages = raw.get("stages")
    if not isinstance(stages, list) or not stages:
        return None
    out: list[dict[str, Any]] = []
    for item in stages:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {}
        name = item.get("name") or item.get("stage")
        if isinstance(name, str) and name.strip():
            row["name"] = name.strip()
        elif _as_number(name) is not None:
            row["name"] = int(name)
        elapsed_ms = _as_number(item.get("elapsed_ms"))
        if elapsed_ms is not None:
            row["elapsed_ms"] = float(elapsed_ms)
        elapsed = _as_number(item.get("elapsed"))
        if elapsed is not None:
            row["elapsed"] = float(elapsed)
        if row:
            out.append(row)
    return out or None


def honest_progress(raw: Any) -> dict[str, Any] | None:
    """Project progress only when real fields are present.

    Missing, empty, or non-mapping input is omitted (None). Numeric
    fields are copied only when the hook provided them — never defaulted
    to 0 / 100. ``fraction`` is never turned into ``percent``. The stub
    runner must not call this with invented values.
    """
    flat = _flatten_progress(raw)
    if not isinstance(flat, dict) or not flat:
        return None
    out: dict[str, Any] = {}
    if "stage" in flat and flat["stage"] is not None:
        stage = flat["stage"]
        if isinstance(stage, str) and stage.strip():
            out["stage"] = stage.strip()
        else:
            number = _as_number(stage)
            if number is not None:
                out["stage"] = int(number)
    _copy_float(out, flat, "fraction")
    _copy_float(out, flat, "elapsed")
    _copy_float(out, flat, "elapsed_ms")
    _copy_float(out, flat, "wall_elapsed_ms")
    _copy_int(out, flat, "stages_total")
    _copy_int(out, flat, "stages_completed")
    started = flat.get("started_at")
    if isinstance(started, str) and started.strip():
        out["started_at"] = started.strip()
    catalog = flat.get("catalog")
    if isinstance(catalog, str) and catalog.strip():
        out["catalog"] = catalog.strip()
    stages = _copy_stages(flat)
    if stages is not None:
        out["stages"] = stages
    if "percent" in flat and flat["percent"] is not None:
        pct = _as_number(flat["percent"])
        if pct is not None:
            out["percent"] = float(pct)
    _copy_int(out, flat, "completed")
    _copy_int(out, flat, "total")
    _copy_int(out, flat, "step")
    _copy_int(out, flat, "steps")
    message = flat.get("message")
    if isinstance(message, str) and message.strip():
        out["message"] = message.strip()
    return out or None


def seam_classes() -> tuple[str, ...]:
    return tuple(sorted(RESOURCE_CLASSES))


def extract_sizes(yaml_text: str) -> dict[str, int]:
    """Pull ACCOUNT / loop sizes from catalog YAML (seed dialog intention)."""
    defaults: dict[str, int] = {}
    text = yaml_text or ""
    inline = _INLINE_SIZES_RE.search(text)
    if inline:
        for match in _PAIR_RE.finditer(inline.group(1)):
            defaults[match.group(1)] = int(match.group(2))
    multiline = _MULTILINE_SIZES_RE.search(text)
    if multiline:
        for match in _PAIR_RE.finditer(multiline.group(1)):
            defaults[match.group(1)] = int(match.group(2))
    for match in _STANDALONE_RE.finditer(text):
        defaults[match.group(1)] = int(match.group(2))
    return defaults


def catalog_fallback(catalog_id: str) -> dict[str, Any]:
    key = str(catalog_id or "").strip().lower()
    row = _CATALOG_FALLBACK.get(key)
    if row is None:
        return {
            "accounts": 200000,
            "precision": "f32",
            "kernel": "flat",
            "mode": "production",
            "spec": "spec_reserve_ifrs17",
            "r2": None,
            "scenarios": 100,
            "horizon": 1201,
            "sizes": {},
        }
    copied = dict(row)
    copied["sizes"] = dict(row.get("sizes") or {})
    return copied


def defaults_for_catalog(
    catalog_id: str, yaml_text: str | None = None
) -> dict[str, Any]:
    """Accounts / precision / sizes for the submit dialog (catalog default)."""
    base = catalog_fallback(catalog_id)
    sizes = dict(base.get("sizes") or {})
    if yaml_text:
        sizes.update(extract_sizes(yaml_text))
    accounts = sizes.get("ACCOUNT", base["accounts"])
    return {
        "accounts": int(accounts),
        "precision": "f32",
        "sizes": sizes,
        "r2": base.get("r2"),
        "kernel": base["kernel"],
        "spec": base["spec"],
    }


def parse_precision(raw: Any) -> str:
    if raw is None or raw == "":
        return "f32"
    if not isinstance(raw, str):
        raise InvalidPrecision(type(raw).__name__)
    value = raw.strip().lower()
    if value not in PRECISIONS:
        raise InvalidPrecision(raw)
    return value


def parse_accounts(raw: Any, *, required: bool = False) -> int | None:
    if raw is None or raw == "":
        if required:
            raise InvalidAccounts("accounts is required")
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise InvalidAccounts("accounts must be a positive integer")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if not re.fullmatch(r"[1-9][0-9]*", text):
            raise InvalidAccounts("accounts must be a positive integer")
        value = int(text)
    else:
        if isinstance(raw, float) and not raw.is_integer():
            raise InvalidAccounts("accounts must be a positive integer")
        value = int(raw)
    if value < 1:
        raise InvalidAccounts("accounts must be a positive integer")
    return value


def parse_override_value(raw: Any) -> str | int | float | bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw == int(raw):
            return int(raw)
        return raw
    if not isinstance(raw, str):
        raise InvalidOverrides("override values must be string, number, or boolean")
    text = raw.strip()
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?[0-9]+", text):
        return int(text)
    if re.fullmatch(r"-?[0-9]+\.[0-9]+", text):
        return float(text)
    return text


def parse_overrides(raw: Any) -> dict[str, str | int | float | bool]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise InvalidOverrides("overrides must be a JSON object")
    out: dict[str, str | int | float | bool] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not _IDENT_RE.fullmatch(name):
            raise InvalidOverrides(f"invalid override name {key!r}")
        out[name] = parse_override_value(value)
    return out


def submit_options_present(body: dict[str, Any]) -> bool:
    return any(
        key in body
        for key in ("accounts", "precision", "overrides", "variable_overrides")
    )


@dataclass
class SubmitOptions:
    catalog: str
    accounts: int
    precision: str
    overrides: dict[str, str | int | float | bool] = field(default_factory=dict)
    kernel: str = "flat"
    mode: str = "production"
    spec: str = "spec_reserve_ifrs17"
    scenarios: int = 100
    horizon: int = 1201
    t_outer: int = 101
    s_outer: int = 100
    t_inner: int = 101
    s_inner: int = 100
    r2: str | None = None
    sizes: dict[str, int] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        """R2-shaped canonical params (guest copy; no engine brands)."""
        if self.kernel == "nested":
            return {
                "workload": "dsl",
                "spec": self.spec,
                "accounts": int(self.accounts),
                "t_outer": int(self.t_outer),
                "s_outer": int(self.s_outer),
                "t_inner": int(self.t_inner),
                "s_inner": int(self.s_inner),
                "kernel": "nested",
                "mode": self.mode,
            }
        return {
            "workload": "dsl",
            "spec": self.spec,
            "accounts": int(self.accounts),
            "scenarios": int(self.scenarios),
            "horizon": int(self.horizon),
            "precision": self.precision,
            "mode": self.mode,
            "kernel": "flat",
        }

    def matching_r2(self) -> str | None:
        """R2 catalog name when payload bytes match a copied golden digest."""
        from dsl.handoff import digest_canonical

        digest = digest_canonical(self.payload())
        for name, golden in R2_DIGESTS.items():
            if digest == golden:
                return name
        return None

    def to_local(self) -> dict[str, Any]:
        local: dict[str, Any] = {
            "accounts": int(self.accounts),
            "precision": self.precision,
            "nsm": False,
            "cupy": False,
        }
        if self.overrides:
            local["overrides"] = dict(self.overrides)
        r2 = self.matching_r2()
        if r2:
            local["r2"] = r2
        return local


def _int_override(overrides: dict[str, Any], *names: str) -> int | None:
    for name in names:
        if name not in overrides:
            continue
        value = overrides[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        return int(value)
    return None


def resolve_submit_options(
    catalog_id: str,
    body: dict[str, Any] | None = None,
    *,
    yaml_text: str | None = None,
) -> SubmitOptions:
    """Merge dialog fields: override ACCOUNT > accounts > catalog default."""
    body = body or {}
    fallback = catalog_fallback(catalog_id)
    defaults = defaults_for_catalog(catalog_id, yaml_text)
    sizes = dict(defaults.get("sizes") or {})
    overrides = parse_overrides(
        body.get("overrides")
        if "overrides" in body
        else body.get("variable_overrides")
    )
    precision = parse_precision(body.get("precision") or defaults["precision"])
    override_accounts = _int_override(overrides, "ACCOUNT", "NB_ACCOUNTS")
    explicit = parse_accounts(body.get("accounts")) if "accounts" in body else None
    accounts = override_accounts or explicit or int(defaults["accounts"])
    if accounts < 1:
        raise InvalidAccounts("accounts must be a positive integer")

    scenarios = (
        _int_override(overrides, "S_OUTER", "NB_SCENARIOS")
        or sizes.get("S_OUTER")
        or int(fallback.get("scenarios") or 100)
    )
    horizon = (
        _int_override(overrides, "T_MONTH", "T_OUTER", "HORIZON")
        or sizes.get("T_MONTH")
        or sizes.get("T_OUTER")
        or int(fallback.get("horizon") or fallback.get("t_outer") or 1201)
    )
    t_outer = (
        _int_override(overrides, "T_OUTER")
        or sizes.get("T_OUTER")
        or int(fallback.get("t_outer") or 101)
    )
    s_outer = (
        _int_override(overrides, "S_OUTER")
        or sizes.get("S_OUTER")
        or int(fallback.get("s_outer") or 100)
    )
    t_inner = (
        _int_override(overrides, "T_INNER")
        or sizes.get("T_INNER")
        or int(fallback.get("t_inner") or 101)
    )
    s_inner = (
        _int_override(overrides, "S_INNER")
        or sizes.get("S_INNER")
        or int(fallback.get("s_inner") or 100)
    )
    return SubmitOptions(
        catalog=str(catalog_id or "").strip().lower() or "all",
        accounts=int(accounts),
        precision=precision,
        overrides=overrides,
        kernel=str(fallback.get("kernel") or "flat"),
        mode=str(fallback.get("mode") or "production"),
        spec=str(fallback.get("spec") or "spec_reserve_ifrs17"),
        scenarios=int(scenarios),
        horizon=int(horizon),
        t_outer=int(t_outer),
        s_outer=int(s_outer),
        t_inner=int(t_inner),
        s_inner=int(s_inner),
        r2=fallback.get("r2"),
        sizes=sizes,
    )
