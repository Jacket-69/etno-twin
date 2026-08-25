# Applied methodology — etno-twin

- **Size:** M · Standard
- **Type:** Library + CLI
- **Process:** Scrumban
- **Style:** *undecided* — see [ADR-0001](architecture/decisions/0001-architecture-style.md),
  status `proposed`, pending the reconnaissance spike (milestone 1 of the roadmap)
- **Canonical source:** vault › `Conocimiento/Procesos/Metodología de Proyectos`
  (`~/Documentos/CELAENO/Conocimiento/Procesos/Metodología de Proyectos/_README.md`)

Decided on 2026-08-24 at bootstrap time.

## Why these choices

**Size M.** Twelve months, one developer, no real users, no sensitive data, no
availability commitment — none of the triggers for size L are present. Size S was
rejected for a specific reason: the thesis proposal (§13) commits to test coverage
over data transformation and external simulator integration, and to reproducing any
experiment with a single command, as *evaluable metrics*. Those commitments require
the standard `docs/` tree; without it the claim "the system is the object of the
thesis" has nothing to point at.

**Type Library + CLI.** The core deliverable is an installable Python package that
orchestrates the chain; the single-command reproducibility metric requires a declared,
tested command-line entry point rather than loose scripts.

**Process Scrumban.** One developer, phases of one to three months with exit gates.
Flow board with limited WIP; the formal cadence is the fortnightly meeting with the
thesis advisor (agenda before, minutes after). Milestones are the six phases of the
roadmap, not invented sprints.

## Deviations from the default

- **`docs/data/provenance.md` added to the standard subset.** Not part of the size-M
  tree. It exists because the catalogues this project consumes are live streams, and
  temporal leakage — using a classification that did not exist at the simulated cut
  date — silently invalidates every downstream result. This is the failure mode that
  is hardest to detect late, so provenance gets a document of its own from day one
  rather than a paragraph inside `architecture/`.
- **`glossary.md` promoted from optional to required.** The size-M tree lists it as
  "if there is jargon". There is: ETNO, sednoid, selection function, survey
  characterisation, opposition arc, tracklet, NPE. Both the advisor and the thesis
  committee come from computer science, not astronomy.
- **ADR-0001 is stamped as `proposed`, not `accepted`.** The architectural style is
  deliberately left open until the reconnaissance spike measures the real integration
  surface of sorcha, the OSSOS Survey Simulator, ASSIST/REBOUND and the SBI library.
  The first pass of that spike already overturned two working assumptions in opposite
  directions — see [SP-1](architecture/spike-sp1-integration-surface.md) — which is
  evidence enough that deciding at bootstrap time would have meant deciding blind.
- **No `operations/` tree.** Nothing is deployed or operated: the deliverable is a
  package that runs locally and on a cluster, not a service.

## Active docs (size M)

- [x] README · DoD · CI
- [x] product/vision.md
- [x] product/roadmap.md
- [x] product/glossary.md
- [x] requirements/requirements.md *(skeleton)*
- [x] architecture/ (C4 levels 1–2) *(skeleton, blocked on ADR-0001)*
- [x] quality/testing-strategy.md *(skeleton)*
- [x] security/security.md *(baseline)*
- [x] data/provenance.md *(deviation, see above)*
- [x] devops/ci-cd.md
- [ ] operations/runbook.md — not applicable, nothing is operated
- [ ] CHANGELOG.md — when there is a user-facing release
