# Fixtures

Small, committed inputs that let the whole pipeline run with no network access, no
Fortran toolchain and none of the 780 MB of ephemeris kernels the real survey simulator
needs. They are what makes the continuous-integration half of the double binding possible.

These are pipeline inputs, not test data. The tests use them too, but the graph
continuous integration runs consumes them directly.

## `sorcha/etno-twin-demo.ini` — the shared survey configuration

Derived from `sorcha/data/demo/sorcha_config_demo.ini`, shipped inside sorcha 1.2.1
(`sha256 c21b2dcc…89e28`, recorded in the file's own header). One edit against that
parent: `aux_format` is `csv` rather than `whitespace`, so the tables crossing the stage
boundary are the comma-separated artifacts with declared headers that every other
boundary uses.

**Both bindings read this file.** The fake one takes its saturation limit, its fading
function and its linking filter from it, which is what stops the two bindings from
quietly disagreeing about what "detected" means.

## `pointing/rubin-baseline-1yr-subsample.csv` — the cadence the fake binding sees

480 visits over 48 nights, extracted from `baseline_v2.0_1yr.db` — the one-year Rubin
cadence database that also ships inside the sorcha wheel — with **sorcha's own SQL
projection**, so the fixture is schema-identical to what the real binding reads rather
than merely similar. Rebuild it with:

```bash
uv run python scripts/build_pointing_fixture.py
```

Nights are sampled in blocks of consecutive observing nights rather than spread evenly
across the year. That is not an aesthetic choice: the linking filter needs several
tracklets inside a short tracking window, and a fixture of evenly spaced nights would make
linking impossible by construction, so the fake would detect nothing and the graph would
walk end to end while proving nothing.

The 17 MB database itself is not committed. It is not downloaded either — installing
sorcha already puts it on disk, and the campaign stage resolves it from the installed
package and hashes it into the manifest like any other snapshot.

## `logs/*.log` — canary excerpts

Two excerpts of real runs, kept because the pipeline recovers a run's seed and its phase
timings from **log messages, not from an API**. Neither is a contract, so a version bump
can break both silently; asserting against these makes a bump fail in seconds on a machine
with nothing installed.

- `sorcha-run-excerpt.log` — a run that detected something.
- `sorcha-empty-run-excerpt.log` — a run whose linking filter emptied the chunk. It
  completed successfully and wrote **no output file at all**, which is the divergence
  from the fake binding that the adapter absorbs.

Only the lines the parsers read are kept: the seed lines and the phase boundaries. The
recorded command line and the copy of the configuration file are dropped — a fixture
exists to pin a log format, not to carry one machine's paths into the repository.

Regenerate them after a version bump. A diff here *is* the bump breaking a surface this
project depends on, which is the whole point.
