# Security baseline

This project operates no service, stores no personal data and exposes no network
surface. The baseline is correspondingly small, but not empty.

## Non-negotiables

- **No secrets in the repository.** Nothing here requires credentials today; if access
  to an authenticated data platform is added, credentials go in the environment and
  never in configuration files that are committed.
- **Dependencies are pinned and auditable.** The scientific Python stack pulls in a
  large transitive tree; the lockfile is committed and dependency updates are reviewed,
  not applied blindly.
- **External code execution is explicit.** Compiling and running third-party Fortran
  and native extensions is part of the design; it happens through declared,
  version-pinned packages, not by fetching and building arbitrary sources at run time.
- **Input data is validated at the boundary.** Catalogue files from external archives
  are parsed defensively: malformed input must fail loudly at ingestion, never produce
  silently wrong numbers downstream.

## Not applicable

Authentication, authorisation, session handling, PII handling, threat modelling per
feature. If the visualisation platform is ever served publicly, this section is
revisited before that happens.
