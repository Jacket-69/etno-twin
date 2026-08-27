---
adr: 0001
title: Architectural style of the pipeline
status: accepted
date: 2026-08-24
decided: 2026-08-25
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

**This decision is deliberately left open** until the reconnaissance spike measures the
real integration surface of the external tools, because a first pass showed the terrain
was not what had been assumed — in both directions. See
[SP-1](../spike-sp1-integration-surface.md) for findings and sources as they are
established.

## Decision

**Artifacts at stage boundaries, memory within a stage.** Options A and C converged on
this formulation once the spike located the seams; the tracer bullet then priced it, and
the price is not close.

Every stage is a pure `run(inputs, outdir, config)` that meets its neighbours only
through files with a declared schema and a manifest. No stage imports another. The
orchestrator is bought, not built.

**The number that decided it.** Inter-boundary I/O is noise against the cost it
separates. Composing a training dataset from detections takes **12 ms**; composing a
reweighted library takes **0.52 s**; a single survey-simulator run costs **28.25 s before
it looks at the first object**. Writing and reading artifacts costs under two per cent of
the cheapest step it sits between. The main objection to the artifact discipline — I/O
overhead — does not survive contact with the measurement.

**The cost model, from the sweep at N = 10 / 100 / 1000 with three repetitions each:**

```
T(N) = 28.25 s + N × 0.0256 s        R² = 0.99994
```

The simulator is almost entirely fixed cost. That single fact reorganises the project's
economics and is treated as a finding in its own right below.

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

## Interim finding (2026-08-24)

Option B is out, and not because of the spike: `provenance.md` requires
content-addressed snapshots at the input boundary, milestones 6 and 8 require campaign
resumption and one-command reproduction, and constraint 1 requires a code path shared
with a machine that does not share our memory. Those documents are already accepted.

The live decision is therefore **A versus C — where the artifact discipline stops** —
and the spike has located the seams: snapshot → selection, survey-simulator outputs,
campaign → training. With the seams known, C's objection collapses and both options
converge on the same formulation: *artifacts at stage boundaries, memory within a
stage.* One number is missing before this becomes `accepted`: the wall-clock and byte
cost at those boundaries, from the tracer bullet described in the spike note.

A scoping constraint comes with it, **decided on 2026-08-24**: the orchestrator is
**bought, not built**. The engineering contribution of this thesis is the domain
system — unified catalogue with provenance, selection functions behind one interface,
joint uncertainty propagation — not workflow middleware. *Which* orchestrator (Snakemake,
DVC, plain make) remains open and is decided with its own trade-off analysis once the
tracer bullet reports artifact shapes and sizes, and once the target cluster's scheduler
situation is known. See Q6 in the spike note.

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

## Evidence

From `docs/architecture/evidence/sp1-step2/`, produced by the step-2 tracer bullet on the
development workstation. 75 simulator runs, 75 seeds recovered, 75 distinct.

| Boundary | Measurement |
|---|---|
| Population → simulator inputs | 276 bytes/object · 2.8 ms to generate |
| Simulator run | fixed **28.25 s** · marginal **0.0256 s/object** · peak RSS **837 MB** |
| Detections | 270 bytes/detection · 10 % of objects detected, 3.2 detections each |
| Detections → (θ, x) pairs | raw **10.4 kB/pair** vs summarised **102 bytes/pair** — a ratio of 102 · composed in 12 ms |
| Reweighted library | composition **0.52 s** against **54 s** to simulate — a speed-up of 104× to 121× |
| Training and calibration | **5.2 s** at 10³ pairs, **19.8 s** at 10⁴ · persisted network **279.5 kB** · SBC over 200 evaluations |

**Training is not the bottleneck, and the replication claim now has a number.** Twenty
seconds of training against a simulator campaign measured in hours settles where the
budget goes. Running each budget under two master seeds — the experiment the design
insisted was free — shows central-50 coverage varying by 18 % relative between seeds at
10³ pairs and by 3 % at 10⁴. Statistical replication is therefore a property of the
simulation budget, not of the code, and the tolerance the thesis declares has to be
stated against a budget. *(Pairs produced by the fake binding: training wall-clock,
network bytes and calibration cannot depend on which simulator wrote the table. Nothing
in that row measures the survey simulator.)*

**Two estimators of fixed cost disagreed, and the disagreement was the point.** The
sweep fit says 28.25 s; summing the log phases believed to be size-independent says
13.61 s — a gap of 14.65 s. The gap is `ephemeris_generation`, classified as
N-dependent and in fact almost entirely fixed: it works over the pointing grid, not over
objects. The protocol was built to cross-check two estimators precisely so a
misclassification like this would surface instead of propagating. Reporting a single
estimator would have understated fixed cost by half.

**Resumption was demonstrated, not argued.** The training-budget run was killed by an
external `SIGTERM` at 96 % of 20,416 jobs and resumed from its artifacts without
recomputing completed work. Milestone 6's gate was exercised by accident, three
milestones early, and it is the strongest possible argument for this decision: the
in-memory option would have lost nineteen thousand completed simulations.

## Consequences

**1 · The campaign stage should simulate large populations per run, not many small
runs.** With marginal cost at 2.6 % of a second per object and fixed cost at 28 s, ten
runs of 100 objects cost 285 s while one run of 1,000 costs 54 s. Any design that calls
the simulator once per draw of θ is paying the fixed cost thousands of times over. This
inverts the assumption behind the step-1 extrapolation of ~335 CPU-days, which is
withdrawn: the same campaign is on the order of days, not months.

**2 · The reweighted library is viable, and its limit is now measured.** Against the
Farr criterion `N_eff > 4·N_obs`, with a 1,000-object library yielding 76 detections:

| Distance along the prior | N_eff (detected) | Out-of-support rejected | n_obs = 14 | n_obs = 40 | n_obs = 100 |
|---|---|---|---|---|---|
| 0.0 | 76.0 | 0 % | ✓ | ✗ | ✗ |
| 0.25 | 68.9 | 1.7 % | ✓ | ✗ | ✗ |
| 0.50 | 58.8 | 5.1 % | ✓ | ✗ | ✗ |
| 0.625 | 51.4 | 8.9 % | ✗ | ✗ | ✗ |
| 1.0 | 27.1 | 28.9 % | ✗ | ✗ | ✗ |

It holds to **half the prior range** for the sample the reference analysis actually
measured, and breaks between 0.5 and 0.625. It never holds for the larger scenarios at
this library size.

**This is a sizing result, not a rejection** — and consequence 1 is what makes it
cheap to act on. `N_eff` scales with the library's detected subset, and enlarging the
library costs marginal time only: a 10⁵-object library is roughly 43 minutes, paid once.
*(Extrapolated from the cost model, not measured.)* The campaign stage therefore splits
into **library-build** and **composition**, with an artifact boundary between them.

**3 · Store x raw at this scale.** The summarised table is 102× smaller, but the raw
table is 10.4 kB per pair — 10 MB for a thousand draws. Summarising is a decision to
defer, not to make now, and the raw artifact keeps every later choice open.

**4 · 837 MB per simulator run is the number that sizes a campaign worker.** It is what
decides how many run concurrently on one machine, and it is measured on the whole process
tree — measuring through the dispatcher reported 15 MB, an empty interpreter.

## Compliance / verification

- **Four import-linter contracts**, enforced in CI: stages independent of one another ·
  stages above bindings above kernel · **nothing in the package imports `sorcha`** ·
  only the training stage imports the neural stack.
- **The same DAG runs against a fake binding in CI** — no Fortran, no network, no 780 MB
  ephemeris cache — and against the real simulator on the workstation. The two experiment
  configurations differ in three lines, and a test asserts it.
- Every boundary writes a manifest; measurements land in `measurements.json`, never in
  prints.
- Seed recovery is covered by a canary test over a committed real log, including
  near-misses that must fail rather than parse.

## References

- Thesis proposal §5–§13 — `~/Documentos/CELAENO/Proyectos/Gemelo Digital Transneptuniano/Propuesta v1 — gemelo digital de la población transneptuniana extrema (2026-08-17).md`
- [sorcha — getting started](https://sorcha.readthedocs.io/en/latest/gettingstarted.html)
- [OSSOS SurveySimulator](https://github.com/OSSOS/SurveySimulator)
