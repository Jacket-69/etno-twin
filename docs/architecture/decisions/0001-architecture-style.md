---
adr: 0001
title: Architectural style of the pipeline
status: proposed
date: 2026-08-24
deciders: Benjamín López Huidobro
tags: [adr, arquitectura]
---

# ADR 0001 — Architectural style of the pipeline

## Context

etno-twin chains six stages: unified ETNO catalogue with orbital uncertainty
(heterogeneous sources — MPC, DES, OSSOS, CFEPS) → per-survey selection functions
(OSSOS Survey Simulator in Fortran 77/95, sorcha in Python for Rubin) → synthetic
population generation with dynamical propagation (ASSIST/REBOUND) → parallel
simulation campaigns with checkpoints and fault tolerance → SBI/NPE inference in
PyTorch plus a classical baseline → calibration diagnostics.

Four hard constraints shape the style:

1. The same code must run on a personal workstation with reduced samples and on
   larger compute, without a rewrite.
2. Catalogues are live streams: snapshots must be versioned and temporal cuts
   enforced, because leakage invalidates results silently.
3. Reproducing a full experiment must cost one command — it is a committed, evaluable
   metric of the thesis, not an aspiration.
4. Tests must cover data transformation and integration with external simulators,
   which means the core has to be exercisable without running Fortran.

**This decision is deliberately left open.** A first reconnaissance search on
2026-08-24 invalidated the assumption that wrapping the Fortran simulator would be the
hard part: the OSSOS Survey Simulator ships `F77/python` and `F95/python` callable
modules and a PyPI distribution that compiles the Fortran at install time, and sorcha
— though canonically a CLI over files — can also be driven from Python. If one search
changed the terrain, the terrain is not yet known well enough to choose.

## Decision

*Pending.* To be decided once the reconnaissance spike (milestone 1 of the
[roadmap](../../product/roadmap.md)) answers the open questions below. This ADR moves
to `accepted` with the chosen option and its rationale at that point.

## Alternatives considered

### Option A — Artifact pipeline

Every stage is a pure file→file function with a manifest (hash of inputs, code
version, seed); an orchestrator chains pure stages.

- Pros: resuming after a crash in a multi-hour campaign is free; the cluster runs the
  same stages without modification because it shares a filesystem, not memory; a
  versioned snapshot with a temporal cut is naturally an artifact with a hash; tests
  compare against small golden files.
- Cons: I/O overhead; requires discipline about inter-stage schemas; may be wasteful
  if the SBI training loop needs simulations on demand rather than pre-computed.

### Option B — In-memory orchestration (classical hexagonal)

The core calls ports (SurveySimulator, CatalogSource, Propagator, InferenceBackend)
and data lives in memory between stages.

- Pros: faster to write and to iterate on early; natural fit if the SBI library
  expects a Python callable as the simulator.
- Cons: a long campaign that crashes loses everything; reproducing a result requires
  re-running the whole chain; the "runs identically on the cluster" claim becomes
  aspirational.

### Option C — Hybrid with a declared seam

Artifacts between major phases, memory within a phase.

- Pros: likely where the system ends up regardless.
- Cons: choosing it *now*, without stating where the seam goes, tends to mean the seam
  gets decided by whatever is urgent each week.

## Open questions (the spike answers these)

1. **sorcha** — is in-process invocation supported, or is the CLI the real path? How
   does it parallelise? How long does a typical run take? *(This last one decides
   whether disk I/O is a bottleneck or noise.)*
2. **OSSOS Survey Simulator** — are the Python bindings first-class or examples? Does
   it install from PyPI compiling the Fortran? What format are the CFEPS/OSSOS
   characterisation files in?
3. **ASSIST/REBOUND** — API shape, state format, whether checkpointing exists already.
4. **SBI library** — does it require a Python callable simulator, or does it accept
   pre-computed offline simulations? If offline works, the artifact pipeline loses its
   main cost and the decision resolves itself.
5. Does a public pipeline already combine a survey simulator with SBI? *(Also feeds
   the formal novelty verification, which is specific objective 1 of the thesis.)*

## Consequences

To be completed when the decision is made.

## Compliance / verification

To be completed when the decision is made. Expected mechanism: import-linter contracts
over module boundaries, plus an integration test that exercises the core against fake
simulators with no Fortran toolchain present.

## References

- Thesis proposal §5–§13 — `~/Documentos/CELAENO/Proyectos/Gemelo Digital Transneptuniano/Propuesta v1 — gemelo digital de la población transneptuniana extrema (2026-08-17).md`
- [sorcha — getting started](https://sorcha.readthedocs.io/en/latest/gettingstarted.html)
- [OSSOS SurveySimulator](https://github.com/OSSOS/SurveySimulator)
