# Formal novelty verification

> Specific objective 1 of the thesis, and a Phase 1 gate. What is versioned here is the
> **protocol** — question, criteria, queries, sources, verification level — not just the
> verdict. A verdict nobody can re-run is an opinion.
>
> Last run: 2026-08-25. Supersedes the informal search of 2026-08-17.

## The question

Does a public pipeline already chain a **survey simulator** (a forward model of
observational selection: cadence, noise, detection limits, footprint) to
**simulation-based inference** in order to infer **population-level parameters**?

Two scopes, answered separately, because they support different claims:

- **Own domain** — trans-Neptunian objects and minor bodies (`sorcha`, OSSOS Survey
  Simulator, CFEPS, DES survey simulator).
- **Analogous domains** — any astronomical field where the same pattern is assembled
  (supernova cosmology, gravitational waves, pulsar and magnetar population synthesis,
  exoplanet occurrence rates).

## Inclusion and exclusion criteria

A work is **included** when it satisfies all three:

1. Selection is modelled by a **forward simulator**, not by an analytic or empirical
   selection function applied after the fact.
2. Inference is **amortised and simulation-based** — NPE, NRE, normalising flows, or
   ABC — over the simulator's output.
3. The target of inference is a **population-level parameter** (a distribution, a rate,
   a power-law index), not a per-object property.

**Excluded:** classical likelihood or KS-style model comparison against survey-simulator
output (this is the state of the art in the TNO domain, and it is the baseline this
thesis must reproduce, not a competitor); post-hoc reweighting of an already-trained
network's samples; per-object parameter estimation.

## Verification rule

Every claim in the results table is graded. **Verified** means the paper body or the
repository README was read directly at the cited section. **Abstract only** means just
the abstract was read; nothing about the mechanism is asserted. Search-engine summaries
are never a source — this rule exists because a summary produced a false claim about the
OSSOS Survey Simulator on 2026-08-24 that cost a correction.

## Results

| Work | What it does | Simulator | Inference | Ref. | Level |
|---|---|---|---|---|---|
| **Stjörnumál** (Popovic et al., 2026) | Infers intrinsic and extrinsic parameters of the SN Ia population; tested against DES-5yr over seven dust/progenitor models; public code | SNANA, with survey-specific detection criteria | NPE + NRE | arXiv:2607.28725 | **Verified** — §4, §4.1 |
| **FlowSN** (Boyd, Mandel, Grayling et al., 2026) | Normalising flow learns the non-analytic selected-SN likelihood from forward simulations, then HMC for cosmological parameters | SNANA, LSST-like | Custom normalising flow | arXiv:2603.11165 | **Verified** — title, abstract, method |
| **Dust2Dust** (Popovic, Brout, Kessler & Scolnic, 2021) | Forward-models dust and intrinsic colour distributions of SNe Ia; origin of the reweighted-bank technique | SNANA | Classical MCMC (**not** SBI) | arXiv:2112.04456 | **Verified** — body |
| **OSSOS X** (Bannister et al., 2018) | Canonical reference of the own domain: survey simulator plus statistical comparison of dynamical models against real detections | OSSOS SS | Classical comparison — **no SBI** | arXiv:1802.00460 | Prior work of SP-1 (Q2) |
| GW population inference with NPE | Normalising flow infers population hyperparameters of LVK events, folding in selection effects | Empirical LVK selection function, not an imaging survey simulator | NPE | arXiv:2311.12093 | Abstract only |
| Isolated-pulsar SBI | Large synthetic P-Ṗ library over five magnetorotational parameters trains an NPE | Population synthesis plus a detection criterion | NPE | arXiv:2312.14848 | Abstract only |
| Galactic magnetars | Reproduces the observed magnetar population with SBI | Not specified in abstract | SBI, method unspecified | arXiv:2503.11875 | Abstract only |
| LISA galactic binaries | Normalising flow over compressed frequency series of the double-white-dwarf population | LISA response simulator | NPE | arXiv:2506.22543 | Abstract only |
| `sorcha` or OSSOS SS combined with `sbi`, `swyft`, `lampe`, `BayesFlow` | — | — | — | — | **Absence confirmed** over the queries below |

## Verdict

**In the trans-Neptunian domain: no such pipeline exists.** No work or public repository
chains a minor-body survey simulator to amortised inference. The canonical reference of
the domain uses the survey simulator with classical statistical comparison.

**In analogous domains: the pattern is established, with public code.** Supernova
cosmology in particular has two independent 2026 implementations.

**Therefore the defensible claim is "first application to the trans-Neptunian domain",
never "first time this is done".** The stronger wording is dismantled by a single paper,
and stating the narrow claim is what makes the related-work section credible.

**Nearest neighbour: Stjörnumál.** It is the only work satisfying both criteria at once —
explicit observational selection through a survey simulator, and NPE. It differs in
domain (SNe Ia, not minor bodies), in inference target (intrinsic/extrinsic population
parameters, not a distribution over orbital elements and H), and in that it never
propagates orbital uncertainty. FlowSN is the second citation: same simulator family,
LSST-like cadence, but its target is cosmological parameters.

## The reweighted-library idea, and the gap that remains

The cost-collapsing idea under consideration — pay the survey simulator **once** over a
large library and compose each dataset by reweighting that library by θ — **already has a
precedent inside an NPE pipeline**, which was not known when the idea was raised.

Dust2Dust builds a `simulation bank` once with SNANA, with the survey's selection effects
already inside, and importance-samples from it to produce the simulation for the desired
parameters; Stjörnumál inherits that machinery and trains its NPE/NRE on the result.
Genealogy: the technique is born in a classical MCMC fit (2021) and acquires a neural
inference layer (2026).

**Neither link of that genealogy analyses the bias.** Verified by direct search of both
bodies:

- No effective sample size, and no quantitative validity criterion for the reweighting.
- Out-of-range handling is binary — the proposal is flagged and assigned −∞ likelihood
  when `p/p_ref > 1`, reported at a frequency of order 10⁻⁴ — with no analysis of the
  intermediate regime, where parameters are far from the reference but not discarded.
  That regime is where bias accumulates silently.
- Validation is empirical (recovery fits against data-sized simulations), not theoretical.

A quantitative criterion does exist, in a different community and outside the NPE frame:
**`N_eff > 4·N_obs`** (Farr 2019, *Accuracy Requirements for Empirically-Measured
Selection Functions*, arXiv:1904.10879, stated after equation 12 — **verified in the
body**). The failure mode is documented there too: when the target population departs
from the reference set, reweighting estimates drop unphysically to zero
(arXiv:2408.16828 — reported by the survey, not independently verified here).

**The gap, stated narrowly enough to defend:** carrying a Farr-style quantitative validity
criterion into library reweighting **inside an NPE training loop** — measuring where it
breaks rather than trapping the failure mechanically. Neither line of work does this today.

Two consequences already acted on:

- **Step 2 of the tracer bullet must measure `N_eff`**, not only wall-clock and bytes.
  Without it the viability of the reweighted library is an opinion; with it, it is
  measured against a published criterion.
- **A mitigation is inherited rather than invented.** When the bank fails to cover the
  proposed region, Dust2Dust regenerates the reference simulation with new centres and
  widths. Out-of-support reweighting is therefore not a dead end: the simulator is paid
  again, boundedly.

## Queries

Run against arXiv, ADS and general web search, 2026-08-25. Recorded literally so the
search can be repeated or extended.

```
"simulation-based inference" "survey simulator" trans-Neptunian OR TNO OR "Kuiper belt"
"neural posterior estimation" survey simulator selection function population
OSSOS survey simulator ABC Bayesian population inference debiasing
sorcha "simulation-based inference" OR "neural posterior" Rubin LSST
"importance reweighting" "simulation-based inference"
"simulation-based inference" reweighting selection function survey astronomy
FlowSN neural simulation-based inference realistic selection effects supernova cosmology
"simulation-based inference" Type Ia supernova population selection effects survey simulator
"simulation reuse" OR "reuse simulations" "simulation-based inference" amortized
"weighted forward model" OR "weighted forward modelling" simulation-based inference reweighting library
"selection function" reweighting "neural posterior estimation" bias not i.i.d.
exoplanet occurrence rate "simulation-based inference" Kepler injection recovery neural posterior
"stellar stream" OR "asteroid belt" "simulation-based inference" OR "neural posterior estimation" selection function survey
OSSOS "approximate Bayesian computation" trans-Neptunian population orbital elements
Kuiper belt "neural posterior estimation" OR "amortized inference" population orbital elements debiasing
"recycling simulations" OR "reusing simulations" reweighting neural posterior estimation likelihood-free
"survey selection function" reweighting library synthetic population "importance sampling" TNO OR asteroid OR exoplanet debiasing
"simulation library" reweight parameter inference "detection probability" astronomy population synthesis cost
gravitational wave population inference selection effects reweighting injection campaign effective number of samples
Farr 2019 "accuracy requirements" selection function Monte Carlo estimate gravitational wave population
"neural posterior estimation" gravitational wave population "selection function" reweighted injections fixed set
asteroid main belt population "simulation-based inference" OR "neural posterior estimation" survey debiasing
"sbi" python package documentation "reuse simulations" OR "importance sampling" amortized proposal mismatch
```

## Open threads

- Four analogous works were read at abstract level only; whether they reuse or reweight a
  fixed library, or resimulate per θ, is unverified.
- The size of Dust2Dust's parent bank is not stated in the paper — only the per-step
  downsizing to 5,000 supernovae.
- The public repository URL for Dust2Dust is not printed in the paper body, which only
  announces that the code is released. Verify before citing it.
- Exoplanet completeness maps (Kepler/TESS with ABC) were surveyed in one pass only.
- Discarded as a precedent: arXiv:2504.07197 reweights samples drawn from an
  already-trained variational flow — a post-hoc correction, not reweighted training data.

## How to repeat this

Re-run the query block above, apply the inclusion criteria, and grade every new hit by
verification level before it enters the table. A hit that changes the verdict changes the
thesis claim, so it is recorded here first and in the vault log second.
