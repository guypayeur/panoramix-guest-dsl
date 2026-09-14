# Panoramix operational notes (dsl guest)

Guest for [guypayeur/panoramix](https://github.com/guypayeur/panoramix). Pin **0.5**. Opaque seam: [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) (`kind` / `class` / `payload_digest`). Engines in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings only. Does **not** stamp `north_star_done`. Cloud stays locked.

## Claim

This repo is a real guest origin (not under `platform-tools/fixtures/`). The platform owns the envelope; dsl stays opaque domain code. G1 is an **opaque jobs HTTP seam** with an in-process stub runner. G2 is a **specs catalog HTTP seam** (G11 seed-shaped domain YAML + process-local overlay). G6 is a **thin local-lab auth gate** (login / optional register, HMAC JWT-style tokens) — **not** Cognito, **not** MFA, **not** SaaS admin RBAC. G3/G10 is an **in-guest React Flow editor** (canvas + YAML I/O + validate + undo/redo + minimap + auto-layout) matching dsl-gui *feel* — **not** a `dsl-gui` SPA lift. G9 is **Matryoshka nested-scope visualization** (compound expand/collapse + drill-in; intention of dsl-gui-v2, not a cone/SPA lift). G5 is a **read-first files browse** (specs / data / results over catalog + `fixtures/`) matching FilesPage *intention* — **not** S3 Shared/Group. G4 is **runs UX** on the G1 seam (editor + global submit, list, honest progress, stub cancel) — **not** Spot theater. **G12** is submit-dialog parity (accounts or catalog default, precision f32|f64, optional variable overrides) on those forms; matching params **copy** runtime R2 digests. G7 is the **honest UX journey probe** (`docs/ux-journey.md` + `tests/test_ux_journey.py`). G8 is **AI chat** (ChatPanel intention; SSE / MCP-style tools mutate the live graph; live provider xAI Grok via `XAI_API_KEY` / `~/.xai`; fail closed without a key unless `DSL_CHAT_STUB=1`). `north_star_done` stays false.

## Guest compute seam (G1; not epic Done)

The guest submits **opaque work** over HTTP (`POST /v0/jobs`) using the Slice B shape in [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on panoramix-runtime main: `kind` (`job`|`stage`|`chunk`), `class` (`cpu`|`gpu`), `payload_digest` (`sha256:` + 64 hex). Status lifecycle is `queued` → `running` → `succeeded` | `failed` | `canceled`. List/get/cancel stay on the same public port. `paused` / `held` wait for a durable hook — this stub skips them.

A **local-only** demo shortcut (`demo: echo|sleep|dsl` plus params) synthesizes that opaque shape so an operator does not need a hand-computed digest. `demo:dsl` without G12 fields still digests the tiny G1 catalog stub (`qa-reserve` / `sos-lite` / `reserve` / `sos`) — **not** NSM math, **not** CuPy. With accounts / precision / overrides the guest copies the R2 payload shape; matching params emit the R2/R3 catalog digest. G2 specs live on `GET`/`PUT /v0/specs` (overlay over `catalog/*.yaml`). `PUT` overlay and `POST` jobs submit/cancel require G6 Bearer auth; `GET /health` and catalog/job reads stay public. Stub runner metadata may nest under `local`; it is not a runtime handoff field.

Ctl exports: `GET /v0/jobs/{id}/handoff` (WorkHandoff projection) and `GET /v0/jobs/{id}/payload` (canonical bytes when a demo stored them). Guest emits WorkHandoff JSON only — no guest→ctl HTTP, no `runtime.apply`.

Runtime bindings will select engines later. This guest does **not** invent `PLATFORM_RAY_*` or other engine URL env. Request bodies that smuggle engine brand keys or URL schemes (`ray:` / `temporal:` / `aws:` / …) are **400** `engine_smuggle`. Epic [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) remains open. Cloud stays locked.

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
| Stamp north-star Done / unlock cloud from stub jobs, a catalog API, the editor, files browse, runs UX, the G7 probe, G8 chat, G10 React Flow, G11 catalogs, or G12 submit dialog | **Rejected** — G1–G12 are seams / polish; epic [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) remains open; cloud stays locked |
| Fold Cognito / Getafix / an LLM SDK into chat | **Rejected** — G8 is stdlib `urllib` to xAI Chat Completions; key from `XAI_API_KEY` / `~/.xai` or `DSL_CHAT_STUB`; persist is G6 Bearer |
| Commit an xAI / Grok key or print it in logs / PR text | **Rejected** — operator `~/.xai` stays on the host (mode 600); env / file resolution only; never vendor the secret |
| Add Matryoshka cones (G9) | **Rejected** — G9 stays Later |
| Lift getafix-seed-paul `dsl-gui` SPA / Cognito hosted UI into this Git | **Rejected** — G3/G4/G5/G8/G10 are greenfield in-guest chrome; `react_flow: true` is a Vite bundle, not that SPA |
| Stamp north-star Done because an editor, runs list, G7 probe, G8 chat, or G10 React Flow exists | **Rejected** — not automatic Done; epic [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) remains open |
| Ship Spot / On-Demand / Batch ECG theater on submit | **Rejected** — G4 labels are cpu / gpu / both; `both` fans out to two G1 jobs |
| Invent a progress percent on the stub runner | **Rejected** — omit `progress` when missing; never invent |
| Fold Cognito / MFA TOTP / SaaS admin RBAC into the guest | **Rejected** — G6 is local accounts + HMAC tokens only; no user pool, no roles |
| Vendor getafix-seed-paul `dsl-work` engine / CuPy / kernel / runner into this Git | **Rejected** — G11 vendors **domain YAML only** (formulas/structure). Engines stay in runtime bindings |
| Persist Untitled / empty overlay as if it were a saved spec | **Rejected** — 400 `empty_content` / `sticky_untitled` (seed editor 0.0 / 0.2) |
| Fold Getafix storage / Cognito into overlay save | **Rejected** — overlay is process-local memory; no S3, no fold |
| Ship multi-tenant S3 Shared / Group locations on files browse | **Rejected** — G5 is guest-local fixtures/catalog; `location=shared|group` is 400 `location_refused` |
| Allow upload / move / delete on fixture or catalog browse paths | **Rejected** — read-first; 400 `write_refused` |
| Invent live run result files from the G1 jobs stub | **Rejected** — results tab lists fixture `data_expected` / `data_out` paths; G4 owns submit/watch |

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
