# North star (guest-dsl)

Owned with the runtime compute plane. **Do not stamp Done from G0/G1/G2/G3/G5/G6.** Epic: [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1). Both boxes are required; neither is the opaque jobs seam, the specs catalog HTTP, the editor MVP, files browse, or the local login gate. G1 landed a stub `POST /v0/jobs`. G2 landed `GET`/`PUT /v0/specs` (thin stubs + overlay). G6 landed thin local auth (HMAC tokens; not Cognito). G3 landed the in-guest editor (`GET /` / `/ui`, YAML I/O, validate). G5 landed read-first specs / data / results browse (`GET /v0/files`, `/files`). Those do **not** flip the UX or perf box.

Benchmark (read-only, not a lift): [getafix-seed-paul](https://github.com/guypayeur/getafix-seed-paul) `dsl-gui` / `dsl-gui-v2` (UX) and `dsl-work` (walls). Same pattern as sos vs iec.

## UX must-match checklist

Representative path: open an SOS or RESERVE-class spec → edit/validate → submit → watch → cancel. Day-one **is thinner** than live `dsl-gui` local-lab. G7 owns the honest side-by-side probe.

Must-match intention (not a code lift):

- [x] **Visual editor** — canvas (DataSource / Loop / Formula / Aggregation) plus side panel (**G3 landed**; in-guest equivalent canvas, not a dsl-gui SPA lift). G7 still owns the honest side-by-side probe.
- [x] **YAML I/O** — import/export with a roundtrip-fidelity goal (**G3 landed** against G2 catalog stubs + a greenfield mini graph)
- [x] **Specs / files** — catalog open + specs / data / results browse (**G2 + G5 landed**). Editor opens a catalog spec (G3). Files page is read-first guest-local fixtures/catalog; writes fail closed; no S3 Shared/Group. Live run artifacts wait for G4. G7 still owns the honest side-by-side probe.
- [ ] **Submit / runs / progress / cancel** — wired to the opaque WorkHandoff seam (G1, G4)
- [ ] Progress is honest: omit when missing; never invent

Day-one may ship a thinner cut of the above. Later (does **not** block epic Done):

- [ ] AI chat that mutates the DSL graph (G8)
- [ ] Matryoshka nested-scope visualization (G9)

The UX box on [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) may flip only when G7 is honest. This file does **not** close it.

## Perf bars

Same-host comparison against seed `dsl-engine.py`. Remeasure the seed on the lab GPU **before** locking SLOs (runtime R1). The documented seed wall below is **not** the locked bar.

| # | Bar | Seed note | Status |
|---|---|---|---|
| 1 | RESERVE IFRS17 · 200k accounts · S=100 · production · **f32** wall ≤ seed on the **same** host | ~**44s** documented on RTX 3080 Laptop in getafix-seed-paul [`dsl-work/docs/PERFORMANCE_COMPARISON.md`](https://github.com/guypayeur/getafix-seed-paul/blob/main/dsl-work/docs/PERFORMANCE_COMPARISON.md) | Remeasure before locking |
| 2 | **f64** accuracy path | Seed production is f32 + Kahan; f64 is the accuracy bar | Open |
| 3 | **SoS nested** | Nested-scope / nested-model class | Open |

Bar **#1** is required for the epic perf box. Bars #2 and #3 are ideally in the same pack (runtime R5). Do **not** claim a wall from this guest. Do **not** invent numbers.

## Anti-goals

- **Cognito** (or MFA TOTP / SaaS admin RBAC). **G6 landed:** thin local login / optional register + Bearer gate on mutating specs and jobs submit. **G3** adds a thin login form in the editor chrome — not a hosted UI / user pool. Box stays closed.
- **Batch ECG** / Watchdog / EC2 journal theater.
- **Getafix fold** as a dependency of this Git.
- `ray:` / `temporal:` / `aws:` / `image:` on Unit or System YAML. Pin stays **0.5**.
- Lifting the CuPy / `dsl-work` engine into this guest Git. Engines stay in panoramix-runtime bindings.
- Unlocking cloud [runtime#61](https://github.com/guypayeur/panoramix-runtime/issues/61) / [runtime#29](https://github.com/guypayeur/panoramix-runtime/issues/29) from this repo.
- Treating [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) as Done because scaffold, stub jobs, a catalog API, a login gate, an editor MVP, or files browse exist. G1/G2/G3/G5/G6 are seams only. Epic #1 remains open.

## Child blast radii (not Done)

G0 scaffold · G1 opaque jobs seam · G2 specs catalog · G3 editor MVP · G4 runs UX · **G5 files browse (this repo; specs / data / results, read-first)** · G6 thin local auth · G7 UX journey probe · G8 AI chat (**Later**) · G9 Matryoshka (**Later**).

Runtime companions: R1 remeasure · R2 digest catalog · R3 local-dsl bindings · R4 guest-seam docs · R5 perf same-host pack.
