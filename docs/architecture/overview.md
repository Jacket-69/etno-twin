# Architecture overview

> **Blocked on [ADR-0001](decisions/0001-architecture-style.md)** (status `proposed`).
> The stage decomposition below is stable — it comes from the thesis proposal — but how
> stages compose (artifact pipeline, in-memory ports, or a hybrid with a declared seam)
> is the open decision that the reconnaissance spike resolves.

## Stages

1. **Catalogue** — ingest heterogeneous sources, resolve identity across them, attach
   orbital uncertainties, emit a versioned snapshot with a temporal cut.
2. **Selection** — per-survey selection functions behind one interface: the OSSOS
   Survey Simulator for classical surveys, sorcha for Rubin.
3. **Population** — generate synthetic populations under competing dynamical
   hypotheses, with dynamical propagation.
4. **Campaign** — run stages 2 and 3 at scale with parallelism, checkpoints and
   resumability.
5. **Inference** — neural posterior estimation over the forward model, plus the
   classical baseline over the same samples.
6. **Diagnostics** — calibration, coverage, statistical power curve.

## Cross-cutting concerns

- **Provenance** — see [data/provenance.md](../data/provenance.md). Snapshots and
  temporal cuts are first-class, not an afterthought of the catalogue stage.
- **Portability** — the same code path on workstation and cluster; scale is
  configuration, not a branch.
- **Testability without external toolchains** — the core must run against fake
  simulators so CI needs no Fortran.

TODO — component diagram and module boundaries once ADR-0001 is accepted.
