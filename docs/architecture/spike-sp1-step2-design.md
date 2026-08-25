# SP-1 step 2 — design of the tracer bullet

> The measurement that closes [ADR-0001](decisions/0001-architecture-style.md), and at
> the same time the walking skeleton of milestone 2. Written before the code so nobody
> has to re-derive it. Findings from step 1 are in
> [the spike note](spike-sp1-integration-surface.md).
>
> **Two numbers lead, because they decide budgets:** the fixed/marginal cost split, and
> whether a reweighted library is viable. Everything else in the spike is already in a
> position to close the ADR once these land.

## What gets measured, boundary by boundary

Every boundary writes and validates a manifest. The manifest code is the deliverable
under test here, not decoration.

**1 · Population → simulator inputs.** Wall-clock of generation, bytes of orbits and
parameters, N.

**2 · Simulator run.** The sweep **N = 10 / 100 / 1000** for the fixed/marginal split —
the measurement step 1's extrapolation lacked. Also peak RSS, output bytes,
bytes/detection, and **detection efficiency** (fraction of objects detected, detections
per object), which feeds the dominant unknown of objects-per-draw. Recover the seed by
parsing the run log, which doubles as a test of the canary regex.

**3 · Detections → (θ, x) pairs.** Wall-clock of composition, and bytes of x **both raw
and summarised** — so "store x at the rawest affordable level" gets priced instead of
decided blind. Note the float32 dtypes `sbi` expects.

**4 · Training and calibration.** Wall-clock at 10³ versus 10⁴ simulations, bytes of the
persisted network, SBC ranks and coverage. **And the free experiment that must not be
skipped: run those two trainings under different master seeds and report the delta in
SBC and posterior.** Two trainings were happening anyway; with two seeds, the
"statistical replication" claim stops being a promise and becomes a measured number,
disarming the "archiving is not reproducing" objection before it is raised.

**5 · Reweighted-library viability.** Added 2026-08-25, after
[the novelty verification](../product/novelty-verification.md) found the idea already has
a working precedent inside an NPE pipeline — and found that neither link of that
genealogy measures when it stops being valid.

Build one library at the largest N of the sweep, then compose datasets for θ values at
increasing distance from the library's reference distribution and record, for each one:
the **effective sample size** `N_eff`, the fraction of proposals rejected as out of
range, and the wall-clock saved against simulating that θ from scratch. The published
criterion to report against is **`N_eff > 4·N_obs`** (Farr 2019, arXiv:1904.10879, after
equation 12), imported from hierarchical inference and never yet applied to this use.

This is the cheapest measurement in the whole step and the one with the largest
consequence: it prices the difference between one simulator campaign and thousands, and
it is where the thesis has something of its own to say. If `N_eff` collapses before θ
reaches the edge of the prior, the campaign stage stays monolithic; if it holds, the
stage splits into library-build and composition with an artifact boundary between them.

Measurements are written to a `measurements.json` artifact, never to prints: they are
the evidence the ADR will cite.

## Shape — skeleton, not scratchpad

- Each stage is a module under `src/` exposing a pure
  `run(inputs, outdir, config) -> artifact paths`, plus its own entry point.
- **Stages do not import each other.** They meet only through files with a declared
  schema, with the import-linter contract the ADR anticipates active from day one.
- One experiment configuration file is the root of the manifest — it is what "one
  command" points at.
- Chained by the candidate orchestrator: a Snakefile. Q6's half-day pays for itself
  here.
- **Double binding.** CI runs the same DAG against the fake simulator with tiny
  committed fixtures — no network, no Fortran, no 780 MB. The workstation runs the
  sorcha binding. Same stage code, different port: that *is* the milestone 2 gate.

## The mistakes of writing it in a hurry, ordered by damage

1. **Passing DataFrames end to end in one process.** Validates nothing about the
   architecture. Every seam must cross a file-and-process boundary or the experiment
   does not discriminate between the options.
2. **Letting the fake and sorcha diverge.** Schema first, contract test for both against
   it.
3. **Writing it as a notebook "to be refactored later".** It never gets refactored.
4. **Measuring only N = 10.** Leaves fixed cost confounded — the exact defect of the
   current extrapolation.
5. **Using the demo files without hashing them into the manifest** like any other
   snapshot.
6. **Treating SBC as a decorative smoke test.** It is the measurement that anchors the
   NPE simulation budget.
7. **Putting the seed in the config instead of recording it per run.** Recreates the
   correlation trap the simulator's own source warns about.

## Cluster notes for when this scales

- **Stages stay scheduler-agnostic** — pure file→file plus manifest. Only the
  orchestration profile knows about the site. With that, "there is no Slurm" is a
  profile problem, not a change to stage code.
- Snakemake runs perfectly well as a **local executor per node** over an artifact store
  on shared storage, which covers milestone 6's scaling measurement with no scheduler at
  all. DVC drops further down the list: it has no cluster execution, so it would only be
  data versioning next to some other runner.
- **Honesty for the thesis:** core scaling can be measured properly; node scaling with
  two nodes is two points. Say that, rather than selling "cluster-ready".
- **SQLite on network storage is a documented locking hazard** *(general knowledge, not
  tested here)*. Sorcha's collation tool writes SQLite — collate on local scratch and
  copy the finished artifact, or collate to parquet.
- **Compute nodes may have no egress:** pre-stage the 780 MB ephemeris cache to shared
  storage and point the simulator's cache at it. The manifest's ephemeris-version field
  is what keeps both machines honest.
