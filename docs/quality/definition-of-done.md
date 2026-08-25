# Definition of Done

Copy of the canonical checklist from the vault methodology
(`Conocimiento/Procesos/Metodología de Proyectos/Calidad y DoD.md`), with the items
that do not apply to this project marked as such. **It blocks the merge.**

A task is Done if and only if:

- It meets the **acceptance criteria** declared in the story.
- It has **relevant tests** — unit for domain logic, integration for adapters that
  touch real simulators or archives, end-to-end for the single-command reproduction
  path.
- **CI is green** — lint, format, typecheck and tests pass with no new warnings.
- **Code review approved.** Solo developer: a structured self-review against explicit
  criteria — correctness, design, security, tests, documentation — recorded as a pull
  request comment.
- **Documentation updated** if behaviour, contract, dependency or configuration
  changed. An ADR if the decision is costly to reverse.
- **No secrets or sensitive data introduced.**
- **No result depends on information postdating its declared temporal cut.** Project
  specific and non-negotiable: any change touching ingestion, snapshots or identity
  resolution must state how it preserves the temporal cut. See
  [data/provenance.md](../data/provenance.md).
- **Reproducibility preserved** — if the change affects an experiment, the
  single-command path still regenerates its outputs.

Not applicable here: CHANGELOG (no user-facing releases yet), structured logs for
operations, metrics and health checks (nothing is operated).

> "Works on my machine" is not Done. Green CI and an approved review are.
