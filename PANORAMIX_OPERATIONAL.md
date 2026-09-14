# Panoramix operational notes (dsl guest)

Guest for [guypayeur/panoramix](https://github.com/guypayeur/panoramix). Pin **0.5**. Opaque seam: [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) (`kind` / `class` / `payload_digest`). Engines in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings only. Does **not** stamp `north_star_done`. Does **not** unlock [runtime#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [runtime#29](https://github.com/guypayeur/panoramix-runtime/issues/29).

## Claim

This repo is a real guest origin (not under `platform-tools/fixtures/`). The platform owns the envelope; dsl stays opaque domain code. G0 is a health/info HTTP stub — **not** getafix-seed-paul, **not** a compute plane, **not** a jobs API.

## Domain-leak log

| Temptation | Decision |
|---|---|
| Add `image:`, `ray:`, `temporal:`, or `aws:` to Unit/System YAML | **Rejected** — pin stays **0.5**; engines and image digests live in runtime bindings / lock sidecars |
| Smuggle engine brand keys or `ray:` / `temporal:` / `s3:` / `image:` URLs on a future jobs body | **Rejected** — 400 `engine_smuggle` when G1 lands; engines stay in bindings |
| Lift getafix-seed-paul `dsl-work` / CuPy kernel / `dsl-gui*` into this Git | **Rejected** — greenfield guest; those trees are UX/perf **benchmarks**, not a dependency |
| Encode engine URLs, Temporal workflow IDs, or Ray addresses in Unit Git | **Rejected** — seam is `kind` / `class` / `payload_digest` only |
| Call `runtime.apply` or open guest→ctl mesh HTTP from this Unit | **Rejected** — guest emits WorkHandoff JSON only (G1); operator/ctl admits via the binding |
| Add a “DSL SDK” facet so apply understands the language | **Rejected** — HTTP/1.1 + `PLATFORM_*` env is the envelope |
| Teach `apply` to walk future `dsl/` imports | **Rejected** — Rec 2 gotcha: digest is entrypoint paths only (`platform_run.py`) |
| Pin Flask/FastAPI/Ray/CuPy on the Unit | **Rejected** — `build` is admission shape; this stub is stdlib; emulate does not execute `build.command` |
| Stamp north-star Done / unlock cloud from this scaffold | **Rejected** — G0 is shape only; [epic#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) stays open; cloud #61 / #29 stay locked |

## Digest gotcha

`run.entrypoint` names only `platform_run.py`. Sibling files must **not** be assumed to change the deploy digest under emulate’s entrypoint rule. Editing `platform_run.py` must.

## Engines

Do not add engine fields here. The container/compute runtime records image digests and binding-selected engines **outside** this Unit. How a future dsl guest submits compute work without embedding engine URLs is [`docs/guest-seam.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/guest-seam.md) — not in `.platform/contract.yaml`.

## Run (with panoramix tools available)

```bash
GUEST=/path/to/panoramix-guest-dsl
# from a panoramix checkout:
python3 platform-tools/platform_check.py "$GUEST"
python3 platform-tools/platform_emulate.py "$GUEST" --run --duration 2
python3 platform-tools/platform_serve.py "$GUEST" --port 19230
```

Emulate only: Unix adapter, localhost edge, stamped `PLATFORM_NETWORK_EGRESS`. `build.command` is not run. Still not `process` / `container` / `microvm`.

## Image digest (container profile, later)

If a container runtime admits a guest-CI image digest, that pin is **not** a Unit field. Pin stays **0.5**. Do not add `image:` here.
