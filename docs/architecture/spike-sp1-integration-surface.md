# SP-1 — Integration surface of the external tools

> Reconnaissance spike, milestone 1 of the [roadmap](../product/roadmap.md). It answers
> the five open questions of [ADR-0001](decisions/0001-architecture-style.md) with
> evidence and sources, so the architectural style is chosen on measurements rather
> than assumptions. Findings are recorded here as they are established, not at the end.
>
> Status: **in progress**, started 2026-08-24.

## Q4 — Does the SBI library require a callable simulator? *(answered)*

**No. Pre-computed simulations are a first-class input.** The `sbi` package exposes
`.append_simulations(theta, x, proposal=proposal).train()`, which takes tensors of
parameters and simulated observations that were generated anywhere, by any process.

The distinction that matters for us is single-round versus multi-round inference:

- **Single-round (amortised):** simulate from the prior once, train on that set. The
  resulting posterior is valid for any observation. Simulation-heavy, but the
  simulation phase is a batch job that can be produced offline, in advance, by another
  system entirely.
- **Multi-round (sequential):** later rounds draw from the posterior obtained for a
  specific observation. More simulation-efficient, but *"it will lead to the posterior
  no longer being amortized"*, and it requires generating new simulations between
  rounds.

**Consequence for ADR-0001:** the main argument against an artifact pipeline —
"the training loop might need simulations on demand" — does not hold for amortised
inference, which is the mode this project needs. Even multi-round is batch-per-round,
not per-sample: the coupling is at round boundaries, which is exactly where an artifact
boundary would sit anyway.

Source: [sbi — multi-round inference tutorial](https://sbi-dev.github.io/sbi/latest/tutorials/02_multiround_inference/)

## Q1 — How does sorcha run and parallelise? *(partially answered)*

**sorcha is already an artifact-and-chunk engine, by design.**

- Built and *"extensively tested for HPC"*, intended to run both locally and on
  clusters, for *"repeated simulation of millions to billions of objects"*.
- **All inputs can be chunked:** it reads and iterates over segments of the input
  files in sequence, with chunk size set in the configuration file, so memory footprint
  is tuned per machine.
- Ships utility scripts to collate and explore the results of **multiple runs** —
  meaning the "many runs, then gather" pattern is the supported workflow, not a
  workaround.
- Python at the high level with a C/C++ backend where it matters.

**Consequence for ADR-0001:** the survey simulation stage is a file-based, chunked,
multi-run batch process whether we like it or not. Wrapping it in an in-memory port
would mean fighting its execution model and re-implementing chunking and collation on
top of it.

**Still open:** wall-clock time of a typical run at our scale, which is what decides
whether disk I/O is a bottleneck or noise. To be measured locally, not looked up.

Sources: [Sorcha: A Solar System Survey Simulator for LSST (AJ 2025)](https://iopscience.iop.org/article/10.3847/1538-3881/add3ec) ·
[arXiv:2506.02804](https://arxiv.org/abs/2506.02804) ·
[JOSS paper](https://joss.theoj.org/papers/10.21105/joss.08145.pdf)

## Q2 — OSSOS Survey Simulator: are the Python bindings first-class? *(answered — no)*

**No, and there is no PyPI distribution.** This corrects an earlier reading made from
search-result summaries rather than sources.

- The repository README states that `F77/python` and `F95/python` *"provide **examples**
  of building Python callable modules from the two fortran branches"*. Examples, not a
  supported interface.
- Installation is a manual build: *"Use `make ReadModelFromFile` to build a `Driver`
  program."*
- There is **no** `ossssim` package on PyPI (404). The `ossos` package that does exist
  (v3.1.18, authored by Kavelaars, Bannister and Rusk) is `OSSOS/MOP` — the Moving
  Object Pipeline — a different piece of software. What earlier search results
  surfaced was an open repository issue titled "Using the F95 Survey Sim for
  publication in PyPI": an intention, not a shipped artifact.
- Interface shape: a **Driver program** consuming a population model (lookup table such
  as the CFEPS L7 model, or parametric `.in` files) plus per-survey characterisation
  directories (pointing history and efficiency functions per block), producing a list
  of *detected* and *tracked* model objects.

**Consequences for ADR-0001.** Two, pulling in the same direction:

1. **Interoperating with the Fortran reference implementation is real work**, not a
   solved problem. It is also, precisely, the "interoperability with legacy scientific
   software" that the thesis claims as part of its engineering contribution — so this
   is a cost that buys thesis-relevant evidence rather than a cost to avoid.
2. Both simulators are therefore **process-and-file oriented at their supported
   interface**: sorcha through chunked runs plus collation, the OSSOS simulator through
   a compiled Driver over characterisation directories. An in-memory port over either
   would be a facade we maintain on top of an execution model we do not control.

Sources: [SurveySimulator README](https://github.com/OSSOS/SurveySimulator/blob/master/README.md) ·
[PyPI JSON API for `ossos`](https://pypi.org/pypi/ossos/json) (queried 2026-08-24) ·
[`ossssim` on PyPI: 404](https://pypi.org/pypi/ossssim/json)

### Correction of the record

The bootstrap of this repository justified leaving ADR-0001 open by stating that the
OSSOS simulator "ships Python bindings and a PyPI distribution". That is wrong: the
bindings are examples and the PyPI distribution does not exist. **Leaving the ADR open
was still the right call — the terrain was different from what was assumed, in both
directions — but the reason is "it had not been measured", not "it is easier than
expected".**

## Q3 — ASSIST/REBOUND: API shape, state format, checkpointing

Pending.

## Q5 — Does a public pipeline already combine a survey simulator with SBI?

Pending. Also feeds the formal novelty verification (specific objective 1 of the
thesis).
