# North star (guest-dsl)

Owned with the runtime compute plane. **Do not stamp Done from G0–G11 alone.** Epic: [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1). Both boxes are required. G1–G6 are seams. **G7 landed** the honest UX journey probe ([docs/ux-journey.md](docs/ux-journey.md) + `tests/test_ux_journey.py`). **G10 landed** React Flow polish (undo/redo, minimap, auto-layout, localStorage). **G9 landed** Matryoshka nested-scope visualization. `north_star_done` stays **false**. Epic #1 remains open for human morning review.

Benchmark (read-only, not a lift): [getafix-seed-paul](https://github.com/guypayeur/getafix-seed-paul) `dsl-gui` / `dsl-gui-v2` (UX) and `dsl-work` (walls). Same pattern as sos vs iec.

## UX must-match checklist

Representative path: open an SOS or RESERVE-class spec → edit/validate → submit → watch → cancel. G7 documented that path. G10 closed the editor-feel gaps (React Flow, undo/redo, minimap, auto-layout, persistence). **G9 landed** Matryoshka nested-scope visualization (compound expand/collapse + drill-in). Remaining gaps vs live seed are stub jobs / omitted progress — not thinner chrome. G8 chat and G11 rich catalogs are landed.

Must-match intention (not a code lift):

- [x] **Visual editor** — canvas (DataSource / Loop / Formula / Aggregation) plus side panel (**G3 landed**; **G10** is real React Flow with undo/redo, minimap, auto-layout, pan/zoom/connect/multi-select — not a dsl-gui SPA lift). **G9** adds Matryoshka compound scopes (expand/collapse + drill-in). G7 probed the path; G10 closed the feel gap.
- [x] **YAML I/O** — import/export with a roundtrip-fidelity goal (**G3 landed**; **G11** against seed-shaped catalog graphs + a greenfield mini graph)
- [x] **Specs / files** — catalog open + specs / data / results browse (**G2 + G5 landed**). Editor opens a catalog spec (G3). Files page is read-first guest-local fixtures/catalog; writes fail closed; no S3 Shared/Group. Live run artifacts stay fixture stubs. G7 probed this honestly.
- [x] **Submit / runs / progress / cancel** — wired to the opaque WorkHandoff seam (**G4 landed** on G1; **G12** accounts / f32·f64 / optional overrides; editor + global submit; cpu/gpu/both labels; no Spot theater). G7 smoke-walked submit → watch → cancel (and succeed).
- [x] Progress is honest: omit when missing; never invent (**G4 landed**; stub exports no progress field; G7 re-asserted). **G13** surfaces hook-reported `stage` / `fraction` / `elapsed` only

Day-one may ship a thinner cut of the above. Later items that have now landed in the UX parity wave:

- [x] AI chat that mutates the DSL graph (**G8 landed** — [#10](https://github.com/guypayeur/panoramix-guest-dsl/issues/10); ChatPanel + SSE/MCP tools; live provider xAI Grok via `XAI_API_KEY` / `~/.xai`; fail closed without key; persist uses G6 Bearer)
- [x] Matryoshka nested-scope visualization (**G9 landed** — [#11](https://github.com/guypayeur/panoramix-guest-dsl/issues/11); compound scopes from catalog YAML / `parentId`; expand/collapse + drill-in; outer graph recoverable)

G7 probe is **honest**: the representative path exists and is smoke-tested. G10 matches dsl-gui editor *feel* on the canvas (React Flow + undo/redo + minimap + auto-layout) without lifting that SPA. **G9** matches dsl-gui-v2 Matryoshka nested-scope *intention* (not a SPA lift). **G11** replaced catalog stubs with seed-shaped domain graphs. **G12** is the submit dialog (accounts / f32·f64 / optional overrides). Stub jobs omit progress; **G13** copies hook-reported `stage` / `fraction` / `elapsed` only and does not invent stub percent. The UX box on [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) is **not** stamped Done — morning review should read [docs/ux-journey.md](docs/ux-journey.md). Epic #1 remains open. `north_star_done` stays **false**.

## Perf bars

Same-host comparison against seed `dsl-engine.py`. This **guest does not measure walls**. Runtime R1 locked the seed bar; runtime R5 compared the Panoramix path.

| # | Bar | Seed note | Status |
|---|---|---|---|
| 1 | RESERVE IFRS17 · 200k accounts · S=100 · production · **f32** wall ≤ seed on the **same** host | R1 same-host lock **38.25s** (LAPTOP-3DSCAN WSL · RTX 3080 Laptop). Runtime R5 live **34.23s** ([panoramix-runtime#170](https://github.com/guypayeur/panoramix-runtime/issues/170) / [#175](https://github.com/guypayeur/panoramix-runtime/issues/175); BEL match). Documented ~44s on the older seed note is **not** the lock. | Earned **on runtime** (not from this guest) |
| 2 | **f64** accuracy path | Seed production is f32 + Kahan; f64 is the accuracy bar | Deferred on R5 (out of that stamp) |
| 3 | **SoS nested** | Nested-scope / nested-model class | Deferred on R5 (`sos-nested` ≠ R1 50×100 SoS) |

Bar **#1** is required for the epic perf box. Bars #2 and #3 are ideally in the same pack (runtime R5). Do **not** invent numbers in this Git. `north_star_done` stays false until a human accepts both boxes.

## Anti-goals

- **Cognito** (or MFA TOTP / SaaS admin RBAC). **G6 landed:** thin local login / optional register + Bearer gate on mutating specs and jobs submit. **G3** adds a thin login form in the editor chrome — not a hosted UI / user pool. Box stays closed.
- **Batch ECG** / Watchdog / EC2 journal theater. **G4** submit labels are cpu / gpu / both only — no Spot / On-Demand picker.
- **Getafix fold** as a dependency of this Git.
- `ray:` / `temporal:` / `aws:` / `image:` on Unit or System YAML. Pin stays **0.5**.
- Lifting the CuPy / `dsl-work` engine into this guest Git. Engines stay in panoramix-runtime bindings.
- Cloud stays locked. This guest does not treat cloud runtime work as done.
- Treating [#1](https://github.com/guypayeur/panoramix-guest-dsl/issues/1) as Done because scaffold, stub jobs, a catalog API, a login gate, an editor MVP, files browse, runs UX, the G7 probe, or G10 React Flow exist. G7+G10 are not automatic Done. Epic #1 remains open.

## Child blast radii (not Done)

G0 scaffold · G1 opaque jobs seam · G2 specs catalog · G3 editor MVP · G4 runs UX · G5 files browse · G6 thin local auth · G7 UX journey probe · **G8 AI chat (ChatPanel + xAI Grok)** · **G10 React Flow polish** · **G11 rich catalog YAML (domain graphs; no CuPy lift)** · **G12 submit dialog (accounts / precision / overrides; no Spot)** · **G9 Matryoshka nested scopes** · **G13 durable progress (hook-reported stage/fraction/elapsed; stub still omits)**.

Runtime companions: R1 remeasure · R2 digest catalog · R3 local-dsl bindings · R4 guest-seam docs · R5 perf same-host pack.
