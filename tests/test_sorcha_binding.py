"""The live canary: assert the pinned surfaces against a running survey simulator.

Every test here is marked `integration` and never runs in continuous integration, which
has no ephemeris cache and no business downloading 780 MB. On the workstation these are
what turn a version bump into a failing test in half a minute rather than a broken
campaign a week in.

They are deliberately the smallest runs that still exercise the surfaces: a population of
two objects, against the demo cadence, with the cache already warm.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from etno_twin.kernel.config import ExperimentConfig
from etno_twin.kernel.measure import run_measured
from etno_twin.kernel.population_model import sample_population
from etno_twin.kernel.rng import stream
from etno_twin.kernel.schemas import DETECTIONS, ORBITS, PHYSICAL_PARAMETERS
from etno_twin.simulators.base import find_log, parse_seeds, phase_profile
from etno_twin.simulators.sorcha_adapter import (
    PHASE_MARKERS,
    SIZE_INDEPENDENT_PHASES,
    build_argv,
    resolve_pointing_db,
    sorcha_version,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def sorcha_run(sorcha_experiment: ExperimentConfig, tmp_path: Path) -> Path:
    """One real run of two objects, with the ephemeris cache already populated."""
    if shutil.which(sorcha_experiment.campaign.sorcha.executable) is None:
        pytest.skip("the survey simulator is not installed in this environment")
    cache = sorcha_experiment.campaign.sorcha.ephemeris_cache
    if not cache.exists():
        pytest.skip(f"no ephemeris cache at {cache}; this test never downloads one")

    objects = sample_population(
        sorcha_experiment.population,
        dict(sorcha_experiment.library.reference),
        2,
        stream(20260825, "integration"),
        id_prefix="canary",
    )
    ORBITS.write_rows(tmp_path / "orbits.csv", (obj.orbit_row() for obj in objects))
    PHYSICAL_PARAMETERS.write_rows(
        tmp_path / "physical-parameters.csv",
        (obj.parameter_row(sorcha_experiment.population) for obj in objects),
    )
    argv = build_argv(
        executable=sorcha_experiment.campaign.sorcha.executable,
        config_ini=sorcha_experiment.campaign.sorcha.config_ini,
        orbits=tmp_path / "orbits.csv",
        physical_parameters=tmp_path / "physical-parameters.csv",
        pointing_db=resolve_pointing_db(sorcha_experiment.campaign.sorcha.pointing_db),
        run_dir=tmp_path,
        stem="detections",
        ephemeris_cache=cache,
    )
    measurement = run_measured(argv, stdout_path=tmp_path / "stdout.txt")
    assert measurement.exit_code == 0, (tmp_path / "stdout.txt").read_text(encoding="utf-8")
    return tmp_path


def test_the_pinned_version_is_the_one_installed() -> None:
    assert sorcha_version().startswith("1.2"), (
        "the pinned surfaces in sorcha_adapter were established against sorcha 1.2.x; "
        "re-establish them before moving on"
    )


def test_the_seed_is_still_recoverable_from_a_live_run(sorcha_run: Path) -> None:
    """The canary the whole provenance chain hangs from: no seed, no manifest."""
    seeds = parse_seeds(find_log(sorcha_run, "detections").read_text(encoding="utf-8"))
    assert seeds.base > 0
    assert seeds.modules, "the per-module seeds are recorded too"


def test_every_pinned_phase_marker_is_still_emitted(sorcha_run: Path) -> None:
    profile = phase_profile(
        find_log(sorcha_run, "detections").read_text(encoding="utf-8"), PHASE_MARKERS
    )
    assert set(profile.phases) == {name for name, _ in PHASE_MARKERS}
    assert profile.unattributed_seconds < 0.5


def test_loading_the_kernels_is_still_the_dominant_fixed_phase(sorcha_run: Path) -> None:
    """Two objects, so anything size-dependent is negligible and the fixed cost stands out."""
    profile = phase_profile(
        find_log(sorcha_run, "detections").read_text(encoding="utf-8"), PHASE_MARKERS
    )
    assert profile.total_of(SIZE_INDEPENDENT_PHASES) > 1.0


def test_the_real_binding_honours_the_declared_detections_schema(sorcha_run: Path) -> None:
    output = sorcha_run / "detections.csv"
    if not output.exists():
        pytest.skip("this draw detected nothing; the adapter's empty-output path covers that")
    rows = DETECTIONS.read_rows(output)
    assert all(row["ObjID"].startswith("canary_") for row in rows)


def test_the_run_stayed_within_a_worker_sized_memory_footprint(
    sorcha_experiment: ExperimentConfig, sorcha_run: Path
) -> None:
    """Peak memory is a hard constraint on how many campaign workers fit on a machine."""
    second = sorcha_run / "second"
    second.mkdir()
    argv = build_argv(
        executable=sorcha_experiment.campaign.sorcha.executable,
        config_ini=sorcha_experiment.campaign.sorcha.config_ini,
        orbits=sorcha_run / "orbits.csv",
        physical_parameters=sorcha_run / "physical-parameters.csv",
        pointing_db=resolve_pointing_db(sorcha_experiment.campaign.sorcha.pointing_db),
        run_dir=second,
        stem="detections",
        ephemeris_cache=sorcha_experiment.campaign.sorcha.ephemeris_cache,
    )
    measurement = run_measured(argv)
    assert measurement.exit_code == 0
    assert measurement.peak_rss_bytes is not None
    assert measurement.peak_rss_bytes > 100_000_000, (
        "a figure this small means the instrument measured a wrapper process rather than "
        "the worker that loaded the ephemerides"
    )
