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

**Phase 1 of 6 — Verification and baseline.** The repository was bootstrapped on
2026-08-24. What exists so far is the reconnaissance spike that is milestone 1 of the
[roadmap](docs/product/roadmap.md): a tracer bullet that walks the whole chain at toy
scale — against the real Rubin survey simulator on a workstation, and against a fake one
in continuous integration — measuring wall-clock and bytes at every stage boundary. How
those numbers are produced, and what is held constant to produce them, is written down
before they are used: [measurement protocol](docs/architecture/spike-sp1-measurement-protocol.md).

None of the five capabilities described below is implemented yet; the spike exercises
their shape, not their content. The architectural style remains an open decision — see
[ADR-0001](docs/architecture/decisions/0001-architecture-style.md), status `proposed` —
until the measurements are in.

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
| [SP-1 spike](docs/architecture/spike-sp1-integration-surface.md) · [design](docs/architecture/spike-sp1-step2-design.md) · [protocol](docs/architecture/spike-sp1-measurement-protocol.md) | What was measured about the external tools, and how |
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

**GPL-3.0-only.** See [LICENSE](LICENSE).

Chosen deliberately over a permissive licence. The scientific tools this project builds
on are copyleft — sorcha carries GPLv3 on the modules that implement the selection
function, and REBOUND and ASSIST are GPL-3.0 — so a permissive licence would turn the
process boundary between this code and those tools into a legal requirement rather than
an engineering decision. Under GPL-3.0 that boundary can be placed wherever the
measurements say it belongs.

The OSSOS Survey Simulator is distributed under EUPL v1.1; interoperating with it across
a process boundary is unaffected, but its compatibility list must be checked before any
of its code is vendored into this repository.
