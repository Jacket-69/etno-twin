---
adr: 0002
title: Which orchestrator chains the stages
status: accepted
date: 2026-08-27
decided: 2026-08-27
deciders: Benjamín López Huidobro
tags: [adr, arquitectura, orquestacion]
---

# ADR 0002 — Which orchestrator chains the stages

## Context

ADR-0001 settled the architectural style — artifacts at stage boundaries, memory within a
stage — and with it a scoping constraint: **the orchestrator is bought, not built**. The
engineering contribution of this thesis is the domain system, not workflow middleware.

It deliberately left *which* orchestrator open, to be decided "once the tracer bullet
reports artifact shapes and sizes, and once the target cluster's scheduler situation is
known". Both inputs have arrived, and they did not land the way the question expected.

**This is not a choice from a blank slate.** Snakemake has run the full tracer bullet:
the SP-1 sweep, the training-budget experiment and the resumption probe below — tens of
thousands of jobs, on the workstation and in CI. The question is whether to confirm a
purchase already made and exercised, or to reverse it. That places the burden of proof on
reversal: something has to be failing, not merely be theoretically tidier elsewhere.

**Three things moved the weights since the question was framed as Q6 of SP-1.**

1. **The Slurm argument collapsed.** Q6 leaned on Snakemake shipping a Slurm executor.
   GÜINA has no declared scheduler — and the source of that claim is an institutional
   presentation, not an inspection, so it is a *standing assumption, not a verified
   fact*. Either way the cluster sits outside the critical path by decision of
   2026-08-24: it is a measurement bench, not a dependency. The argument is dead as a
   requirement.
2. **The campaign stopped being enormous.** With fixed cost measured at 28.25 s per
   simulator run and the ~335 CPU-day extrapolation withdrawn, a full campaign is on the
   order of days on one machine. The DAG is modest — 46 jobs for the smoke experiment.
   `make` stopped being absurd *a priori*.
3. **Resumption stopped being a promise.** It is no longer a feature to compare across
   brochures: it is measured behaviour of the tool in use, in two kill regimes and at four
   points of progress. See *Evidence*.

## Decision

**Snakemake**, confirmed — with its one known failure mode documented here rather than
discovered later.

Three properties decide it, and all three are anchored in what the repository already
does, not in feature lists.

**1 · A per-rule resource semaphore, which is what keeps measurements valid.** The
campaign rule claims `bench_slot=1`, so simulator invocations serialise *while the rest of
the DAG keeps running in parallel*. This is not cosmetic: two simulator processes sharing
a machine measure contention, not cost, and every number in ADR-0001 depends on it.
`make` has no equivalent — `-j N` is a global parallelism cap, not a per-rule quota — so
under `make` this would have to be built, which is precisely what ADR-0001 said would not
be done.

**2 · The run matrix is already expressed as wildcards.** `sweep-n{n}-rep{rep}` and
`b{budget}-s{seed}` expand from the experiment file. Under `make` the expansion becomes
generated target lists maintained by hand.

**3 · One description of an experiment.** The Snakefile reads the same TOML with the same
parser the stages use. There is one description of an experiment, not one for the pipeline
and a second for the workflow engine.

## Alternatives considered

### Option A — Snakemake (chosen)

- Pros: the three properties above; a Python-native rule language over a codebase already
  in Python; the standard of practice in reproducible research, which matters for a thesis
  a committee will read; **if AstroData ever installs Slurm on GÜINA, it becomes an
  executor plugin rather than a redesign** — the option stays open at no cost.
- Cons: a real dependency with its own learning curve, and gotchas already paid for (the
  target must precede the flags; a hard kill leaves a stale lock — see *Consequences*).

### Option B — GNU make

- Pros: zero new dependencies, present on every machine, and legible to any reader without
  explanation — a genuine argument for a document a committee evaluates.
- Cons: no per-rule resource quota, so the serialisation the measurements depend on would
  have to be built by hand; the run matrix becomes hand-maintained target lists; no
  structured provenance of which rules ran. The first of these is disqualifying on its own,
  because it converts a bought capability into a built one.

### Option C — DVC

- Pros: data versioning and artifact caching as first-class concerns, which sounds like a
  direct fit for a pipeline built on artifacts.
- Cons: **its core value duplicates a subsystem this project built deliberately.**
  Snapshot fingerprinting with a temporal cut lives in `stages/snapshot.py` and the
  per-boundary manifests, and it is *thesis content* — leakage from a live catalogue
  invalidates results silently, so provenance is not infrastructure to delegate here.
  Adopting DVC would mean two provenance systems competing for the same responsibility.

### Option D — Nextflow

Not seriously in contention, and worth recording why so the omission is not read as an
oversight. It is the other standard of the field, but its rule language is Groovy against
a codebase that is Python end to end, and its strengths — container-per-process,
multi-cloud execution — address problems this project does not have. The cost of the
mismatch is paid every time a stage is touched.

> **On what the wider field does, honestly.** Snakemake and Nextflow are the two de facto
> standards of reproducible research workflows, with the evidence base concentrated in
> bioinformatics. **Rubin itself uses neither** — its production stack is Pegasus/HTCondor
> and its own BPS. That is observatory production with dedicated infrastructure teams, not
> the scale of a single-author thesis, and adopting it here would import a problem the
> project does not have. The comparable community is reproducible research, where
> Snakemake is the conservative choice.

## Evidence

### Resumption, measured in two kill regimes

ADR-0001 cited a resumption that happened *by accident*: an external `SIGTERM` killed the
training-budget run at 96 % of 20,416 jobs and it resumed without recomputing. One
observation at one point of progress is not evidence that resumption holds generally, so
it was turned into a protocol. See
[`evidence/adr-0002-resumption/`](../evidence/adr-0002-resumption/) for the script and the
full method.

46-job smoke DAG, fake binding. Each run killed at a target percentage, then resumed and
compared hash-for-hash against a run that was never interrupted.

| Kill regime | Died at | Resumes unaided | Jobs re-executed |
|---|---|---|---|
| `SIGTERM` to the snakemake process | 35 % | **yes** | 26 / 46 |
| `SIGKILL` to the process group | 15 % | no — needs `--unlock` | 38 / 46 |
| `SIGKILL` to the process group | 30 % | no — needs `--unlock` | 30 / 46 |
| `SIGKILL` to the process group | 50 % | no — needs `--unlock` | 23 / 46 |
| `SIGKILL` to the process group | 96 % | no — needs `--unlock` | 2 / 46 |

**The mechanism does not look at the percentage.** It decides job by job, from the presence
of output files and the metadata of incomplete ones. Re-executed work therefore falls
monotonically with progress — 38, 30, 23, 2 — with no special point anywhere along the
range. Resumption is a structural property of the artifact discipline, not a behaviour that
happens to hold near the end of a run.

**In all four hard-kill cases the 58 deterministic artifacts were byte-identical to the
baseline.** Nothing already computed was corrupted or silently recomputed to a different
value.

### The failure mode this found

A hard kill leaves a **stale lock**, and resumption refuses to start:

```
LockException: Directory cannot be locked. […] the remaining lock was likely caused by a
kill signal or a power loss. It can be removed with the --unlock argument.
```

This is why the 2026-08-25 run resumed unaided: it received `SIGTERM`, which let the
orchestrator shut down in order and release the lock. A power loss, an OOM kill or a
`kill -9` does not. The remedy costs one command and recomputes nothing — but it belongs in
the milestone-6 runbook, not in a footnote.

### What "reproducible" means here, stated precisely

The determinism control — two clean, uninterrupted runs compared to each other — found that
**the pipeline is not bit-identical to itself**, and this is by design rather than a defect.
`simulators/base.py` records why: neither binding takes its seed from the caller, because
sorcha's own authors warn that a fixed seed "should never be used for science results". The
simulator's stochasticity is part of the forward model; what the pipeline owes is a record,
not a pin, and the seed drawn is recovered from the run log.

The pipeline is therefore **deterministic where it was designed to be** — `population`,
whose seeds derive from `master_seed`, which is why 58 artifacts match hash for hash — and
**stochastic by design where it mirrors the real simulator** (`campaign`, and everything
downstream of it).

This has to be stated carefully wherever the thesis commits to reproducibility. *One
command reproduces an experiment* means the same invocation and complete provenance, and
**statistical** reproducibility — not equal hashes. Somebody will run the pipeline twice
and compare.

## Consequences

**1 · The milestone-6 runbook gains a step.** Resuming after a hard kill is
`snakemake --unlock` followed by the normal invocation with `--rerun-incomplete`. Worth
stating in the operations documentation before a long campaign, not after one.

**2 · The claim the thesis makes about resumption changes shape.** It is no longer "a run
survived an interruption" but "resumption is decided per job, measured at four points of
progress across two kill regimes, with the one failure mode identified and its remedy
costing one command". That is a claim a committee can check.

**3 · The reproducibility metric must be worded as statistical, not bitwise**, in the
proposal and the thesis. See the evidence section above.

**4 · The decision stays cheap to reverse, and this is now measured rather than asserted.**
The orchestrator lives outside the import graph — four import-linter contracts enforce it in
CI, and no stage knows Snakemake exists. Producing this ADR meant running the whole pipeline
five times from outside its normal use, killing it by hand, without touching a line of
`src/`. Replacing the orchestrator is rewriting one file of roughly 250 lines.

## Compliance / verification

- **CI runs the full DAG against the fake binding** on every push — the orchestrator is
  exercised, not just declared.
- **The four import-linter contracts** keep the orchestrator outside the import graph,
  which is what preserves the reversibility claimed above. A rule that imported a stage
  would fail CI.
- **The resumption probe is versioned** in `docs/architecture/evidence/adr-0002-resumption/`
  and can be re-run against any experiment configuration.

## References

- ADR-0001 — [Architectural style of the pipeline](0001-architecture-style.md), which
  scoped this decision and left it open
- [Snakemake CLI reference](https://snakemake.readthedocs.io/en/stable/executing/cli.html)
  — `--rerun-incomplete`, `--keep-incomplete`, `--unlock`
- [How Do Users Design Scientific Workflows? The Case of Snakemake and Nextflow](https://dl.acm.org/doi/10.1145/3676288.3676290)
  (SSDBM '24)
- [LSST Science Pipelines](https://pipelines.lsst.io/) and
  [Rubin data management pipelines](https://www.lsst.org/about/dm/pipelines) — the
  observatory's own orchestration, for contrast
- Decision of 2026-08-24 on GÜINA as a measurement bench rather than a dependency —
  `~/Documentos/CELAENO/Proyectos/Gemelo Digital Transneptuniano/decisiones.md`
