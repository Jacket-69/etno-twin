# Evidence — ADR-0002, resumption after interruption

The measurement behind ADR-0002's resumption table, and the script that produces it.

ADR-0001 cited a resumption that happened **by accident**: an external `SIGTERM` killed the
training-budget run at 96 % of 20,416 jobs, and it resumed from its artifacts without
recomputing completed work. That was a fortunate observation, not evidence — one point of
progress, one kill signal, no control. This turns it into a protocol.

## The question

Does resumption depend on *how far* a run got before it died?

The honest prior was that nobody knew. A resumption observed at 96 % is compatible with two
very different mechanisms: one that decides per job, and one that happens to work when
almost everything is already on disk.

## Method

`resumption-probe.sh`, in this directory. A 46-job smoke DAG against the fake binding —
no Fortran, no network, no ephemeris cache — so the probe runs in minutes and in CI-like
conditions.

1. **Baseline.** A run that is never interrupted. Every artifact hashed.
2. **Determinism control.** A second clean run, compared to the first. Without this step
   the rest is unreadable: a resumed run that differs from the baseline tells you nothing
   until you know whether two *clean* runs differ.
3. **Kills.** At each target percentage, in two regimes:
   - `SIGTERM` to the snakemake process — the orderly case, what a `kill` or a Ctrl-C sends.
   - `SIGKILL` to the whole process group — the hard case: power loss, OOM killer, `kill -9`.

   Then resume **without unlocking first**, because whether that works is itself the finding.

## Results

Measured 2026-08-27 on the development workstation.

| Kill regime | Died at | Resumes unaided | Jobs re-executed |
|---|---|---|---|
| `SIGTERM` to the process | 35 % | **yes** | 26 / 46 |
| `SIGKILL` to the group | 15 % | no — needs `--unlock` | 38 / 46 |
| `SIGKILL` to the group | 30 % | no — needs `--unlock` | 30 / 46 |
| `SIGKILL` to the group | 50 % | no — needs `--unlock` | 23 / 46 |
| `SIGKILL` to the group | 96 % | no — needs `--unlock` | 2 / 46 |

**In all four hard-kill cases, the 58 deterministic artifacts came back byte-identical to
the baseline.**

## What it means

**Resumption does not look at the percentage.** It decides job by job, from the presence of
output files and the metadata of incomplete ones. Re-executed work falls monotonically with
progress — 38, 30, 23, 2 — with no threshold or special region anywhere. This is a
structural property of the artifact discipline ADR-0001 chose, not a behaviour that happens
to hold near the end of a run. The 96 % case was not lucky; it was the cheapest point on a
continuum.

**A hard kill leaves a stale lock.** Resumption refuses to start:

```
LockException: Directory cannot be locked. […] the remaining lock was likely caused by a
kill signal or a power loss. It can be removed with the --unlock argument.
```

This is exactly why the 2026-08-25 run resumed unaided — it received `SIGTERM`, and the
orchestrator released its lock on the way out. A power loss will not be so polite. The
remedy costs one command and recomputes nothing, but it belongs in the milestone-6 runbook.

## The determinism control, and why the numbers above exclude most artifacts

Two clean runs of this pipeline are **not** byte-identical to each other. This is by design
and worth stating plainly, because it looks like a defect until you know why.

`simulators/base.py` documents it: neither binding takes its seed from the caller. Both draw
from the operating system and record what they drew, because sorcha's own authors warn that
reusing seeds between simulations produces hard-to-detect correlations, and that a fixed
seed is for testing and "should never be used for science results". The simulator's
stochasticity is part of the forward model. What the pipeline owes is a record, not a pin —
and the seed is recovered from the run log by `parse_seeds`.

So the pipeline is **deterministic where it was designed to be**:

| Artifact | Behaviour | Why |
|---|---|---|
| `orbits.csv`, `physical-parameters.csv`, `theta.json`, `draws.txt` | identical across runs | seeds derived from `master_seed` |
| `detections.csv` and everything downstream | differs across runs | the simulator seeds from the OS, by design |

The probe therefore compares the deterministic set for identity, and reports the stochastic
drift separately — a resumed run must not differ from the baseline by more than two clean
runs differ from each other.

**This wording matters beyond the probe.** Wherever the thesis commits to one-command
reproduction, it means the same invocation and complete provenance, and *statistical*
reproducibility. It does not mean equal hashes, and somebody will eventually run the
pipeline twice and check.

## Re-running it

```bash
docs/architecture/evidence/adr-0002-resumption/resumption-probe.sh
```

It copies the experiment configuration to its own output tree, so it never competes with a
real run, and cleans up after itself. `TARGETS="10 50 90"` and `CORES=8` override the
defaults; pass a different experiment file as the first argument.
