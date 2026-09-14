# Catalog (G11)

In-guest specs the editor opens. Four rows match getafix-seed-paul `dsl-backend` `platform.ts`: `sos` / `reserve` / `sos-lite` / `qa-reserve`.

These files are **domain YAML** (formulas / structure / file maps). They are **not** a lift of the seed compute plane.

## Seed provenance

Benchmark (read-only): [getafix-seed-paul](https://github.com/guypayeur/getafix-seed-paul) @ `320dee4`.

| Catalog id | In-guest file | Seed `dsl-work` spec | What the editor should open |
|---|---|---|---|
| `sos` | `sos.yaml` | `spec_sos.yaml` | Full SOS graph (DataSources, loops, formulas, aggregations) |
| `reserve` | `reserve.yaml` | `spec_reserve_ifrs17.yaml` | Full RESERVE IFRS17 graph |
| `sos-lite` | `sos-lite.yaml` | `spec_sos_lite_t_outer_101_s_outer_100.yaml` | SOS with smaller outer loops |
| `qa-reserve` | `qa-reserve.yaml` | `qa_reserve_ifrs17.yaml` | QA file-pair graph (obtained vs expected) |

Copied/adapted as **read-only editor seed**. Guest `metadata` (last-key-wins) pins `id`, `entity`, `kind: graph`, `cupy: false`, `seed_file`, `seed_repo`, `seed_ref`. Seed comments that named the compute runner were dropped. RESERVE seed `engine.precision` is stored as `numeric.precision` (domain f32/f64 note, not a binding).

## Explicitly not vendored

- CuPy / NumPy kernels
- `dsl-work` engine / distributed runner / batch worker
- `dsl-work/src` kernel trees
- Getafix fold, Cognito, S3 Shared/Group

Engines stay in [panoramix-runtime](https://github.com/guypayeur/panoramix-runtime) bindings. `demo:dsl` on the G1 jobs seam still digests a tiny catalog pointer — it does **not** execute these graphs.

`north_star_done` stays **false**. Epic #1 remains open. Cloud stays locked.
