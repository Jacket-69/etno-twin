# Testing strategy

Follows the canonical pyramid from the vault methodology
(`Conocimiento/Procesos/Metodología de Proyectos/Calidad y DoD.md`), with the coverage
targets and layer split defined there. What is specific to this project:

## What must be true regardless of architecture

- **The core runs without external toolchains.** CI has no Fortran compiler and no
  survey characterisation archives; the full chain must be exercisable against fake
  simulators that honour the same interface. If a test needs the real simulator, it is
  an integration test, marked and excluded from the default run.
- **Golden files over assertions on floats.** Data transformation stages are verified
  against small, versioned reference outputs, not hand-written expectations.
- **Snapshot rebuild determinism is a test**, not a convention — same source, same
  temporal cut, same content hash.
- **Fixtures never touch the network.** Test data is committed, small and
  representative by category.

## Layers

| Layer | What it covers here | Target |
|---|---|---|
| Unit | Coordinate and element transformations, identity resolution, selection-function math, catalogue schema normalisation | ≥ 80% lines |
| Integration | Real survey simulators, real catalogue sources, campaign resumption after interruption | ≥ 60% lines |
| End-to-end | The single-command reproduction path, on toy data | A handful, kept green |

TODO — concrete test plan per module once ADR-0001 is accepted.
