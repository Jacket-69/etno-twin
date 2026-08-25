# Requirements

Numbered functional (FR) and non-functional (NFR) requirements. Derived from the thesis
proposal §5–§13; the specific objectives there are the source, this document is the
engineering restatement.

## Functional

| ID | Requirement | Source | Status |
|---|---|---|---|
| FR-01 | Build a unified ETNO catalogue with orbital uncertainties from sources with differing schemas, identities and reference frames | Proposal, objective 2 | TODO — detail after SP-1 |
| FR-02 | Version every source snapshot and enforce a declared temporal cut | Proposal, objective 2 | TODO |
| FR-03 | Expose a common interface over heterogeneous survey simulators, including the Fortran reference implementation | Proposal, objective 3 | TODO — shape depends on ADR-0001 |
| FR-04 | Orchestrate simulation campaigns with parallelism, checkpoints and fault tolerance | Proposal, objective 3 | TODO |
| FR-05 | Implement the classical baseline: per-survey selection function plus consistency test against a uniform population | Proposal, objective 4 | TODO |
| FR-06 | Generate synthetic populations under competing dynamical hypotheses | Proposal, objective 5 | TODO |
| FR-07 | Infer population parameters via neural posterior estimation over the forward model, with calibration diagnostics | Proposal, objective 6 | TODO |
| FR-08 | Report statistical power against the baseline and project detections needed to discriminate hypotheses | Proposal, objective 7 | TODO |

## Non-functional

| ID | Requirement | Verification |
|---|---|---|
| NFR-01 | Reproduce any published experiment with a single documented command from a clean clone | Milestone 8 gate |
| NFR-02 | Run identically on a personal workstation with reduced samples and on larger compute | Same stages, same command, different configuration |
| NFR-03 | The core is exercisable without a Fortran toolchain present | CI runs the full chain against fake simulators |
| NFR-04 | Test coverage over data transformation and external simulator integration | See testing strategy |
| NFR-05 | No result may depend on information postdating its declared temporal cut | Snapshot manifests plus rebuild determinism test |

TODO — acceptance criteria in Given-When-Then form, per requirement, once SP-1 closes.
