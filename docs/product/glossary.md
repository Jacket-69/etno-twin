# Glossary

Domain vocabulary. Read this before the rest of the documentation: the advisor and the
thesis committee come from computer science, and most of these terms are load-bearing
in the code.

| Term | Definition |
|---|---|
| **TNO** | Trans-Neptunian Object. A minor body orbiting the Sun beyond Neptune. |
| **ETNO** | Extreme TNO. A TNO on a large, distant orbit — the population this project infers over. Short observational arcs and severe selection effects make it the hardest and most interesting case. |
| **Sednoid** | An ETNO whose perihelion is far enough out that Neptune cannot have shaped its orbit. The archetype is Sedna. Relevant because these objects drive the clustering debate. |
| **Semi-major axis (a)** | Half the long axis of an orbital ellipse; sets the orbital size and period. For single-opposition ETNOs its uncertainty can exceed 100 au. |
| **Opposition** | The period when an object is observable near the anti-solar direction. A *single-opposition* orbit comes from one such window and is degenerate. |
| **Observational arc** | The time span between the first and last astrometric observation of an object. Short arc, poorly constrained orbit. |
| **Tracklet** | A set of detections of the same moving object within one night, used to link observations across nights. |
| **Astrometry** | Position measurements of an object on the sky at given times. The raw input from which orbits are fitted. |
| **Selection function** | The probability that a survey detects and tracks an object with given properties. It is what makes an observed catalogue unrepresentative of the real population. |
| **Survey characterisation** | The published description of a survey's pointings, depth and follow-up criteria, from which its selection function is computed. |
| **Survey simulator** | Software that takes a synthetic population and returns what a given survey would have detected. Here: OSSOS Survey Simulator for classical surveys, sorcha for Rubin. |
| **Debiasing** | Correcting an observed catalogue for its selection function to reason about the underlying population. |
| **Forward model** | The generative direction: hypothetical population → selection function → simulated observed catalogue. This is the structure that simulation-based inference requires. |
| **SBI** | Simulation-Based Inference. Bayesian inference when the likelihood is intractable but the forward model can be simulated. |
| **NPE** | Neural Posterior Estimation. The SBI variant used here: a neural network learns the posterior directly from simulated pairs. |
| **Posterior calibration** | Whether the inferred uncertainty is honest — e.g. whether 90% credible intervals contain the truth 90% of the time on synthetic data with known truth. |
| **Statistical power** | The ability to distinguish between competing hypotheses. The primary metric of this project's contribution. |
| **Temporal cut** | The simulated "as of" date of a catalogue snapshot. Enforcing it prevents using information that did not exist at that date. See [provenance](../data/provenance.md). |
| **Temporal leakage** | Using information from after the temporal cut — e.g. a classification assigned later. It silently invalidates results and is the failure mode this project guards hardest against. |
| **MPCORB** | The Minor Planet Center's orbital catalogue; the public source of solved orbits. |
| **OpSim** | Rubin's Operations Simulator, which produces the survey cadence that sorcha consumes. |

## Terms to avoid

- **"Digital twin"** — the client's term, kept in the thesis title and in conversation
  with him because it is his framing, but it does not exist as a term of art in this
  field. In technical documents, name the layers: live catalogue, dynamical
  propagation, bias simulator, inference.
- **"Detecting Planet Nine"** — the project infers population structure and quantifies
  power; it does not set out to confirm or refute a specific body.
