"""Measurement instruments.

Numbers produced here end up in ``measurements.json`` and are cited by ADR-0001, so
they are recorded as structured data and never printed. Two rules the instruments
enforce rather than document:

* Timed work happens inside a ``Stopwatch`` context and nothing else does — hashing
  snapshots, fingerprinting the ephemeris cache and writing manifests all sit outside
  the timed region, because they are the harness, not the thing under test.
* A subprocess is measured from the parent, so the number includes interpreter start-up.
  That is deliberate: process start-up is part of the fixed cost the sweep exists to
  quantify.
"""

from __future__ import annotations

import os
import resource
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

_POLL_INTERVAL_SECONDS = 0.025
_MINIMUM_RELIABLE_SAMPLES = 5


def utc_now() -> str:
    """Timestamp for manifests, in UTC with a trailing ``Z``-equivalent offset."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class Stopwatch:
    """Wall-clock of a block, from a monotonic clock.

    ``time.perf_counter`` rather than ``time.time``: the measurement must not move if
    the system clock is adjusted mid-run.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.started_at: str = ""
        self.seconds: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> Stopwatch:
        self.started_at = utc_now()
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.seconds = time.perf_counter() - self._start

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "started_utc": self.started_at, "wall_seconds": self.seconds}


def _read_vm_hwm_bytes(pid: int) -> int | None:
    """Peak resident set size of a live process, from ``/proc/<pid>/status``.

    ``VmHWM`` is the kernel's own high-water mark, so a poll only has to catch the
    process before it exits, not at its moment of peak usage.
    """
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _descendants(pid: int) -> list[int]:
    """Every process below ``pid``, from the kernel's own child lists.

    A binding may well be a dispatcher that spawns the process doing the work, so
    measuring only the process this package started would report the memory footprint of
    a wrapper. Walking the tree costs a few file reads per poll and removes a whole class
    of silently wrong numbers.
    """
    found: list[int] = []
    frontier = [pid]
    while frontier:
        current = frontier.pop()
        found.append(current)
        try:
            for task in os.listdir(f"/proc/{current}/task"):
                with open(f"/proc/{current}/task/{task}/children", encoding="utf-8") as handle:
                    frontier.extend(int(token) for token in handle.read().split())
        except (OSError, ValueError):
            continue
    return found


class _PeakRssProbe(threading.Thread):
    """Polls the peak RSS of a child and everything it spawns, until it exits."""

    def __init__(self, pid: int, interval: float = _POLL_INTERVAL_SECONDS) -> None:
        super().__init__(daemon=True)
        self.pid = pid
        self.interval = interval
        self.peak_bytes: int | None = None
        self.n_processes_seen: int = 0
        self.n_samples: int = 0
        # Not `_stop`: threading.Thread already defines a private method by that name
        # and shadowing it breaks join().
        self._finished = threading.Event()

    def run(self) -> None:
        while not self._finished.is_set():
            tree = _descendants(self.pid)
            self.n_processes_seen = max(self.n_processes_seen, len(tree))
            for pid in tree:
                observed = _read_vm_hwm_bytes(pid)
                if observed is None:
                    continue
                self.n_samples += 1
                if self.peak_bytes is None or observed > self.peak_bytes:
                    self.peak_bytes = observed
            self._finished.wait(self.interval)

    def stop(self) -> None:
        self._finished.set()


@dataclass
class SubprocessMeasurement:
    """What one measured child process cost."""

    argv: list[str]
    exit_code: int
    wall_seconds: float
    cpu_user_seconds: float
    cpu_system_seconds: float
    peak_rss_bytes: int | None
    peak_rss_source: str
    peak_rss_samples: int
    peak_rss_reliable: bool
    processes_observed: int
    started_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "argv": self.argv,
            "exit_code": self.exit_code,
            "wall_seconds": self.wall_seconds,
            "cpu_user_seconds": self.cpu_user_seconds,
            "cpu_system_seconds": self.cpu_system_seconds,
            "peak_rss_bytes": self.peak_rss_bytes,
            "peak_rss_source": self.peak_rss_source,
            "peak_rss_samples": self.peak_rss_samples,
            "peak_rss_reliable": self.peak_rss_reliable,
            "processes_observed": self.processes_observed,
            "started_utc": self.started_utc,
        }


def run_measured(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    stdout_path: Path | None = None,
) -> SubprocessMeasurement:
    """Run a child process and record what it cost.

    CPU time comes from ``getrusage(RUSAGE_CHILDREN)`` differences, which are exact
    because those counters accumulate. Peak RSS comes from polling the child's own
    ``VmHWM`` across the whole process tree, because ``ru_maxrss`` for children is a
    high-water mark over *all* children the parent ever reaped and would silently report
    the largest earlier run. The reported figure is the largest single process in the
    tree, which is the right quantity while a run has one worker.

    Polling has a floor: a process that lives for a few tens of milliseconds is sampled
    once or twice, before it has allocated anything, and the figure that comes back is an
    underestimate rather than a measurement. Rather than hide that, the sample count is
    recorded and the figure is flagged unreliable below a handful of samples — a run of the
    fake binding takes 40 ms and its memory figure means nothing; a run of the real one
    takes half a minute and its figure means what it says.
    """
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = utc_now()
    handle = None
    if stdout_path is not None:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        handle = stdout_path.open("wb")
    start = time.perf_counter()
    try:
        process = subprocess.Popen(  # argv is built by this package, never a shell
            list(argv),
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            stdout=handle if handle is not None else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if handle is not None else subprocess.DEVNULL,
        )
        probe = _PeakRssProbe(process.pid)
        probe.start()
        exit_code = process.wait()
        probe.stop()
        probe.join(timeout=1.0)
    finally:
        if handle is not None:
            handle.close()
    wall = time.perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak = probe.peak_bytes
    source = "proc_vm_hwm"
    if peak is None:
        peak = int(after.ru_maxrss) * 1024
        source = "rusage_children_maxrss_upper_bound"
    return SubprocessMeasurement(
        argv=list(argv),
        exit_code=exit_code,
        wall_seconds=wall,
        cpu_user_seconds=after.ru_utime - before.ru_utime,
        cpu_system_seconds=after.ru_stime - before.ru_stime,
        peak_rss_bytes=peak,
        peak_rss_source=source,
        peak_rss_samples=probe.n_samples,
        peak_rss_reliable=probe.n_samples >= _MINIMUM_RELIABLE_SAMPLES,
        processes_observed=probe.n_processes_seen,
        started_utc=started,
    )


@dataclass
class ByteLedger:
    """Sizes of the artifacts a stage produced, by role.

    Bytes at a boundary are half of what the ADR is deciding on, so they are collected
    the same way everywhere instead of being counted ad hoc per stage.
    """

    entries: dict[str, int] = field(default_factory=dict)

    def record(self, role: str, path: Path) -> int:
        size = path.stat().st_size
        self.entries[role] = self.entries.get(role, 0) + size
        return size

    def record_bytes(self, role: str, count: int) -> None:
        self.entries[role] = self.entries.get(role, 0) + count

    def total(self) -> int:
        return sum(self.entries.values())

    def as_dict(self) -> dict[str, Any]:
        return {"by_role": dict(self.entries), "total_bytes": self.total()}


def environment_snapshot(packages: Sequence[str] = ()) -> dict[str, Any]:
    """Machine and package versions, so a measurement is attributable to a machine."""
    import platform
    from importlib.metadata import PackageNotFoundError, version

    versions: dict[str, str] = {}
    for name in packages:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "not-installed"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "packages": versions,
    }
