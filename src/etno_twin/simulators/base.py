"""The survey-simulator port: what both bindings must honour, and how a run is read back.

The contract is small on purpose, because it is the only thing keeping the fake and the
real simulator from drifting apart:

1. **In:** a table of orbits and a table of physical parameters, in the schemas declared
   in `etno_twin.kernel.schemas`.
2. **Out:** a detections table in the declared schema, written under a run directory.
   An empty table is a valid result.
3. **A log** containing the line ``the base rng seed is <integer>``, because neither
   binding takes its seed from the caller — both draw it from the operating system and
   record what they drew.
4. **An exit code**, which is how a dead worker becomes a missing artifact with a
   recorded reason instead of a silent gap.

Point 3 is not an aesthetic choice. sorcha's own source warns that re-using seeds
between simulations produces hard-to-detect correlations in the outputs, and its authors
state that a fixed seed is for testing and "should never be used for science results".
The simulator's stochasticity is part of the forward model; what the pipeline owes is a
record, not a pin. The fake binding reproduces that behaviour exactly so that the
recovery path is exercised on both sides.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_SEED_PATTERN = re.compile(r"the base rng seed is (\d+)")
"""The line every binding must emit, and the canary the version pin is tested against.

Recovering the seed depends on a log message, not on an API, so a version bump can break
it silently. `tests/test_simulator_contract.py` asserts this pattern against a committed
excerpt of a real run log; `tests/test_sorcha_binding.py`, marked `integration`, asserts
it against a live run.
"""

MODULE_SEED_PATTERN = re.compile(r"the rng seed for the (\S+) module is (\d+)")

LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) "
    r"(?P<logger>\S+)\s+(?P<level>\w+)\s+(?P<message>.*)$"
)
LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S,%f"


class SimulatorContractError(RuntimeError):
    """A binding produced something the port does not allow."""


@dataclass(frozen=True)
class SeedRecord:
    """The seeds a run drew, recovered from its log."""

    base: int
    modules: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"base": self.base, "modules": dict(self.modules)}


def parse_seeds(log_text: str) -> SeedRecord:
    """Recover the seeds of a run from its log, or fail loudly.

    Failing loudly is the point: a run whose seed cannot be recovered is a run that
    cannot enter a manifest, and `docs/data/provenance.md` makes the seed a mandatory
    field. Silently writing ``null`` would produce artifacts that look complete.
    """
    match = BASE_SEED_PATTERN.search(log_text)
    if match is None:
        raise SimulatorContractError(
            "no base rng seed in the run log: the binding did not record its seed, or the "
            "log format changed and the canary pattern needs updating"
        )
    modules = {name: int(value) for name, value in MODULE_SEED_PATTERN.findall(log_text)}
    return SeedRecord(base=int(match.group(1)), modules=modules)


@dataclass(frozen=True)
class PhaseProfile:
    """Where a single run spent its time, read from the timestamps in its own log.

    This is the second, independent estimator of fixed cost. The sweep across population
    sizes estimates it as the intercept of a straight-line fit; the phase profile
    estimates it by adding up the phases that do not depend on how many objects were
    simulated. The two are derived from different data and should agree — and when they
    disagree, the classification of phases is what is wrong, which is worth knowing.
    """

    phases: dict[str, float]
    log_span_seconds: float
    unattributed_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "phases": dict(self.phases),
            "log_span_seconds": self.log_span_seconds,
            "unattributed_seconds": self.unattributed_seconds,
        }

    def total_of(self, names: Sequence[str]) -> float:
        return sum(self.phases.get(name, 0.0) for name in names)


def phase_profile(log_text: str, markers: Sequence[tuple[str, str]]) -> PhaseProfile:
    """Attribute a run's wall-clock to named phases.

    ``markers`` is an ordered sequence of ``(phase, message prefix)``: a phase runs from
    its own marker line to the next marker that appears. Marker text is a non-contractual
    surface of whichever binding emits it, which is exactly why the markers are passed in
    by the binding rather than assumed here.
    """
    timeline: list[tuple[datetime, str]] = []
    for line in log_text.splitlines():
        match = LOG_LINE_PATTERN.match(line)
        if match is None:
            continue
        moment = datetime.strptime(match.group("timestamp"), LOG_TIMESTAMP_FORMAT)
        timeline.append((moment, match.group("message")))
    if not timeline:
        return PhaseProfile(phases={}, log_span_seconds=0.0, unattributed_seconds=0.0)

    found: list[tuple[str, datetime]] = []
    cursor = 0
    for phase, needle in markers:
        for index in range(cursor, len(timeline)):
            if timeline[index][1].startswith(needle):
                found.append((phase, timeline[index][0]))
                cursor = index + 1
                break

    phases: dict[str, float] = {}
    for position, (phase, moment) in enumerate(found):
        end = found[position + 1][1] if position + 1 < len(found) else timeline[-1][0]
        phases[phase] = max((end - moment).total_seconds(), 0.0)
    span = (timeline[-1][0] - timeline[0][0]).total_seconds()
    return PhaseProfile(
        phases=phases,
        log_span_seconds=span,
        unattributed_seconds=max(span - sum(phases.values()), 0.0),
    )


def find_log(run_dir: Path, stem: str) -> Path:
    """Locate the log a run wrote.

    sorcha decorates the stem with a timestamp and a process id; the fake does not. Both
    are covered by the same glob, and finding no log — or more than one — is an error
    rather than a guess.
    """
    candidates = sorted(run_dir.glob(f"{stem}*.log"))
    if not candidates:
        raise SimulatorContractError(f"no log matching '{stem}*.log' in {run_dir}")
    if len(candidates) > 1:
        raise SimulatorContractError(
            f"several logs matching '{stem}*.log' in {run_dir}: {[p.name for p in candidates]}"
        )
    return candidates[0]


def detections_path(run_dir: Path, stem: str) -> Path:
    return run_dir / f"{stem}.csv"
