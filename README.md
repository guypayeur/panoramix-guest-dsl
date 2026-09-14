# panoramix-guest-dsl

Day-one **DSL** (actuarial) guest for [Panoramix](https://github.com/guypayeur/panoramix).

Pin **0.5**. This repository is a greenfield Unit plus opaque domain space. Compute engines live in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings only. The guest-facing handoff shape is opaque `kind` / `class` / `payload_digest` ([`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) / [`docs/guest-seam.md`](https://github.com/guypayeur/panoramix-runtime/blob/main/docs/guest-seam.md)). Cloud stays locked.

The platform *shape* follows [panoramix-guest-sos](https://github.com/guypayeur/panoramix-guest-sos) (Unit + `platform_run.py` + `.platform/contract.yaml` + jobs HTTP). This is a **new** guest — not a copy of sos domain, iec, or getafix-seed-paul engine code.

**G1** (opaque jobs seam), **G2** (specs catalog API), **G6** (thin local auth), **G3** (editor MVP), **G5** (files browse), **G4** (runs UX), **G7** (UX journey probe), and **G8** (AI chat) have landed. `GET /v0/info` reports `jobs_api: true`, `specs_api: true`, `auth_api: true`, `files_api: true`, `ui: true`, `runs_ux: true`, `ux_journey: true`, `chat_api: true`, `north_star_done: false`. The editor is a greenfield canvas (dsl-gui *intention*, not a SPA lift). Files browse is read-first specs / data / results over fixture and catalog paths. Runs submit/list/watch/cancel sit on the G1 seam. The editor ChatPanel uses SSE / MCP-style tools to mutate the live graph (fail closed without `ANTHROPIC_API_KEY` unless `DSL_CHAT_STUB=1`). The representative journey is documented in [docs/ux-journey.md](docs/ux-journey.md) and smoke-tested; day-one is thinner than live `dsl-gui` local-lab. Epic #1 remains open. Cloud stays locked.

## What this is

- A greenfield Panoramix **0.5** guest: Unit `dsl`, public HTTP on **18380**, probes at `/health`.
- A stdlib Python 3.12 control surface (`platform_run.py` + `dsl/`): `GET /health`, `GET /v0/info`, the G1 jobs seam, the G2 specs catalog (`GET`/`PUT /v0/specs`), G5 files browse (`GET /v0/files`, `GET /files`), G6 thin local auth (`POST /v0/auth/login`, optional `POST /v0/auth/register`), the G3 editor (`GET /`, `GET /ui`, `POST /v0/graph/parse|export|validate`), G4 runs UX (editor + global submit, list, honest progress, cancel), the G7 UX probe (`docs/ux-journey.md`), and G8 AI chat (`POST /v0/chat`, SSE / MCP-style tools). HMAC JWT-style tokens, no extra deps.
- An opaque WorkHandoff *seam*: `POST /v0/jobs` accepts `{kind, class, payload_digest}` (`kind` `job`|`stage`|`chunk`, `class` `cpu`|`gpu`, `payload_digest` `sha256:` + 64 hex). Local demo shortcuts (`echo`, `sleep`, `demo:"dsl"`) synthesize that triple. `demo:"dsl"` digests a tiny catalog stub — **not** NSM / CuPy math.
- Engines stay in panoramix-runtime bindings. No engine URLs in this Git. Guest emits WorkHandoff JSON only — no guest→ctl mesh, no `runtime.apply`.

## What this is not

- **Not** a lift of [getafix-seed-paul](https://github.com/guypayeur/getafix-seed-paul) `dsl-work` / `dsl-gui` / `dsl-gui-v2` / `dsl-backend`. Those trees are the **benchmark** (UX + walls), not a dependency.
- **Not** a copy of [panoramix-guest-sos](https://github.com/guypayeur/panoramix-guest-sos) domain, reserve catalogs, or operator UI.
- **Not** a place for `image:`, `ray:`, `temporal:`, or `aws:` fields on Unit/System YAML. Pin stays **0.5**.
- **Not** engine management. CuPy / Ray / Temporal / GPU / AWS stay in runtime bindings.
- **Not** cloud-first. Local lab before AWS. Cloud stays locked.
- **Not** a lift of the getafix-seed-paul `dsl-gui` SPA (G3/G4 are greenfield in-guest chrome; G5 matches FilesPage *intention* only). **Not** Cognito / MFA TOTP / SaaS admin RBAC, multi-tenant S3 Shared/Group, or north-star Done. G6 Bearer is what the editor uses for overlay save and job submit/cancel. G7 is an honest thinner-day-one stamp, not automatic Done. Epic #1 remains open.

## Benchmark (read-only)

| Surface | Seed | Role |
|---|---|---|
| UX | getafix-seed-paul `dsl-gui` / `dsl-gui-v2` | Intention to match; not a code lift |
| Specs API | getafix-seed-paul `dsl-backend` | Intention only; no Getafix fold |
| Walls | getafix-seed-paul `dsl-work` | Same-host bars; remeasure before locking |

See [NORTH_STAR.md](NORTH_STAR.md) and the G7 probe [docs/ux-journey.md](docs/ux-journey.md).

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

The G3 editor is served at `/` and `/ui` (`ui: true`). Open a catalog spec, edit the canvas, import/export YAML, validate, then save an overlay with a G6 Bearer token. Persistence across catalog nav is **sessionStorage** (thinner day-one; overlay PUT is the process-local save). No undo/redo.

G4 adds **Editor** and **Runs** views: submit from the editor toolbar or the global Runs form (cpu / gpu / both — no Spot theater). `both` fans out to two G1 jobs (`class` `cpu` and `class` `gpu`). The runs list filters by status. Run detail shows progress only when the job actually has it (the stub omits the field). Cancel uses the G1 stub path; durable cancel is reported only when a hook is installed.

The G5 files page is served at `/files`, `/files/specs`, `/files/data`, `/files/results` (`files_api: true`). Specs / data / results tabs browse catalog stubs and `fixtures/` paths. Writes are refused. There is no Shared / Group / user S3 location.

### Thin local auth (G6)

Intention from getafix-seed-paul `dsl-gui` local-lab / `dsl-backend` `localAuth` — **not** Cognito, **not** MFA TOTP, **not** SaaS admin RBAC. Accounts and HMAC tokens are process-local (stdlib `hmac` / `hashlib.pbkdf2_hmac`). Seed admin: `guy.payeur@gp2.ca` / `admin123!` (override with `DSL_SEED_EMAIL` / `DSL_SEED_PASSWORD` / `DSL_AUTH_SECRET`).

**Public** (no token):

- `GET /health`, `GET /v0/info`, `GET /`, `GET /ui`, `GET /files`
- `POST /v0/auth/login`, `POST /v0/auth/register`
- `GET /v0/specs`, `GET /v0/specs/{id}`, `GET /v0/specs/{id}/yaml`, `GET /v0/specs/folders`
- `GET /v0/files`, `GET /v0/files/{tab}`, `GET /v0/files/{tab}/{id}`, `GET /v0/files/{tab}/{id}/text`
- `POST /v0/graph/parse`, `POST /v0/graph/export`, `POST /v0/graph/validate`
- `GET /v0/chat`, `GET /v0/chat/usage`, `POST /v0/chat` (live-graph mutate)
- `GET /v0/jobs`, `GET /v0/jobs/{id}`, `GET /v0/jobs/{id}/handoff`, `GET /v0/jobs/{id}/payload`

**Protected** (fail closed **401** `unauthorized` without `Authorization: Bearer <accessToken>`):

- `PUT /v0/specs/{id}` (overlay)
- `POST /v0/specs`, `DELETE /v0/specs/{id}` (still catalog-readonly after auth)
- `POST /v0/jobs`, `POST /v0/jobs/{id}/cancel`
- `GET /v0/auth/me`
- `POST /v0/chat` when `persist` / overlay save is requested

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:18380/v0/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"guy.payeur@gp2.ca","password":"admin123!"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokens"]["accessToken"])')

curl -sS -X PUT http://127.0.0.1:18380/v0/specs/qa-reserve \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"content":"metadata:\n  id: qa-reserve\n  kind: overlay-stub\n"}'

curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"demo":"echo","message":"hello"}'
```

Unauthenticated `PUT /v0/specs/{id}` or `POST /v0/jobs` returns **401**. Optional register:

```bash
curl -sS -X POST http://127.0.0.1:18380/v0/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"lab.user@example.com","password":"userpass1","name":"Lab User"}'
```

The editor chrome includes a thin login form (same seed account). It is **not** Cognito and **not** a hosted UI.

### Jobs API (WorkHandoff)

`POST /v0/jobs` accepts either:

1. **Opaque seam** (must match [`runtime/compute_work.py`](https://github.com/guypayeur/panoramix-runtime/blob/main/runtime/compute_work.py) on panoramix-runtime main):
   - `kind`: `job` | `stage` | `chunk`
   - `class`: `cpu` | `gpu`
   - `payload_digest`: `sha256:` + 64 lowercase hex
2. **Local demo shortcut** (operator UX only): `{"demo":"echo","message":"..."}`, `{"demo":"sleep","seconds":8}`, or `{"demo":"dsl"}` / `{"demo":"dsl","catalog":"qa-reserve"}`. The server synthesizes `{kind:"job", class:"cpu"|"gpu", payload_digest}` from canonical JSON (`json.dumps(..., sort_keys=True, separators=(",", ":"))` then sha256). `demo:"dsl"` digests the tiny in-guest catalog stub (`qa-reserve` / `sos-lite` / `reserve` / `sos`, or the whole catalog). It is **not** NSM math and **not** CuPy. The seam `kind` is always `job` for these shortcuts.

Resources expose at least `id`, `kind`, `class`, `payload_digest`, `status`. Status is `queued` → `running` → `succeeded` | `failed` | `canceled` (one L). `paused` / `held` are **not** on this stub (no durable hook). Guest-local stub metadata may appear under `local` (not a runtime handoff field). `progress` is omitted unless a hook recorded real values — the stub never invents a percent.

Ctl exports (no nested `payload` key):

- `GET /v0/jobs/{id}/handoff` — WorkHandoff projection
- `GET /v0/jobs/{id}/payload` — canonical JSON bytes as hex/utf8 when the demo stored them; opaque-only submit is **404** `payload_unknown`

Engine brand keys/schemes on the body (`engine`, `engine_kind`, `payload`, `url` / `uri` / `endpoint` / `address`, `ray:` / `temporal:` / `aws:` / `s3:` / `image:` / …) return **400** `engine_smuggle`.

Opaque submit (Bearer required):

```bash
DIGEST=$(python3 -c 'import hashlib,json; p={"demo":"echo","message":"hello"}; print("sha256:"+hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest())')
curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d "{\"kind\":\"job\",\"class\":\"cpu\",\"payload_digest\":\"${DIGEST}\"}"
```

Local demos (Bearer required):

```bash
curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"demo":"echo","message":"hello"}'

curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
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
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"demo":"sleep","seconds":8}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://127.0.0.1:18380/v0/jobs/${ID}/cancel" \
  -H "Authorization: Bearer ${TOKEN}"
curl -sS "http://127.0.0.1:18380/v0/jobs/${ID}"
```

Bad `kind` / `class` / `payload_digest` return **400**. Cancel of a terminal job returns **409** `{"error":"already_terminal", ...}`. Missing ids return **404**.

Jobs are process-local and disappear on restart. The stub records opaque work locally; it does not start an engine.

### Specs catalog API (G2)

Intention from getafix-seed-paul [`dsl-backend/src/platform.ts`](https://github.com/guypayeur/getafix-seed-paul/blob/main/dsl-backend/src/platform.ts) — **not** a Getafix fold, **not** Cognito, **not** a `dsl-work` CuPy lift. Day-one catalog is the **full** four-row set (not a subset):

| id | name | entity | in-guest stub | seed pointer |
|---|---|---|---|---|
| `sos` | SOS | SOS | `catalog/sos.yaml` | `dsl-work/spec_sos.yaml` |
| `reserve` | RESERVE IFRS17 | RESERVE | `catalog/reserve.yaml` | `dsl-work/spec_reserve_ifrs17.yaml` |
| `sos-lite` | SOS lite | SOS | `catalog/sos-lite.yaml` | `dsl-work/spec_sos_lite_t_outer_101_s_outer_100.yaml` |
| `qa-reserve` | QA RESERVE IFRS17 | RESERVE | `catalog/qa-reserve.yaml` | `dsl-work/qa_reserve_ifrs17.yaml` |

Stubs are thin pointers. They do **not** vendor the seed engine YAML.

```bash
curl -sS http://127.0.0.1:18380/v0/specs
curl -sS http://127.0.0.1:18380/v0/specs/sos
curl -sS http://127.0.0.1:18380/v0/specs/sos/yaml
```

`PUT /v0/specs/{id}` writes a **process-local overlay** (JSON `{"content":"...yaml..."}`; `yaml` is accepted as an alias). Catalog files are never mutated. Overlay is gone on restart.

Save rules (seed editor 0.0 / 0.2; enforced on PUT):

- **No empty** — whitespace-only `content` is **400** `empty_content`
- **No sticky Untitled** — `name` of `Untitled` / `Untitled Spec` / `Untitled Specification` is **400** `sticky_untitled` (visual cue only). Omit `name` to keep the catalog row title.
- `POST /v0/specs` (create) and `DELETE /v0/specs/{id}` are **400** `catalog_readonly`

`PUT` requires a Bearer token (see G6 above). Catalog `GET` stays public.

```bash
curl -sS -X PUT http://127.0.0.1:18380/v0/specs/qa-reserve \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"content":"metadata:\n  id: qa-reserve\n  kind: overlay-stub\n"}'
```

### Editor (G3)

Intention from getafix-seed-paul `dsl-gui` (canvas + side panel + YAML I/O + validate) — **not** a code lift of that SPA, **not** React Flow vendored, **not** Cognito, **not** Matryoshka/cone (G9).

```bash
# browser
open http://127.0.0.1:18380/
# or:
curl -sS -D- -o /dev/null http://127.0.0.1:18380/ui
```

Canvas node types: DataSource, Loop, Formula, Aggregation. Side panel edits the selected node. YAML import/export talks to `POST /v0/graph/parse` and `POST /v0/graph/export`. Unedited G2 catalog stubs roundtrip as the original YAML blob. Validate (`POST /v0/graph/validate`) reports `undefined_var` (error) and `missing_filename` (warning). Overlay save is `PUT /v0/specs/{id}` with `Authorization: Bearer`.

### Runs UX (G4)

Intention from getafix-seed-paul `dsl-gui` local-lab submit / list / watch / cancel — **not** a SPA lift, **not** Spot / On-Demand / Batch ECG theater, **not** Getafix workers.

- **Editor submit** — catalog stub (`demo:"dsl"`) for the open spec, labels `cpu` / `gpu` / `both`
- **Global submit** — same labels from the Runs view (catalog stub, or local `echo` / `sleep`)
- **List** — `GET /v0/jobs` with the status filter chips
- **Detail** — honest progress: the progress block is omitted when the job has none
- **Cancel** — `POST /v0/jobs/{id}/cancel` (G6 Bearer). Works on the stub path. `GET /v0/info` reports `runs.cancel_durable: false` unless an operator installed a hook

`both` is a UI label only. Each submit still hits `POST /v0/jobs` with seam `class` `cpu` or `gpu`.

```bash
curl -sS -X POST http://127.0.0.1:18380/v0/graph/parse \
  -H 'Content-Type: application/json' \
  --data-binary @<(python3 -c 'import json,pathlib; print(json.dumps({"yaml": pathlib.Path("catalog/sos.yaml").read_text()}))')
```

### Files browse (G5)

Intention from getafix-seed-paul `dsl-gui` FilesPage — **read-first**, **not** a code lift, **not** multi-tenant S3 Shared/Group. Specs tab pairs with G2 catalog rows. Data tab walks `fixtures/data_in/`. Results tab walks `fixtures/data_expected/` and `fixtures/data_out/` (fixture paths; G4 owns submit/watch, not result files).

```bash
open http://127.0.0.1:18380/files
curl -sS http://127.0.0.1:18380/v0/files
curl -sS http://127.0.0.1:18380/v0/files/specs
curl -sS http://127.0.0.1:18380/v0/files/data
curl -sS 'http://127.0.0.1:18380/v0/files/data?folder=data_in/SOS'
curl -sS http://127.0.0.1:18380/v0/files/results
curl -sS http://127.0.0.1:18380/v0/files/data/in-sos-accounts.csv/text
```

Writes fail closed (**400** `write_refused`) even with a Bearer token. `?location=shared` / `group` / `user` is **400** `location_refused`.

```bash
curl -sS -X POST http://127.0.0.1:18380/v0/files/data \
  -H 'Content-Type: application/json' \
  -d '{"filename":"upload.csv"}'
# → {"error":"write_refused", ...}
```

### AI chat (G8)

Intention from getafix-seed-paul `dsl-gui` ChatPanel + `dsl-backend` `POST /api/chat` — **not** a SPA lift, **not** Cognito, **not** a Getafix dependency. The editor ChatPanel streams SSE events; MCP-style tools (`create_data_source`, `create_loop`, `create_formula`, `create_aggregation`, `update_node`, `delete_node`, `connect_nodes`, plus `get_current_state` / `load_skill`) mutate the live canvas.

Fail closed without a model key:

- Live: set `ANTHROPIC_API_KEY` (optional `DSL_CHAT_MODEL`; stdlib `urllib` to the Messages API — no SDK pin)
- Documented stub (tests / no model): `DSL_CHAT_STUB=1`

`GET /v0/chat` reports `{available, mode}`. `POST /v0/chat` without a key and without stub is **503** `chat_unavailable`. Live-graph mutate is public (same idea as parse/validate). Persisting the mutated spec (`persist: true` + `spec_id`) is overlay `PUT` and **requires G6 Bearer**.

```bash
DSL_CHAT_STUB=1 python3 ./platform_run.py
curl -sS http://127.0.0.1:18380/v0/chat
curl -sS -X POST http://127.0.0.1:18380/v0/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Create a data source for population.csv","dslState":{"nodes":[],"edges":[]}}'
```

SSE (`Accept: text/event-stream`) emits `tool_use` then `message` then `[DONE]`. JSON is the default for tests. Stub NL understands the ChatPanel examples (data source / outer loop / formula) plus `connect A to B`, `delete <id>`, and `update <id>`. Tests may also send an explicit `tools` array or inject a mocked model driver.

### UX journey probe (G7)

Written stamp: [docs/ux-journey.md](docs/ux-journey.md). Automated smoke: `python3 -m unittest tests.test_ux_journey -v`.

Representative path (SOS / RESERVE-class catalog stub → edit/validate → submit → watch → cancel or succeed) is wired. Day-one is **thinner** than getafix-seed-paul `dsl-gui` local-lab (`isLocalAuth()` cpu/gpu/both — not the AWS Spot theater). `north_star_done` stays false. Epic #1 remains open.

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
