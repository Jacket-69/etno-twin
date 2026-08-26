# SP-1 step 2 — the measurement protocol

> How the numbers in `measurements.json` are produced, written down before they are used
> to close [ADR-0001](decisions/0001-architecture-style.md). The design of the step is in
> [the step-2 design note](spike-sp1-step2-design.md); this document is the *method*, so
> that anyone reading a number can see what was held constant to obtain it.
>
> A measurement whose protocol is not written down is an anecdote. The whole point of
> this step is to replace an extrapolation nobody can audit with numbers somebody can.

## What the pipeline is

Seven stages, each a module under `src/etno_twin/stages/` exposing a pure
`run(inputs, outdir, config)` and its own entry point, chained by a Snakefile.

| Stage | Boundary it measures |
|---|---|
| `snapshot` | none — it fingerprints the external data so nothing else has to |
| `population` | population parameters → simulator inputs |
| `campaign` | the simulator run |
| `dataset` | detections → (parameters, observations) pairs |
| `training` | training and calibration |
| `library` | reweighted-library viability |
| `collate` | none — it folds every stage manifest into one `measurements.json` |

**Stages do not import each other.** They meet only through files whose schema is declared
in `etno_twin.kernel.schemas`, and four import-linter contracts enforce it rather than
trusting it — including one that forbids `import sorcha` anywhere in the package, and one
that confines PyTorch to the training stage. `uv run lint-imports` checks them, and so does
continuous integration.

One command runs an experiment, and it points at one configuration file:

```bash
uv run snakemake --cores 1 --resources bench_slot=1 \
    --config experiment=experiments/smoke-fake.toml
```

## The rules that make a number a measurement

### 1 · Only the thing under test is inside the timed region

Hashing snapshots, fingerprinting the ephemeris cache, counting rows and writing manifests
all happen outside every stopwatch. In the campaign stage the timed region contains
exactly one thing: the child process.

Wall-clock comes from `time.perf_counter`, not the system clock, so a clock adjustment
mid-run cannot move a measurement.

### 2 · The simulator is measured as a process, and it is the *right* process

The simulator always runs as a child process, for both bindings. That is not caution about
a crash-prone dependency — it is the seam ADR-0001 is deciding about, and a stage that
called the simulator in-process would work and would prove nothing.

Timing from the parent means interpreter start-up is counted. That is deliberate: process
start-up is part of the fixed cost the sweep exists to quantify.

Two traps here, both found by running it:

- **`sorcha run` is a dispatcher.** It resolves the verb and spawns `sorcha-<verb>` as a
  *second* process. Driving it puts a wrapper's start-up inside every timing and points
  every per-process instrument at the wrapper. The first peak-memory figure this spike
  produced was 15 MB — a bare interpreter, not a simulator holding planetary ephemerides.
  The binding invokes the worker, `sorcha-run`, directly.
- **Peak memory is polled across the process tree.** `ru_maxrss` for children is a
  high-water mark over every child the parent ever reaped, so it would silently report the
  largest *earlier* run. Instead the probe reads `VmHWM` — the kernel's own high-water
  mark — for the child and every descendant, every 25 ms, and reports the largest single
  process. Polling has a floor: a process that lives for a few tens of milliseconds is
  sampled once or twice, before it has allocated anything, so the sample count is
  recorded and a figure below a handful of samples is flagged unreliable and excluded
  from the collation rather than reported as a measurement.

### 3 · Fixed cost is separated from marginal cost twice, by independent routes

The cost model is `T(N) = T_fixed + N · t_marginal`. A single population size cannot
separate the two terms, which is the known defect of the extrapolation this step replaces.

**Route one — the ladder.** Run the sweep of population sizes declared in
`[campaign].sweep_objects`, several repetitions each, and fit a straight line. Repetitions
at the same size are reduced by their **median**, not their mean, so one descheduled run
cannot move the estimate. The intercept is `T_fixed`, the slope is `t_marginal`, and the
coefficient of determination is reported alongside so a bad fit is visible rather than
averaged away.

**Route two — the run's own log.** Every run's log is parsed into named phases from the
timestamps that bracket them, and the phases that cannot depend on population size are
added up:

| Phase | Size-dependent? |
|---|---|
| `startup` | no |
| `pointing_database` | no — reading 216,233 visits is paid once |
| `ephemeris_setup` | no — loading the ephemeris kernels is paid once |
| `input_read` | yes |
| `nbody_setup` | yes |
| `ephemeris_generation` | yes |
| `post_processing` | yes |

Plus `interpreter_startup`, the difference between what the parent measured and the span
the log covers: importing the simulator's package happens before its first log line.

**The classification above is a hypothesis under test, not an assertion.** The two routes
use different data. Agreement is evidence the classification is right; disagreement says it
is wrong, which is worth knowing before a campaign is sized on it. `measurements.json`
therefore reports both numbers and their difference side by side, under
`cost_model.fixed_cost_agreement`.

The phase markers are log messages, not API. They are pinned in
`etno_twin.simulators.sorcha_adapter` and asserted by the canary tests, so a version bump
that renames one fails a test instead of silently shifting a number.

### 4 · The machine is warm, and only one run is measured at a time

- **Warm-up.** `[campaign].warmup_runs` runs execute before any measured run. They are
  recorded in full, marked `warmup`, and excluded from the fit. The dependency is real, not
  a scheduling hint: in the workflow graph every measured run takes the warm-up manifests
  as inputs, so a measurement cannot be taken before a cold page cache has been paid for.
- **Serialisation.** Every rule that invokes the simulator claims `bench_slot`, and runs
  are launched with `--resources bench_slot=1`. Two simulator processes sharing a machine
  measure contention, not cost. A run whose numbers matter is launched with that flag.
- **The ephemeris cache is warm and constant.** It is fingerprinted once, in its own stage,
  and its content digest is recorded in every campaign manifest — so "the same cache" is a
  checkable claim across runs and across machines, not an assumption. Nothing in the
  pipeline downloads it: a missing cache is an error naming the problem.

### 5 · The seed is recovered from every run, never pinned

Neither binding takes a seed from the caller. The simulator's own source warns that
re-using seeds between simulations produces hard-to-detect correlations, and its authors
state a fixed seed is for testing and "should never be used for science results" — the
stochasticity is part of the forward model the inference has to learn.

So the protocol is: **record, do not pin.** Each run's seed is parsed out of its log with

```
the base rng seed is (\d+)
```

and a run whose seed cannot be recovered raises rather than writing `null` into a manifest
— an artifact that looks complete and is not is worse than a missing one.

Because that depends on a log message rather than an API, it is guarded twice:

- `tests/test_simulator_contract.py` asserts the pattern against a committed excerpt of a
  real run log, and asserts that near-misses (`the base rng seed was 42`, `RNG` in capitals)
  do *not* match. It runs in continuous integration, on a machine with nothing installed.
- `tests/test_sorcha_binding.py`, marked `integration` and never run in continuous
  integration, asserts the same thing against a live run.

Campaign seeds are derived, not incremented: each stream seed is
`BLAKE2b("<master>/<label>")`, so the campaign is reproducible from one recorded master
seed while neighbouring labels get unrelated streams.

### 6 · Every input is content-addressed, the demo files included

The `snapshot` stage hashes the shared survey configuration, the pointing source and — for
the real binding — every file of the ephemeris cache, folding them into one digest. Full
SHA-256, not size and modification time: a reviewer asking "why modification time?" is a
question with no good answer, and hashing 780 MB costs a second or two once per experiment,
outside every timed region.

Each stage manifest additionally carries the prior specification and the code version. A
stored set of pairs is valid **only** for the prior its parameters were drawn from, and
nothing in the data reveals a mismatch, so the training stage refuses a dataset whose prior
fingerprint differs from the one it declares.

### 7 · The ladders are configuration

Both of them. `[campaign].sweep_objects` is the ladder of population sizes;
`[library].theta_ladder_scale` is the ladder of parameter distances, in units of prior
width. Neither appears as a constant in any stage. Extending a ladder is an edit to a
configuration file, and the file's digest is in every manifest that resulted from it.

The ladder's direction is normalised so that a distance of 1 moves one prior width *in
total* — otherwise adding a parameter to the model would silently change the step size.

### 8 · Nothing is printed

Measurements are written to manifests next to the artifacts they describe, and folded by
the `collate` stage into one `measurements.json` per experiment. Each stage records its own,
which is what keeps the stages independent; the collation is what gives the ADR a single
artifact to cite.

## The effective sample size, stated explicitly

The reweighted-library measurement reports **Kish's effective sample size**:

```
N_eff = (Σ wᵢ)² / Σ wᵢ²
```

Stated in full here and in the docstring of `etno_twin.kernel.stats.kish_effective_sample_size`
because "effective sample size" names several different estimators in the literature, and
the ADR will cite this one. It equals the sample size when all weights are equal and
collapses towards one as a single weight comes to dominate. It is invariant to a common
scale factor, so the weights are left unnormalised.

The criterion reported against is

```
N_eff > 4 · N_obs        (Farr 2019, arXiv:1904.10879, after equation 12)
```

imported from hierarchical inference, where it is established, and applied here to a use it
has not been applied to. That application is the point: a simulation bank built once and
importance-sampled from is already a working part of a published neural-posterior-estimation
pipeline, and **neither link of that genealogy gives a quantitative criterion for when the
substitution stops being valid**.

`N_eff` is reported twice per rung and the criterion is applied to one of them:

- `n_eff_library` — over the whole library. Diagnostic.
- `n_eff_detected` — over the library members the survey actually detected. **This is what
  the criterion is applied to**, because those are the objects a composed dataset is built
  from, and it is recorded as such in the manifest under
  `n_eff_criterion.reported_against`.

Alongside it, per rung: the fraction of the library the target parameters exclude outright,
the wall-clock of composing the rung, and the wall-clock of the simulation that built the
library — read from that run's manifest rather than re-run, so the comparison does not
itself pay for a simulation.

### Why the rejected fraction is not a column of zeros

The toy population model truncates its inclination distribution at a configured multiple of
its own width, so the **support depends on the parameters**. Walking towards a narrower
inclination distribution therefore pushes part of the library outside the target's support:
the model at those parameters says those objects do not exist, and no amount of reweighting
can make the library speak for them. Those members get weight zero and are counted.

## The double binding

The same graph, the same stage code, the same configuration file, two ports.

|  | workstation | continuous integration |
|---|---|---|
| binding | `sorcha` | `fake` |
| pointing source | 17 MB database inside the installed wheel | 480-visit committed fixture |
| ephemerides | 780 MB cache, pre-existing | none |
| survey configuration | `fixtures/sorcha/etno-twin-demo.ini` | the same file |

`experiments/smoke-fake.toml` and `experiments/smoke-sorcha.toml` differ in exactly three
lines — name, output directory, binding — and a test asserts that every other section is
identical, so "same graph, different port" is checkable rather than claimed.

The fake binding is not an astronomical model and does not pretend to be: object positions
on the sky are drawn rather than computed. What it reproduces is the *structure* the
pipeline depends on — detection depends on the orbit and the absolute magnitude and never
on the population parameters; the same three filters, read from the same configuration
file; a seed drawn from the operating system and recorded in the log. Stages that consume
detections from either binding may read only the columns the port declares meaningful in
both, which the schema states and a test checks.

### Two divergences the port absorbs, both found by running it

1. **An empty catalogue.** When the linking filter empties a chunk, the real simulator exits
   zero and writes *no output file at all*; the fake writes an empty table with a header.
   Both are successful runs of a population the survey could not see. The adapter
   normalises: if a run completed and its log says it had nothing to write, an empty
   schema-valid table is created and the manifest records that it was synthesised. If the
   log does *not* account for the absence, the stage raises — inventing an empty artifact
   for a dead worker would turn a failure into a data point.
2. **Stale artifacts on a retry.** The real simulator decorates its log filename with a
   timestamp and a process id, so a retried run leaves the previous log in place, and a
   directory holding two logs is a directory where "which seed did this run use?" has two
   answers. Its force flag overwrites the output file and not the log. The campaign stage
   therefore clears the artifacts of its own stem before invoking the binding: a stage owns
   its output directory and rebuilds it, rather than adding to it.

Both are recorded here rather than only in code because both are exactly the failure mode
the design names — the fake and the real simulator drifting apart — and both would have
surfaced as a missing artifact partway into a campaign.

## What the smoke run does and does not establish

The smoke experiment is ten objects per population and one rung of the size ladder. It
establishes that the chain walks end to end on both ports, that every manifest is written,
that every seed is recovered, and that the collation produces a `measurements.json`. It
establishes nothing about cost, and says so in its own output: with one population size the
collation reports `fit.available: false` and names the reason.

Three things are visibly starved at smoke scale and are the sweep's job, not the smoke's:

- The cost model needs the full `10 / 100 / 1000` ladder with repetitions.
- The effective-sample-size ladder needs a library large enough that the *detected* subset
  is not a handful of objects.
- Simulation-based calibration over a few evaluations is a smoke test of the plumbing. Its
  numbers are not calibration evidence and must not be read as any.

## What the smoke actually produced, 2026-08-25

Both bindings, same graph, same sizes: ten objects per population, sixteen draws, one
warm-up run, one rung of the size ladder, one library, two trainings. Recorded here
because the experiment output trees are regenerable and therefore not committed, so
without this the numbers would have no durable home until the sweep runs.

**Read these as a proof that the chain walks, not as evidence about cost.** The
collation says so itself: with one population size it reports `fit.available: false` and
names the reason.

| | sorcha binding | fake binding |
|---|---|---|
| Runs completed | 19 | 19 |
| Seeds recovered from the log | 19 / 19 | 19 / 19 |
| Wall-clock, N = 10 | 28.19 s | 0.046 s |
| Peak worker memory | **741 MB** | not reportable — see below |
| Objects detected, median per draw | 10 % | 20 % |
| Detections per object, median | 2.7 | 21.4 |
| Bytes per detection | 271 | 219 |
| Detections, raw, 16 draws | 224.9 kB | 749.1 kB |
| Training pairs, summarised | 1.83 kB | 1.88 kB |
| Raw-to-summary ratio | **123 ×** | 398 × |
| Persisted network | 279.5 kB | 279.5 kB |
| Training wall-clock, 12 simulations | 0.47 – 0.51 s | 0.50 s |

Four of these are worth pulling out.

**Peak memory of a worker is 741 MB, and it is a constraint rather than a curiosity.**
It is what decides how many campaign workers fit on a machine, and it is the reason the
instrument had to be got right: measured through the dispatcher it read 15 MB.

**The fake binding's memory figure is not reported at all.** Its runs last 46 ms, which
is one or two polls — taken before the process had allocated anything. The collation
excludes runs the probe could not sample and says why, rather than folding an
underestimate into a maximum.

**The fixed/marginal split, from one run's log**: 13.52 s fixed — 11.48 s in the phases
that cannot depend on population size, plus 2.04 s of interpreter start-up before the
first log line — against 14.67 s in the size-dependent phases, or about 1.47 s per
object. **This is the log-derived estimate from a single run, not the fit.** The second
estimator needs the ladder, and cross-checking the two against each other is the point of
having both.

**Six of the nineteen real runs produced no output file**, the library among them: five
draws plus the library run detected nothing, the linking filter emptied their chunks, and
sorcha exited zero without writing. Every one of them became an empty schema-valid table
with the manifest recording that it was synthesised. Without that normalisation the graph
stops a third of the way through, which is exactly how it was found.

### The ladder is starved at this scale, and that is informative

The library run detected **zero** objects under the real binding and two under the fake
one, so `n_eff_detected` — the quantity the criterion is applied to — is 0 and 2 across
every rung. The reweighted-library measurement therefore proved its plumbing here and
nothing else.

What did behave as designed is the diagnostic over the whole library, which is
independent of what the survey saw:

| Rung (prior widths from the reference) | 0 | 0.25 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|
| `n_eff_library` (of 10) | 10.00 | 9.65 | 8.41 | 6.09 | 3.25 |
| Fraction rejected as out of support | 0 | 0 | 0 | 0 | 0.20 |

The effective sample size erodes monotonically as the parameters walk away, and the
truncated support starts excluding library members at the far rung — both the behaviour
the ladder exists to quantify, at a scale too small to quantify it.

**The consequence is a design point, not a defect:** the library has to be built at the
largest population size of the sweep, so that its *detected* subset is large enough for
the criterion to bite. That is what `experiments/sp1-sweep.toml` does.

### Calibration at this scale means nothing

Four calibration evaluations. The coverage figures the smoke reports are a test that the
plumbing runs end to end and produces ranks; they are not calibration evidence and must
not be quoted as any.
