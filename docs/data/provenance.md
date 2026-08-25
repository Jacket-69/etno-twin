# Data provenance, snapshots and temporal cuts

> Deviation from the standard size-M documentation tree, added deliberately. The
> catalogues this project consumes are live streams: objects get new astrometry,
> refined orbits and new classifications continuously. Using information that did not
> exist at the simulated cut date invalidates every downstream result — and does so
> **silently**, producing numbers that look correct. This is the failure mode that is
> hardest to catch late, so it gets its own document and its own tests from day one.

## The rule

Every input to an experiment is a **snapshot**: an immutable, content-addressed copy of
a source as of a declared date, never a live query at run time.

An experiment declares its **temporal cut**. Every snapshot it consumes must be at or
before that cut, and every field derived from a source must be traceable to a value
that existed at that date.

## Snapshot manifest

Each snapshot carries a manifest recording, at minimum:

- Source identity and access method (endpoint, file, query).
- Retrieval timestamp and the declared temporal cut.
- Content hash of the raw payload, before any transformation.
- Code version that produced the snapshot.
- Row count and schema fingerprint.

Rebuilding a snapshot from the same source and cut must produce the same content hash.
When it does not, that is a finding to investigate — the source changed history — not
a test to relax.

## Known leakage traps

- **Classification date vs discovery date.** An object's dynamical classification is
  assigned, and often revised, well after discovery. Using discovery date as a proxy
  for "when we knew what this was" leaks future knowledge into the past. The
  classification date must come from a per-object source that records it, never from a
  proxy.
- **Orbit refinement.** Orbital elements in a catalogue reflect all astrometry to date,
  including observations taken after the cut. An experiment simulating knowledge as of
  date D needs the orbit as it stood at D, not today's orbit filtered by date.
- **Survey characterisation revisions.** Published characterisations are updated. The
  version used must be pinned per experiment.
- **Cross-source identity.** The same object may appear under different designations
  across sources, and identity resolution itself can encode later knowledge. Identity
  mapping is versioned along with the snapshot.

## Verification

- Snapshot rebuild determinism is a test: same source, same cut, same hash.
- Any field used in inference is traceable to a manifest — enforced by construction,
  not by review.
- Fixtures for tests are small, versioned snapshots committed to the repository, so the
  test suite never touches the network.

TODO — fill in per-source detail (MPC, DES, OSSOS, CFEPS) once the reconnaissance spike
establishes what each source exposes and in what format.
