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

Decoupling is an explicitly supported workflow, not a side effect: the documentation
describes simulating ahead of time *"on a cluster or using a different programming
language or environment"* and feeding the pairs in afterwards.

**Amortisation is not a preference here — the success criteria require it.**
`vision.md` commits to posterior calibration including credible-interval coverage as an
evaluable metric. Simulation-based calibration evaluates the posterior over ~200
additional synthetic observations, which is only affordable when the posterior is
amortised; global coverage analysis is computationally prohibitive otherwise
(Hermans et al., *A Trust Crisis in Simulation-Based Inference*,
[arXiv:2110.06581](https://arxiv.org/pdf/2110.06581)).

**Consequence for ADR-0001:** the main argument against an artifact pipeline —
"the training loop might need simulations on demand" — does not hold. Even multi-round
is batch-per-round, not per-sample: the coupling sits at round boundaries, exactly
where an artifact boundary would sit anyway.

**New provenance trap, found here:** because θ must be drawn from the prior, a stored
(θ, x) set is **only valid for the prior it was sampled from**. Changing the prior
silently invalidates the whole simulation artifact — the same class of failure
`provenance.md` exists to prevent, and its trap list did not cover it because it only
addressed source snapshots. The prior specification (distribution, hyperparameters,
version) is therefore a required field of the campaign manifest.

Sources: [sbi — getting started](https://sbi.readthedocs.io/en/stable/tutorials/00_getting_started.html) ·
[sbi — multi-round inference](https://sbi-dev.github.io/sbi/latest/tutorials/02_multiround_inference/) ·
[sbi — simulation-based calibration](https://sbi.readthedocs.io/en/latest/advanced_tutorials/11_diagnostics_simulation_based_calibration.html)

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

Verified in the documentation rather than inferred: chunk size is a configuration key
(`size_serial_chunk = 5000`), and the HPC page presents the multi-run pattern as the
supported workflow — example Slurm scripts, mass-run log checking, and *"a tool designed
to combine the results of multiple runs and the input files used into tables on a SQL
database"*.

**An in-process entry point exists, but it is exposed CLI plumbing, not a library
contract.** `runLSSTSimulation(args, sconfigs, return_only=False)` is importable and
appears in the autoapi, and with `return_only=True` it returns DataFrames in memory.
However: its `args` are file paths (pointing database, orbits, parameters — inputs are
staged on disk regardless), validation failures call `sys.exit(err)`, which kills the
calling process and is hostile to any in-memory port, and the documentation declares no
stability guarantee, being CLI-first throughout.

**Precision on the consequence:** the chunking loop lives *inside*
`runLSSTSimulation`, so wrapping it would not re-implement chunking. What would be
re-implemented is **collation across parallel runs**, because sorcha's parallelism is
process-level over files. The conclusion is unchanged: even in-process, inputs are
staged on disk and scale is achieved by many-processes-then-collate.

**Still open:** wall-clock time of a typical run at our scale, which is what decides
whether disk I/O is a bottleneck or noise. To be measured locally, not looked up — see
[the tracer bullet](#the-experiment-that-closes-the-spike).

Sources: [sorcha — getting started](https://sorcha.readthedocs.io/en/latest/gettingstarted.html) ·
[sorcha — HPC](https://sorcha.readthedocs.io/en/latest/hpc.html) ·
[`src/sorcha/sorcha.py`](https://github.com/dirac-institute/sorcha/blob/main/src/sorcha/sorcha.py) (read on `main`, not a pinned release) ·
[Sorcha AJ paper](https://iopscience.iop.org/article/10.3847/1538-3881/add3ec)

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
- **There is, however, a Python package inside the repository:** `python/ossssim`,
  installable with `pip install .` from a checkout. Its `setup.py` runs `make Modules`
  over the F95 sources at install time. **Consequence, and it is a hard one:**
  installing `ossssim` requires a Fortran toolchain, which collides with constraint 4
  (the core must be exercisable without Fortran). The package therefore cannot be a
  dependency of the core — only of the adapter, and CI cannot install it.
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

## Q3 — ASSIST/REBOUND: API shape, state format, checkpointing *(partially answered)*

REBOUND ships **Simulationarchive**, which provides *"exact reproducibility of N-body
simulations"* and documented restart examples (Rein & Tamayo 2017). If ASSIST is
compatible with it, checkpointing of the propagation stage is native — and the archive
*is* an artifact with a defined format, which reinforces rather than challenges the
artifact direction.

**Remaining sub-checks, both small:** ASSIST compatibility with Simulationarchive, and
size in bytes per particle-snapshot. Neither can revive the in-memory option.

Source: [REBOUND documentation](https://rebound.hanno-rein.de/)

## Q5 — Does a public pipeline already combine a survey simulator with SBI?

**Moved out of the ADR dependency chain.** It cannot change the architectural style;
it bears on the *novelty* of the thesis, which is specific objective 1 and has its own
protocol requirement (documented queries, sources, inclusion criteria, results table).
Kept here only as a pointer so the spike does not silently absorb it.

Search terms for that work: `"simulation-based inference" OR "neural posterior"` ×
`"survey simulator" OR "selection function"` × `TNO / KBO / trans-Neptunian`, plus the
neighbouring `ABC + debiasing + OSSOS`.

## Q6 — Who executes the DAG? *(new question, added 2026-08-24)*

Not in the original five, and it reorders the cost/benefit of the artifact option. The
"more machinery" objection to an artifact pipeline assumes the orchestrator gets
**built**. It does not have to be: Snakemake, DVC or even make provide resumption,
input hashing, cluster execution and selective regeneration off the shelf.

Cheap to answer: half a day of Snakemake over the tracer bullet below.

## Interim finding — the in-memory option is already out

Not because of the spike, but because of documents already accepted:

- `provenance.md` requires immutable, content-addressed snapshots with manifests at the
  input boundary.
- Roadmap milestone 6 requires resuming an interrupted campaign without recomputing
  completed work, and milestone 8 requires one-command reproduction from a clean clone.
- Constraint 1 requires the same code path on workstation and cluster, which do not
  share memory.

So **option B is dead on arrival**, and the real decision is A versus C: *where the
artifact discipline stops*. The findings above already located the seams — snapshot →
selection (provenance), survey-simulator outputs (sorcha's native model), campaign →
training (`append_simulations`). With the seams known, C's objection ("the seam gets
decided by whatever is urgent each week") is void, and A and C converge on the same
formulation: **artifacts at stage boundaries, memory within a stage.**

What is missing before this ADR can move to `accepted` is one number: the wall-clock
and byte cost at the boundaries.

## The experiment that closes the spike

**Tracer bullet at ~1% scale.** sorcha ships an official demo (`sorcha demo`) with a
one-year Rubin pointing database. The run: synthetic population of ~10³ objects →
sorcha → detections → train NPE with `sbi` on that toy → SBC with ~200 evaluations.
Measure at every boundary: bytes, wall-clock, and bytes per object-visit, to
extrapolate to real scale.

It answers the open half of Q1, sizes the artifacts, and doubles as the walking
skeleton of milestone 2 — with a real simulator instead of fakes. Days, not weeks.

**Simulation budget for NPE** is bracketed the same way rather than researched: train
the toy at 10³ and 10⁴ simulations and read the calibration trend. If the real budget
turns out to be ~10⁶, the campaign is a massive batch job and the artifact argument
becomes overwhelming; if it is ~10⁴ it fits in memory — and milestones 6 and 8 still
require persistence, so even that extreme does not revive option B.

**Open schema question to settle in the tracer bullet:** what exactly is `x` in the
training artifact. Persisting only hand-made summary statistics closes the door on
training embedding nets later without re-running the whole campaign. Store `x` at the
rawest affordable level — per-simulated-population detection catalogues — and let the
measurement say whether that is affordable.

