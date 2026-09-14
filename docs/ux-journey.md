# G7 UX journey probe

Honest stamp for the epic UX box on [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1). This file is the written probe. Automated evidence is `tests/test_ux_journey.py` (in-process `DslApp.handle`, no sockets, no invented progress).

**Verdict (2026-09-14):** the representative path is wired and smoke-tested. Day-one is **thinner** than live getafix-seed-paul `dsl-gui` local-lab. `GET /v0/info` reports `ux_journey: true` and **`north_star_done: false`**. Epic #1 remains open for human morning review. Cloud stays locked.

This guest did **not** measure walls. Runtime R5 bar #1 is cited only as a pointer ([panoramix-runtime#170](https://github.com/guypayeur/panoramix-runtime/issues/170): 34.23s ≤ R1 38.25s on the same host). Perf is not earned from this Git.

## Representative path

NORTH_STAR path: **open an SOS or RESERVE-class spec → edit/validate → submit → watch → cancel** (and/or succeed).

| Step | Guest surface | Smoke |
|---|---|---|
| Open SOS-class | `GET /v0/specs/sos` (also `sos-lite`) | catalog stub, `entity: SOS` |
| Open RESERVE-class | `GET /v0/specs/reserve` (also `qa-reserve`) | catalog stub, `entity: RESERVE` |
| Edit / validate | canvas + `POST /v0/graph/parse\|export\|validate` | live graph wins over stale YAML |
| Save (optional) | `PUT /v0/specs/{id}` + G6 Bearer | process-local overlay |
| Submit | editor toolbar or Runs form → `POST /v0/jobs` | labels `cpu` / `gpu` / `both` |
| Watch | `GET /v0/jobs` + `GET /v0/jobs/{id}` | status only; `progress` omitted on stub |
| Cancel | `POST /v0/jobs/{id}/cancel` + Bearer | stub path; durable hook unused |
| Succeed | `demo:echo` or `demo:dsl` | terminal `succeeded`; still no invented percent |

UI chrome for that path (served at `/` / `/ui`):

- Catalog `<select data-testid="spec-select">` + Open
- Editor canvas (`data-testid="canvas"`) + side panel + Validate
- Editor submit (`data-testid="submit-editor"`) and global submit (`data-testid="submit-global"`)
- Runs list / detail / status filter / cancel (`data-testid="runs-list"`, `run-detail`, `status-filter`, `cancel-run`)
- Progress copy: **“Progress omitted — stub did not report any.”**

Operator replay (local lab; same sequence as the unittest):

```bash
python3 ./platform_run.py
TOKEN=$(curl -sS -X POST http://127.0.0.1:18380/v0/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"guy.payeur@gp2.ca","password":"admin123!"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokens"]["accessToken"])')

curl -sS http://127.0.0.1:18380/v0/specs/sos
curl -sS http://127.0.0.1:18380/v0/specs/reserve
curl -sS -X POST http://127.0.0.1:18380/v0/graph/validate \
  -H 'Content-Type: application/json' \
  --data-binary @<(python3 -c 'import json,pathlib; print(json.dumps({"yaml": pathlib.Path("tests/fixtures/mini_graph.yaml").read_text()}))')

ID=$(curl -sS -X POST http://127.0.0.1:18380/v0/jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"demo":"sleep","seconds":8}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -sS "http://127.0.0.1:18380/v0/jobs/${ID}"   # no progress field
curl -sS -X POST "http://127.0.0.1:18380/v0/jobs/${ID}/cancel" \
  -H "Authorization: Bearer ${TOKEN}"
```

`python3 -m unittest tests.test_ux_journey -v` is the automated stamp. Do not claim a browser SPA e2e from that test.

## Side-by-side vs dsl-gui local-lab

Benchmark (read-only, not a lift): [getafix-seed-paul](https://github.com/guypayeur/getafix-seed-paul) `dsl-gui` @ `320dee4`. **Local-lab** means `isLocalAuth()` in `dsl-gui/src/components/runs/SubmitRunDialog.tsx` (and `dsl-backend` `localAuth`) — **not** the AWS Cognito / Spot / cost-estimate theater that the same SPA shows when local-lab is off.

| Surface | dsl-gui local-lab | guest-dsl day-one | Honest gap |
|---|---|---|---|
| Auth | `localAuth` / mock when Cognito unset | G6 HMAC login in editor chrome | Thinner. Anti-goal: no Cognito / MFA / RBAC |
| Open SOS / RESERVE | Editor opens seed `dsl-work` YAML (full graph) | Catalog stubs `sos` / `reserve` / `sos-lite` / `qa-reserve` | Stubs are pointers (`kind: catalog-stub`). Not a CuPy lift |
| Visual editor | React Flow canvas + side panel | In-guest equivalent canvas (G3) | Intention match. Not a SPA lift. No undo/redo, theme, mini-map, auto-layout |
| YAML I/O | Import / export / validate | `POST /v0/graph/parse\|export\|validate` | Roundtrip on stubs + mini graph. Unedited stubs stay the original blob |
| Files | FilesPage (Shared / Group / user S3 in SaaS) | G5 read-first `/files` over catalog + `fixtures/` | Accepted. Writes refused. No S3 |
| Submit labels | local-lab: **cpu / gpu / both** Getafix placement (explicitly not Spot / On-Demand) | G4: **cpu / gpu / both**; `both` → two G1 jobs | Intention match. Guest has no account-count / f32·f64 / variable-override dialog |
| What submit runs | POST `/api/v1/runs` → Getafix start of the engine | `POST /v0/jobs` WorkHandoff; `demo:dsl` digests the catalog stub | **Not** NSM / CuPy. Engines stay in runtime bindings |
| Watch | Runs list + detail; WebSocket when configured | Poll `GET /v0/jobs`; filter by status | Thinner. No WebSocket |
| Progress | Seed may show batch / percent when the backend reports it | **Omit when missing; never invent** | Honest. Stub exports no `progress` |
| Cancel | Run detail cancel | G1 stub cancel; durable hook only if installed | Stub cancel works. No Batch ECG / Watchdog |
| AI chat | Session 3 ChatPanel (seed) | G8 **Later** ([#10](https://github.com/guypayeur/panoramix-guest-dsl/issues/10)) | Does not block day-one path |
| Matryoshka | Nested-scope viz (seed / G9) | G9 **Later** ([#11](https://github.com/guypayeur/panoramix-guest-dsl/issues/11)) | Does not block day-one path |

AWS-only seed surfaces (cost dashboard, Spot pools, Watchdog, Cognito hosted UI, MFA, admin RBAC) are **anti-goals** here, not gaps to close.

## Gaps — filed or closed

| Gap | Disposition |
|---|---|
| Representative path missing | **Closed** — G3 + G4 + this probe |
| Invented progress / SPA lift claims | **Closed** — omitted; `react_flow: false` |
| Cognito / MFA / RBAC / Spot / S3 Shared | **Closed as anti-goals** |
| AI chat mutates graph | **Filed Later** — [#10](https://github.com/guypayeur/panoramix-guest-dsl/issues/10) |
| Matryoshka nested-scope viz | **Filed Later** — [#11](https://github.com/guypayeur/panoramix-guest-dsl/issues/11) |
| Full seed YAML / live engine from this guest | **Closed as anti-lift** — runtime bindings only |
| “Matches or beats live dsl-gui *feel*” | **Open for human review** — path exists; feel is thinner |

No new issues filed. Remaining feel gaps are accepted day-one thinner cuts or already-filed Later children.

## What this does not stamp

- `north_star_done` stays **false** until a human accepts the thinner feel *and* treats runtime R5 bar #1 as the perf box. This probe does not do that.
- Epic #1 remains open.
- Cloud [runtime#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [runtime#29](https://github.com/guypayeur/panoramix-runtime/issues/29) stay locked.
- This file does not unlock engines, fold Getafix, or lift the `dsl-gui` SPA.
