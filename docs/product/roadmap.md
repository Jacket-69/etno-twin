# Roadmap — etno-twin

**Finish line for v1:** a third party can clone this repository and, with one command,
reproduce the full chain — unified catalogue → per-survey selection functions →
simulation campaign → neural posterior inference → calibration diagnostics — plus the
statistical power curve against the classical baseline over the same samples.

Milestones are coarse-grained and each one has a gate that is *constatable*: a
condition someone else can check, not a feeling. The thesis phases live in the vault
roadmap (`~/Documentos/CELAENO/Proyectos/Gemelo Digital Transneptuniano/Roadmap.md`);
this one tracks the software.

| # | Milestone | Gate | Status |
|---|---|---|---|
| 1 | **Reconnaissance spike (SP-1)** | The five open questions in [ADR-0001](../architecture/decisions/0001-architecture-style.md) are answered with evidence, each with a source; ADR-0001 moves to `accepted` | **Done — 2026-08-25** |
| 2 | **Walking skeleton** | The chain runs end to end on toy data with fake simulators, in CI, with no Fortran toolchain present | **Substantially met** by the SP-1 tracer bullet — the same DAG runs against both bindings and CI exercises the fake one. Formal close pending a review of the stage set against the real pipeline |
| 3 | **Unified catalogue with provenance** | An ETNO snapshot is built from at least two real sources, with a manifest recording temporal cut and source hashes; rebuilding it from the same cut produces an identical hash | **Next** — unblocked; the Rubin Science Platform account was approved 2026-08-25, so the ingestion schema can be built against the real `SSSource`/`SSObject` schema |
| 4 | **Selection functions behind one interface** | The same synthetic population is pushed through the OSSOS simulator and through sorcha via the same call, and both return detections in a common schema | Blocked by 3 |
| 5 | **Classical baseline reproduced** | Published results of the reference analysis are reproduced within stated tolerance over the same sample | Blocked by 4 |
| 6 | **Simulation campaign at scale** | A campaign survives an interrupted run and resumes without recomputing completed work; throughput measured in object-visits per unit time on both machines | Blocked by 4. **Resumption already demonstrated** on 2026-08-25: a 20,416-job run killed at 96 % resumed from artifacts without recomputation |
| 7 | **Inference and diagnostics** | Posterior calibrated on synthetic populations with known truth; credible-interval coverage within tolerance | Blocked by 6 |
| 8 | **One-command reproduction** | Two tiered claims, named as such. **Reproducibility:** a clean clone regenerates every published figure and table from persisted artifacts — including the trained network — with one documented command. **Replicability:** a fresh master seed yields posterior and coverage compatible within a declared tolerance. Retraining from scratch is the replication claim, never the default path | Blocked by 7 |

Milestone 1 closed on 2026-08-25 with [ADR-0001](../architecture/decisions/0001-architecture-style.md)
accepted and its evidence versioned under `docs/architecture/evidence/`. The spike was a
spike, so everything after it was marked blocked rather than
scheduled: the spike may change how milestones 2, 4 and 6 are built. Scope does not
change — the deliverables come from the thesis proposal — only the shape of the
implementation.

Milestone 8 is worded deliberately, and the wording was approved by the author on
2026-08-24 because it interprets a committed metric of the thesis proposal (§13,
"execution through a single command"). Bit-for-bit determinism is pursued at exactly two
points — input snapshots and the regeneration of final figures and tables — and **not**
through GPU training, which PyTorch does not guarantee. Chasing it there would make the
gate unreachable and turn the commitment into debt.

## Tracking profile

**Solo, no tracker.** There is no board: this table is the state of the project.
Progress is reported fortnightly to the thesis advisor. Requirements live in
`docs/requirements/requirements.md`, not in issues.
