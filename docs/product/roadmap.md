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
| 1 | **Reconnaissance spike (SP-1)** | The five open questions in [ADR-0001](../architecture/decisions/0001-architecture-style.md) are answered with evidence, each with a source; ADR-0001 moves to `accepted` | **Active** |
| 2 | **Walking skeleton** | The chain runs end to end on toy data with fake simulators, in CI, with no Fortran toolchain present | Blocked by 1 |
| 3 | **Unified catalogue with provenance** | An ETNO snapshot is built from at least two real sources, with a manifest recording temporal cut and source hashes; rebuilding it from the same cut produces an identical hash | Blocked by 1 |
| 4 | **Selection functions behind one interface** | The same synthetic population is pushed through the OSSOS simulator and through sorcha via the same call, and both return detections in a common schema | Blocked by 3 |
| 5 | **Classical baseline reproduced** | Published results of the reference analysis are reproduced within stated tolerance over the same sample | Blocked by 4 |
| 6 | **Simulation campaign at scale** | A campaign survives an interrupted run and resumes without recomputing completed work; throughput measured in object-visits per unit time on both machines | Blocked by 4 |
| 7 | **Inference and diagnostics** | Posterior calibrated on synthetic populations with known truth; credible-interval coverage within tolerance | Blocked by 6 |
| 8 | **One-command reproduction** | Two tiered claims, named as such. **Reproducibility:** a clean clone regenerates every published figure and table from persisted artifacts — including the trained network — with one documented command. **Replicability:** a fresh master seed yields posterior and coverage compatible within a declared tolerance. Retraining from scratch is the replication claim, never the default path | Blocked by 7 |

Milestone 1 is a spike, so everything after it is marked blocked rather than
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
