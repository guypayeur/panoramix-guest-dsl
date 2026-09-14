# Panoramix operational notes (dsl guest)

Guest for [guypayeur/panoramix](https://github.com/guypayeur/panoramix). Pin **0.5**. Opaque seam: [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) (`kind` / `class` / `payload_digest`). Engines in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings only. Does **not** stamp `north_star_done`. Does **not** unlock [runtime#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [runtime#29](https://github.com/guypayeur/panoramix-runtime/issues/29).

## Claim

This repo is a real guest origin (not under `platform-tools/fixtures/`). The platform owns the envelope; dsl stays opaque domain code. G1 is an **opaque jobs HTTP seam** with an in-process stub runner. G2 is a **specs catalog HTTP seam** (thin YAML stubs + process-local overlay). G6 is a **thin local-lab auth gate** (login / optional register, HMAC JWT-style tokens) — **not** Cognito, **not** MFA, **not** SaaS admin RBAC, **not** an editor.

## Guest compute seam (G1; not epic Done)

The guest submits **opaque work** over HTTP (`POST /v0/jobs`) using the Slice B shape in [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on panoramix-runtime main: `kind` (`job`|`stage`|`chunk`), `class` (`cpu`|`gpu`), `payload_digest` (`sha256:` + 64 hex). Status lifecycle is `queued` → `running` → `succeeded` | `failed` | `canceled`. List/get/cancel stay on the same public port. `paused` / `held` wait for a durable hook — this stub skips them.

A **local-only** demo shortcut (`demo: echo|sleep|dsl` plus params) synthesizes that opaque shape so an operator does not need a hand-computed digest. `demo:dsl` still digests the tiny G1 catalog stub (`qa-reserve` / `sos-lite` / `reserve` / `sos`) — **not** NSM math, **not** CuPy. That digest path is unchanged. G2 specs live on `GET`/`PUT /v0/specs` (overlay over `catalog/*.yaml`). `PUT` overlay and `POST` jobs submit/cancel require G6 Bearer auth; `GET /health` and catalog/job reads stay public. Stub runner metadata may nest under `local`; it is not a runtime handoff field.

Ctl exports: `GET /v0/jobs/{id}/handoff` (WorkHandoff projection) and `GET /v0/jobs/{id}/payload` (canonical bytes when a demo stored them). Guest emits WorkHandoff JSON only — no guest→ctl HTTP, no `runtime.apply`.

Runtime bindings will select engines later. This guest does **not** invent `PLATFORM_RAY_*` or other engine URL env. Request bodies that smuggle engine brand keys or URL schemes (`ray:` / `temporal:` / `aws:` / …) are **400** `engine_smuggle`. This alignment does **not** close [epic#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) and does **not** unlock #61 / #29.

## Domain-leak log

| Temptation | Decision |
|---|---|
| Add `image:`, `ray:`, `temporal:`, or `aws:` to Unit/System YAML | **Rejected** — pin stays **0.5**; engines and image digests live in runtime bindings / lock sidecars |
| Smuggle engine brand keys or `ray:` / `temporal:` / `aws:` / `s3:` / `image:` URLs on a jobs body | **Rejected** — 400 `engine_smuggle`; engines stay in bindings |
| Lift getafix-seed-paul `dsl-work` / CuPy kernel / `dsl-gui*` into this Git | **Rejected** — greenfield guest; those trees are UX/perf **benchmarks**, not a dependency |
| Copy sos reserve / IFRS17 / iec-local catalogs into this guest | **Rejected** — HTTP *shape* only; `demo:dsl` is a digest stub, not sos domain |
| Encode engine URLs, Temporal workflow IDs, or Ray addresses in Unit Git | **Rejected** — seam is `kind` / `class` / `payload_digest` only |
| Call `runtime.apply` or open guest→ctl mesh HTTP from this Unit | **Rejected** — guest emits WorkHandoff JSON only; operator/ctl admits via the binding |
| Add a “DSL SDK” facet so apply understands the language | **Rejected** — HTTP/1.1 + `PLATFORM_*` env is the envelope |
| Teach `apply` to walk `dsl/` imports | **Rejected** — Rec 2 gotcha: digest is entrypoint paths only (`platform_run.py`). Entry may import `dsl.http`; sibling `dsl/` edits still must not be assumed to change emulate digest |
| Pin Flask/FastAPI/Ray/CuPy on the Unit | **Rejected** — `build` is admission shape; this guest is stdlib; emulate does not execute `build.command` |
| Stamp north-star Done / unlock cloud from stub jobs or a catalog API | **Rejected** — G1/G2/G6 are seams only; [epic#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) is not Done; cloud #61 / #29 stay locked |
| Ship a React editor or login page with this catalog | **Rejected** — G3; `ui` stays false |
| Fold Cognito / MFA TOTP / SaaS admin RBAC into the guest | **Rejected** — G6 is local accounts + HMAC tokens only; no user pool, no roles |
| Vendor getafix-seed-paul `dsl-work` YAML / CuPy into `catalog/` | **Rejected** — thin stubs or seed-file pointers only |
| Persist Untitled / empty overlay as if it were a saved spec | **Rejected** — 400 `empty_content` / `sticky_untitled` (seed editor 0.0 / 0.2) |
| Fold Getafix storage / Cognito into overlay save | **Rejected** — overlay is process-local memory; no S3, no fold |

## Digest gotcha

`run.entrypoint` names only `platform_run.py`. Editing `dsl/jobs.py` (or other siblings) alone must **not** change the deploy digest under emulate’s entrypoint rule. Editing `platform_run.py` must. The thin entrypoint **may** import `dsl.http` (like sos/httpbin); that import does not expand the digest to the package.

## Engines

Do not add engine fields here. The container/compute runtime records image digests and binding-selected engines **outside** this Unit. How this guest submits compute work without embedding engine URLs is [`docs/guest-seam.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/guest-seam.md) — not in `.platform/contract.yaml`.

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
