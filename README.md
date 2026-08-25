# etno-twin

Reproducible pipeline for **population-level inference on extreme trans-Neptunian
objects (ETNOs)**, jointly propagating two sources of uncertainty that are currently
handled separately: the orbital degeneracy of short-arc detections (≥100 au in
semi-major axis for single-opposition objects) and the selection function of each
survey that produced them.

The scientific question is what can legitimately be claimed about the orbital
structure of the underlying population when both uncertainties are propagated
together — and how much statistical power that buys over current methods.

> **This repository is the object of a Bachelor's thesis in Computer Engineering**
> (Universidad Central de Chile, La Serena; defense expected ~August 2027). The
> engineering *is* the contribution: heterogeneous catalogue integration, temporal
> cut control over live data sources, simulation campaign orchestration,
> interoperability with legacy scientific software, and end-to-end reproducibility.
> The statistical inference is the instrument that demonstrates the system works.

## Status

**Phase 1 of 6 — Verification and baseline.** Nothing is implemented yet: the repo
was bootstrapped on 2026-08-24. The architectural style is still an open decision
(see [ADR-0001](docs/architecture/decisions/0001-architecture-style.md), status
`proposed`), pending the reconnaissance spike that is milestone 1 of the
[roadmap](docs/product/roadmap.md).

## What it will do

1. Ingest the public catalogue of ETNOs together with their astrometry and orbital
   uncertainties, from sources with different schemas, identities and reference
   frames, under versioned snapshots with explicit temporal cuts.
2. Model the selection function of each source survey, reusing existing public
   characterisations and adding Rubin/LSST through cadence simulation.
3. Generate synthetic populations under competing dynamical hypotheses and push them
   through those selection functions to produce simulated observed catalogues.
4. Infer the parameters of the underlying population via neural posterior estimation,
   treating each object as a distribution over orbits rather than a point estimate.
5. Quantify the statistical power achieved against the classical method, implemented
   in-project as a baseline over the same samples.

## Planned stack

Python · NumPy/Polars · [sorcha](https://sorcha.readthedocs.io) (Rubin survey
simulation) · [OSSOS Survey Simulator](https://github.com/OSSOS/SurveySimulator)
(classical surveys, Fortran) · ASSIST/REBOUND (dynamical propagation) ·
PyTorch with simulation-based inference libraries.

Nothing here is pinned yet: the stack is confirmed by ADR once the reconnaissance
spike measures the real integration surface of each tool.

## Methodology

Size **M · Standard** · Type **Library + CLI** · Process **Scrumban**.
Applied methodology and its deviations: [docs/methodology-applied.md](docs/methodology-applied.md).
Canonical source: personal vault ›
`~/Documentos/CELAENO/Conocimiento/Procesos/Metodología de Proyectos/_README.md`.

## Documentation

| Document | What is in it |
|---|---|
| [Vision](docs/product/vision.md) | Problem, gap, deliverables, success criteria |
| [Roadmap](docs/product/roadmap.md) | Milestones with verifiable gates |
| [Glossary](docs/product/glossary.md) | Domain vocabulary — read before the rest |
| [Requirements](docs/requirements/requirements.md) | Functional and non-functional requirements |
| [Architecture](docs/architecture/overview.md) | System overview and C4 levels 1–2 |
| [ADRs](docs/architecture/decisions/) | Technical decisions and their trade-offs |
| [Data provenance](docs/data/provenance.md) | Snapshots, temporal cuts, leakage control |
| [Testing strategy](docs/quality/testing-strategy.md) · [DoD](docs/quality/definition-of-done.md) | Quality gates |

## Project context

Planning, decision log and progress notes live outside this repository, in the
author's personal knowledge vault:

- README and current status — `~/Documentos/CELAENO/Proyectos/Gemelo Digital Transneptuniano/README.md`
- Decision log (rationale for direction) — `~/Documentos/CELAENO/Proyectos/Gemelo Digital Transneptuniano/decisiones.md`
- Work log — `~/Documentos/CELAENO/Proyectos/Gemelo Digital Transneptuniano/bitácora.md`

Direction decisions are recorded in the vault; technical decisions are recorded here
as ADRs.

## License

TODO — decide before the repository is used by third parties. Candidates: MIT
(maximum reuse) or BSD-3-Clause (common in astronomy tooling).
