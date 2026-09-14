# panoramix-guest-dsl

Day-one **DSL** (actuarial) guest for [Panoramix](https://github.com/guypayeur/panoramix).

Pin **0.5**. This repository is a greenfield Unit plus opaque domain space. Compute engines live in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings only. The guest-facing handoff shape is opaque `kind` / `class` / `payload_digest` ([`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) / [`docs/guest-seam.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/guest-seam.md)). This guest does **not** unlock cloud [runtime#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [runtime#29](https://github.com/guypayeur/panoramix-runtime/issues/29).

The platform *shape* follows [panoramix-guest-sos](https://github.com/guypayeur/panoramix-guest-sos) (Unit + `platform_run.py` + `.platform/contract.yaml`). This is a **new** guest — not a copy of sos domain, iec, or getafix-seed-paul engine code.

## What this is

- A greenfield Panoramix **0.5** guest: Unit `dsl`, public HTTP on **18380**, probes at `/health`.
- A stdlib Python 3.12 control stub (`platform_run.py`) that serves `GET /health` and `GET /v0/info` (unit `dsl`, pin `0.5`).
- An opaque WorkHandoff *seam* documented for G1: `kind` / `class` / `payload_digest`. G0 does **not** expose a jobs API.
- Engines stay in panoramix-runtime bindings. No engine URLs in this Git.

## What this is not

- **Not** a lift of [getafix-seed-paul](https://github.com/guypayeur/getafix-seed-paul) `dsl-work` / `dsl-gui` / `dsl-gui-v2` / `dsl-backend`. Those trees are the **benchmark** (UX + walls), not a dependency.
- **Not** a copy of [panoramix-guest-sos](https://github.com/guypayeur/panoramix-guest-sos) domain, jobs, or operator UI.
- **Not** a place for `image:`, `ray:`, `temporal:`, or `aws:` fields on Unit/System YAML. Pin stays **0.5**.
- **Not** engine management. CuPy / Ray / Temporal / GPU / AWS stay in runtime bindings.
- **Not** cloud-first. Local lab before AWS. Cloud #61 / #29 stay locked.
- **Not** G1 jobs, G3 React editor, or north-star Done. This scaffold does **not** stamp [epic#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1).

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

`run.entrypoint` is only `platform_run.py`. Emulate digest is entrypoint paths only.

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

There is **no** `POST /v0/jobs` yet (G1) and **no** React UI yet (G3).

With Panoramix tools (from a [panoramix](https://github.com/guypayeur/panoramix) checkout):

```bash
GUEST=/path/to/panoramix-guest-dsl
python3 platform-tools/platform_check.py "$GUEST"
python3 platform-tools/platform_emulate.py "$GUEST" --run --duration 2
```

Emulate is Unix adapter / localhost edge. It does not execute `build.command`. It is not `process` / `container` / `microvm`, and it is not AWS.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

## Operational notes

See [PANORAMIX_OPERATIONAL.md](PANORAMIX_OPERATIONAL.md) (domain-leak log).
