# panoramix-guest-dsl

Day-one **DSL** (actuarial) guest for [Panoramix](https://github.com/guypayeur/panoramix).

Pin **0.5**. This repository is a greenfield Unit plus opaque domain space. Compute engines live in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings only. The guest-facing handoff shape is opaque `kind` / `class` / `payload_digest` ([`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) / [`docs/guest-seam.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/guest-seam.md)). This guest does **not** unlock cloud [runtime#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [runtime#29](https://github.com/guypayeur/panoramix-runtime/issues/29).

The platform *shape* follows [panoramix-guest-sos](https://github.com/guypayeur/panoramix-guest-sos) (Unit + `platform_run.py` + `.platform/contract.yaml` + jobs HTTP). This is a **new** guest — not a copy of sos domain, iec, or getafix-seed-paul engine code.

**G1 landed** (opaque jobs seam). There is still **no editor** ([G3](https://github.com/guypayeur/panoramix-guest-dsl/issues/5)). `GET /v0/info` reports `jobs_api: true`, `ui: false`, `north_star_done: false`. Stub jobs do **not** close [epic#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1).

## What this is

- A greenfield Panoramix **0.5** guest: Unit `dsl`, public HTTP on **18380**, probes at `/health`.
- A stdlib Python 3.12 control surface (`platform_run.py` + `dsl/`): `GET /health`, `GET /v0/info`, and the G1 jobs seam.
- An opaque WorkHandoff *seam*: `POST /v0/jobs` accepts `{kind, class, payload_digest}` (`kind` `job`|`stage`|`chunk`, `class` `cpu`|`gpu`, `payload_digest` `sha256:` + 64 hex). Local demo shortcuts (`echo`, `sleep`, `demo:"dsl"`) synthesize that triple. `demo:"dsl"` digests a tiny catalog stub — **not** NSM / CuPy math.
- Engines stay in panoramix-runtime bindings. No engine URLs in this Git. Guest emits WorkHandoff JSON only — no guest→ctl mesh, no `runtime.apply`.

## What this is not

- **Not** a lift of [getafix-seed-paul](https://github.com/guypayeur/getafix-seed-paul) `dsl-work` / `dsl-gui` / `dsl-gui-v2` / `dsl-backend`. Those trees are the **benchmark** (UX + walls), not a dependency.
- **Not** a copy of [panoramix-guest-sos](https://github.com/guypayeur/panoramix-guest-sos) domain, reserve catalogs, or operator UI.
- **Not** a place for `image:`, `ray:`, `temporal:`, or `aws:` fields on Unit/System YAML. Pin stays **0.5**.
- **Not** engine management. CuPy / Ray / Temporal / GPU / AWS stay in runtime bindings.
- **Not** cloud-first. Local lab before AWS. Cloud #61 / #29 stay locked.
- **Not** G3 React editor, G2 specs API, or north-star Done. G1 does **not** stamp [epic#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1).

## Benchmark (read-only)

| Surface | Seed | Role |
|---|---|---|
| UX | getafix-seed-paul `dsl-gui` / `dsl-gui-v2` | Intention to match; not a code lift |
| Specs API | getafix-seed-paul `dsl-backend` | Intention only; no Getafix fold |
| Walls | getafix-seed-paul `dsl-work` | Same-host bars; remeasure before locking |

See [NORTH_STAR.md](NORTH_STAR.md).

## Contract

`.platform/contract.yaml` is a v0.5 Unit. Port **18380** avoids colliding with httpbin **18080**, shop **18180**, and sos **18280**.

Listen env (same idea as [panoramix-guest-httpbin](https://github.com/guypayeur/panoramix-guest-httpbin) / [panoramix-guest-sos](https://github.com/guypayeur/panoramix-guest-sos) `platform_run.py`):

- `PLATFORM_LISTEN_HTTP` or `PLATFORM_LISTEN_http`
- accepted shapes: `port`, `:port`, `host:port`
- port-only binds loopback (`127.0.0.1`) for emulate

`run.entrypoint` is only `platform_run.py`. Emulate digest is entrypoint paths only — editing `dsl/*.py` alone must **not** be assumed to change it.

## Local run

Python **3.12** stdlib only. No `requirements.txt`.

```bash
python3 ./platform_run.py
# or:
PLATFORM_LISTEN_HTTP=18380 python3 ./platform_run.py
```

Health and product info:

```bash
curl -sS http://127.0.0.1:18380/health
curl -sS http://127.0.0.1:18380/v0/info
```

There is **no** React UI yet (G3). Open `/` or `/ui` and you get 404.

### Jobs API (WorkHandoff)

`POST /v0/jobs` accepts either:

1. **Opaque seam** (must match [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on panoramix-runtime main):
   - `kind`: `job` | `stage` | `chunk`
   - `class`: `cpu` | `gpu`
   - `payload_digest`: `sha256:` + 64 lowercase hex
2. **Local demo shortcut** (operator UX only): `{"demo":"echo","message":"..."}`, `{"demo":"sleep","seconds":8}`, or `{"demo":"dsl"}` / `{"demo":"dsl","catalog":"qa-reserve"}`. The server synthesizes `{kind:"job", class:"cpu"|"gpu", payload_digest}` from canonical JSON (`json.dumps(..., sort_keys=True, separators=(",", ":"))` then sha256). `demo:"dsl"` digests the tiny in-guest catalog stub (`qa-reserve` / `sos-lite` / `reserve` / `sos`, or the whole catalog). It is **not** NSM math and **not** CuPy. The seam `kind` is always `job` for these shortcuts.

Resources expose at least `id`, `kind`, `class`, `payload_digest`, `status`. Status is `queued` → `running` → `succeeded` | `failed` | `canceled` (one L). `paused` / `held` are **not** on this stub (no durable hook). Guest-local stub metadata may appear under `local` (not a runtime handoff field).

Ctl exports (no nested `payload` key):

- `GET /v0/jobs/{id}/handoff` — WorkHandoff projection
- `GET /v0/jobs/{id}/payload` — canonical JSON bytes as hex/utf8 when the demo stored them; opaque-only submit is **404** `payload_unknown`

Engine brand keys/schemes on the body (`engine`, `engine_kind`, `payload`, `url` / `uri` / `endpoint` / `address`, `ray:` / `temporal:` / `aws:` / `s3:` / `image:` / …) return **400** `engine_smuggle`.

Opaque submit:

```bash
DIGEST=$(python3 -c 'import hashlib,json; p={"demo":"echo","message":"hello"}; print("sha256:"+hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest())')
curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -d "{\"kind\":\"job\",\"class\":\"cpu\",\"payload_digest\":\"${DIGEST}\"}"
```

Local demos:

```bash
curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"echo","message":"hello"}'

curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"dsl","catalog":"qa-reserve"}'

curl -sS http://127.0.0.1:18380/v0/jobs
curl -sS http://127.0.0.1:18380/v0/jobs/<id>
curl -sS http://127.0.0.1:18380/v0/jobs/<id>/handoff
curl -sS http://127.0.0.1:18380/v0/jobs/<id>/payload
```

Sleep, then cancel while queued/running:

```bash
ID=$(curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -d '{"demo":"sleep","seconds":8}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://127.0.0.1:18380/v0/jobs/${ID}/cancel"
curl -sS "http://127.0.0.1:18380/v0/jobs/${ID}"
```

Bad `kind` / `class` / `payload_digest` return **400**. Cancel of a terminal job returns **409** `{"error":"already_terminal", ...}`. Missing ids return **404**.

Jobs are process-local and disappear on restart. The stub records opaque work locally; it does not start an engine.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

With Panoramix tools (from a [panoramix](https://github.com/guypayeur/panoramix) checkout):

```bash
GUEST=/path/to/panoramix-guest-dsl
python3 platform-tools/platform_check.py "$GUEST"
python3 platform-tools/platform_emulate.py "$GUEST" --run --duration 2
```

Emulate is Unix adapter / localhost edge. It does not execute `build.command`. It is not `process` / `container` / `microvm`, and it is not AWS.

## Operational notes

See [PANORAMIX_OPERATIONAL.md](PANORAMIX_OPERATIONAL.md) (domain-leak log).
