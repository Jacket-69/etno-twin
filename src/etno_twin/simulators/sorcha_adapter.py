"""The sorcha binding: build an argument vector, run a process, read the run back.

Everything sorcha-specific that is *not* a documented contract lives here and is marked
as such, so a version bump breaks in one place with a test naming what changed rather
than three hundred CPU-days into a campaign.

The binding never imports sorcha. It resolves the installed distribution through the
import system's metadata — enough to record a version and to locate the demo files that
ship inside the wheel — and drives the command-line interface, which is the interface
sorcha supports. That keeps `import sorcha` out of this package entirely, which is what
lets the core be exercised on a machine that has no scientific stack installed.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from etno_twin.simulators.base import PhaseProfile

PHASE_MARKERS: tuple[tuple[str, str], ...] = (
    ("startup", "Sorcha Start (Main)"),
    ("pointing_database", "Reading pointing database..."),
    ("ephemeris_setup", "Pre-computing pointing information for ephemeris generation"),
    ("input_read", "Starting main Sorcha processing loop round"),
    ("nbody_setup", "Generating ASSIST+REBOUND simulations."),
    ("ephemeris_generation", "Generating ephemeris..."),
    ("post_processing", "Ephemeris generated."),
    ("shutdown", "Sorcha process is completed."),
)
"""Log messages that bracket the phases of a run.

**Pinned, non-contractual surface.** These strings are log messages, not API. They are
listed here rather than inferred so that the canary test has something to assert
against; if a version bump renames one, the phase disappears from the profile and the
unattributed time jumps, which the contract test catches.
"""

SIZE_INDEPENDENT_PHASES: tuple[str, ...] = ("startup", "pointing_database", "ephemeris_setup")
"""Phases hypothesised to cost the same regardless of how many objects are simulated.

Reading a 216,000-visit pointing database and loading the ephemeris kernels are paid once
per process. This is a **hypothesis under test**, not an assertion: the sweep estimates
fixed cost independently, as the intercept of a straight-line fit, and the two numbers
are compared. Disagreement means this classification is wrong.
"""

SIZE_DEPENDENT_PHASES: tuple[str, ...] = (
    "input_read",
    "nbody_setup",
    "ephemeris_generation",
    "post_processing",
)


WORKER_EXECUTABLE = "sorcha-run"
"""The console script that does the work, invoked directly rather than through `sorcha run`.

**Pinned, non-contractual surface, and a measurement decision.** `sorcha run` is a
dispatcher: it resolves the verb to `sorcha-<verb>` and runs *that* as a second process.
Driving it would put a wrapper's interpreter start-up inside every timing and, worse,
would point any per-process instrument at the wrapper instead of the worker — the first
peak-memory figure this spike produced was 15 MB, which is a bare interpreter, not a
simulator that has just loaded planetary ephemerides.

Invoking the worker directly measures the process doing the work. The dispatcher's own
source is where this behaviour is read from, and the run log confirms it: the command
line it records is the `sorcha-run` one, never the `sorcha run` one.
"""


EMPTY_OUTPUT_MESSAGE = "No observations left in chunk. No output will be written for this chunk."
COMPLETION_MESSAGE = "Sorcha process is completed."
"""Log messages that identify a successful run which detected nothing.

**Pinned, non-contractual surface, and a divergence the port has to absorb.** When the
linking filter empties a chunk, sorcha exits zero and writes *no output file at all*. The
fake binding writes an empty table with a header. Left alone, that is precisely the
failure the design warns about — the two bindings drifting apart — and it surfaces as a
missing artifact in the middle of a campaign rather than as a population the survey could
not see.

An empty detection catalogue is a valid result, and for parts of the parameter space it is
the expected one. So the adapter normalises: a run that completed and said it had nothing
to write gets an empty, schema-valid table, and the manifest records that the table was
synthesised rather than produced.
"""


def explains_empty_output(log_text: str) -> bool:
    """Whether a run's own log accounts for the absence of an output file.

    Both messages are required. A log that says it wrote nothing but never reports
    completion describes a run that died, and inventing an empty artifact for it would
    turn a failure into a data point.
    """
    return EMPTY_OUTPUT_MESSAGE in log_text and COMPLETION_MESSAGE in log_text


class SorchaNotAvailable(RuntimeError):
    """The sorcha distribution is not installed in this environment."""


def sorcha_version() -> str:
    """Version of the installed sorcha distribution, or a marker that it is absent."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("sorcha")
    except PackageNotFoundError:
        return "not-installed"


def package_data_dir() -> Path:
    """Directory of data files shipped inside the installed sorcha wheel.

    Located through ``find_spec``, which reads the module's origin without executing it.
    """
    spec = importlib.util.find_spec("sorcha")
    if spec is None or spec.origin is None:
        raise SorchaNotAvailable("sorcha is not installed in this environment")
    return Path(spec.origin).parent / "data"


def resolve_pointing_db(spec: str) -> Path:
    """Resolve the pointing database, including the ``auto`` shorthand.

    ``auto`` means the one-year Rubin cadence database that ships inside the sorcha
    wheel: 17 MB, too large to commit and unnecessary to download, since installing the
    package already put it on disk. Its content hash goes into the campaign manifest like
    any other snapshot.
    """
    if spec != "auto":
        path = Path(spec).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"pointing database not found: {path}")
        return path
    candidate = package_data_dir() / "demo" / "baseline_v2.0_1yr.db"
    if not candidate.exists():
        raise SorchaNotAvailable(
            f"expected the packaged demo pointing database at {candidate}; "
            "reinstall sorcha rather than downloading it separately"
        )
    return candidate


def build_argv(
    *,
    executable: str,
    config_ini: Path,
    orbits: Path,
    physical_parameters: Path,
    pointing_db: Path,
    run_dir: Path,
    stem: str,
    ephemeris_cache: Path,
) -> list[str]:
    """The command line for one run.

    ``--ar`` points sorcha at an existing ephemeris cache. Pointing it at a populated
    directory is what keeps a measured run from paying a 780 MB download, and the cache's
    content hash is recorded in the manifest so two machines can be compared.

    The executable is the worker, not the dispatcher — see ``WORKER_EXECUTABLE``.
    """
    return [
        executable,
        "-c",
        str(config_ini),
        "--ob",
        str(orbits),
        "-p",
        str(physical_parameters),
        "--pd",
        str(pointing_db),
        "-o",
        str(run_dir),
        "-t",
        stem,
        "-f",
        "--ar",
        str(ephemeris_cache),
    ]


def fixed_cost_from_profile(profile: PhaseProfile) -> float:
    """Fixed cost of a run as the sum of its size-independent phases."""
    return profile.total_of(SIZE_INDEPENDENT_PHASES)


def marginal_cost_from_profile(profile: PhaseProfile, n_objects: int) -> float:
    """Per-object cost of a run from its size-dependent phases."""
    if n_objects <= 0:
        raise ValueError("n_objects must be positive")
    return profile.total_of(SIZE_DEPENDENT_PHASES) / n_objects


def phase_names() -> Sequence[str]:
    return [name for name, _ in PHASE_MARKERS]
