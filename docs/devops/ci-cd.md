# CI/CD

**CD does not apply**: nothing is deployed. This project ships a package and
reproducible experiments, not a running service.

## CI pipeline

Runs on every push and pull request (`.github/workflows/ci.yml`):

| Stage | Tool | Gate |
|---|---|---|
| Lint | ruff | No new warnings |
| Format check | ruff format | Clean |
| Typecheck | mypy | Clean on `src/` |
| Unit tests | pytest | Green |

Integration tests against real survey simulators are **excluded from CI by design**:
they need a Fortran toolchain and external characterisation archives. They run locally
and are marked `integration`. The consequence is a hard architectural requirement, not
a gap: the core must be exercisable against fake simulators (see
[testing strategy](../quality/testing-strategy.md)).

## Branching and releases

GitHub Flow with short-lived branches; `main` always in a working state. Conventional
Commits. No releases yet — versioning and CHANGELOG start when there is something
user-facing to release.
