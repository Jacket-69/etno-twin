# Evidence — SP-1 step 2

The collated measurements ADR-0001 cites, versioned so the citation survives. Experiment
output trees are regenerable and are not in version control; these summaries are, because
an ADR that points at a gitignored directory points at nothing.

Each file is the `measurements.json` a run of the pipeline produced, copied verbatim:

```bash
uv run python scripts/publish_evidence.py runs/<experiment>
```

## What is here and what is not

**Here:** the collated summary per experiment — the cost model with both estimates of
fixed cost, detection efficiency, bytes at every boundary, the reweighted-library ladder
with its criterion evaluated against each declared catalogue size, training cost and
calibration, and the fingerprints of the external data every run consumed.

**Not here:** detection catalogues, run logs, per-run manifests, trained networks. Those
stay in the run tree. The summary carries their counts and the path they were produced
under; putting hundreds of megabytes into a repository a preprint will cite would buy
nothing a reader can use.

The summaries aggregate rather than enumerate. An experiment of ten thousand draws has ten
thousand recorded seeds; the summary states that every one was recovered, how many were
distinct, and quotes a handful. The individual values are in the per-run manifests, which
is where a reader chasing one run should look.

## Reading a file

| Field | What it answers |
|---|---|
| `boundaries.campaign.cost_model.fit` | Fixed and marginal cost, from the ladder of population sizes |
| `boundaries.campaign.cost_model.fixed_cost_from_log` | The same fixed cost, from the phase profile of each run |
| `boundaries.campaign.cost_model.fixed_cost_agreement` | Whether the two independent estimates agree |
| `boundaries.campaign.peak_rss_bytes` | Worker memory — what decides how many fit on a machine |
| `boundaries.campaign.detection_efficiency` | Objects detected per draw, the dominant unknown of the cost estimate |
| `boundaries.library[].rungs[]` | Effective sample size, rejected fraction and criterion per rung |
| `boundaries.dataset[].raw_to_summary_ratio` | The price of storing observations raw rather than summarised |
| `boundaries.training[].pairs_binding` | **Which simulator produced the pairs a training figure was measured on** |

That last row matters. The training-budget frontier is measured against the fake binding
by decision, because wall-clock of training, bytes of the network and calibration do not
depend on which simulator wrote the pairs — and the manifest says so in words, so no
reader has to infer it.

The method behind every number is in
[the measurement protocol](../../spike-sp1-measurement-protocol.md).
