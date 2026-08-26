"""The survey-simulator port, and the canary that guards the surfaces it rests on.

The recovery of a run's seed depends on a log message rather than an API, and so does the
attribution of a run's wall-clock to phases. Neither is contractual, so a version bump can
break both silently. These tests assert them against an excerpt of a real run log, kept in
the repository, so a bump breaks here — in seconds, on a machine with nothing installed —
rather than partway into a campaign.

The excerpt is a fixture; the live assertion against a running simulator is in
`test_sorcha_binding.py`, marked `integration` and excluded from the default run.
"""

from __future__ import annotations

import pytest

from etno_twin.simulators.base import (
    BASE_SEED_PATTERN,
    SimulatorContractError,
    find_log,
    parse_seeds,
    phase_profile,
)
from etno_twin.simulators.fake import FAKE_PHASE_MARKERS
from etno_twin.simulators.sorcha_adapter import (
    EMPTY_OUTPUT_MESSAGE,
    PHASE_MARKERS,
    SIZE_DEPENDENT_PHASES,
    SIZE_INDEPENDENT_PHASES,
    build_argv,
    explains_empty_output,
)


def test_the_base_seed_is_recoverable_from_a_real_log(sorcha_log_excerpt: str) -> None:
    assert parse_seeds(sorcha_log_excerpt).base == 1976528314


def test_the_per_module_seeds_are_recovered_too(sorcha_log_excerpt: str) -> None:
    modules = parse_seeds(sorcha_log_excerpt).modules
    assert modules["sorcha.modules.PPRandomizeMeasurements"] == 897560051
    assert modules["sorcha.modules.PPDropObservations"] == 960780149


def test_the_seed_pattern_matches_the_exact_message_the_simulator_emits() -> None:
    line = (
        "2026-08-25 20:05:38,981 sorcha.utilities.sorchaArguments INFO     "
        "the base rng seed is 1976528314 "
    )
    assert BASE_SEED_PATTERN.search(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "the base rng seed is",
        "the base rng seed was 42",
        "the base RNG seed is 42",
    ],
)
def test_a_changed_seed_message_is_not_silently_accepted(line: str) -> None:
    """What the canary is for: a near-miss must fail, not parse as something."""
    assert BASE_SEED_PATTERN.search(line) is None


def test_a_log_without_a_seed_is_refused_rather_than_recorded_as_null() -> None:
    with pytest.raises(SimulatorContractError, match="no base rng seed"):
        parse_seeds("2026-08-25 20:05:38,980 root INFO     Sorcha Start (Main) ")


def test_every_pinned_phase_marker_still_appears_in_a_real_log(sorcha_log_excerpt: str) -> None:
    profile = phase_profile(sorcha_log_excerpt, PHASE_MARKERS)
    assert set(profile.phases) == {name for name, _ in PHASE_MARKERS}


def test_the_phase_profile_accounts_for_the_whole_run(sorcha_log_excerpt: str) -> None:
    profile = phase_profile(sorcha_log_excerpt, PHASE_MARKERS)
    assert sum(profile.phases.values()) == pytest.approx(profile.log_span_seconds, abs=1e-6)
    assert profile.unattributed_seconds == pytest.approx(0.0, abs=1e-6)


def test_the_phase_classification_covers_every_phase_exactly_once() -> None:
    named = {name for name, _ in PHASE_MARKERS}
    classified = set(SIZE_INDEPENDENT_PHASES) | set(SIZE_DEPENDENT_PHASES)
    assert classified <= named
    assert not set(SIZE_INDEPENDENT_PHASES) & set(SIZE_DEPENDENT_PHASES)


def test_loading_the_ephemeris_kernels_dominates_the_fixed_phases(sorcha_log_excerpt: str) -> None:
    """The finding the whole sweep rests on, pinned so a regression is visible."""
    profile = phase_profile(sorcha_log_excerpt, PHASE_MARKERS)
    assert profile.phases["ephemeris_setup"] > 10.0
    assert profile.total_of(SIZE_INDEPENDENT_PHASES) > 10.0


def test_a_missing_marker_leaves_time_unattributed_rather_than_misattributed() -> None:
    log = "\n".join(
        [
            "2026-01-01 00:00:00,000 root INFO     Sorcha Start (Main) ",
            "2026-01-01 00:00:10,000 root INFO     Something Else Entirely ",
            "2026-01-01 00:00:20,000 root INFO     Sorcha process is completed. ",
        ]
    )
    profile = phase_profile(log, PHASE_MARKERS)
    assert "pointing_database" not in profile.phases
    assert profile.unattributed_seconds == pytest.approx(0.0, abs=1e-6)
    assert profile.phases["startup"] == pytest.approx(20.0)


def test_both_bindings_declare_a_startup_marker() -> None:
    """One profiler reads both logs, so both must mark where a run begins."""
    assert PHASE_MARKERS[0][0] == FAKE_PHASE_MARKERS[0][0] == "startup"


def test_finding_no_log_is_an_error_rather_than_a_guess(tmp_path) -> None:
    with pytest.raises(SimulatorContractError, match="no log matching"):
        find_log(tmp_path, "detections")


def test_finding_several_logs_is_an_error_rather_than_a_guess(tmp_path) -> None:
    (tmp_path / "detections-a.log").write_text("", encoding="utf-8")
    (tmp_path / "detections-b.log").write_text("", encoding="utf-8")
    with pytest.raises(SimulatorContractError, match="several logs"):
        find_log(tmp_path, "detections")


def test_the_argument_vector_drives_the_worker_not_the_dispatcher(tmp_path) -> None:
    argv = build_argv(
        executable="sorcha-run",
        config_ini=tmp_path / "survey.ini",
        orbits=tmp_path / "orbits.csv",
        physical_parameters=tmp_path / "params.csv",
        pointing_db=tmp_path / "pointing.db",
        run_dir=tmp_path,
        stem="detections",
        ephemeris_cache=tmp_path / "cache",
    )
    assert argv[0] == "sorcha-run"
    assert "run" not in argv[:2]
    assert "--ar" in argv, "the ephemeris cache must be pointed at, never downloaded"


def test_a_run_that_detected_nothing_is_recognised(repo_root) -> None:
    """The real simulator writes no file at all when the linking filter empties a chunk.

    The fake writes an empty table. Both are successful runs of a population the survey
    could not see, and the adapter is where the two are reconciled — but only when the log
    accounts for the absence.
    """
    log = (repo_root / "fixtures" / "logs" / "sorcha-empty-run-excerpt.log").read_text(
        encoding="utf-8"
    )
    assert explains_empty_output(log)
    assert parse_seeds(log).base > 0


def test_a_completed_run_with_output_is_not_mistaken_for_an_empty_one(
    sorcha_log_excerpt: str,
) -> None:
    assert not explains_empty_output(sorcha_log_excerpt)


def test_a_run_that_died_before_finishing_is_not_treated_as_empty() -> None:
    """Inventing an empty artifact for a dead worker would turn a failure into a data point."""
    assert not explains_empty_output(
        "2026-01-01 00:00:00,000 sorcha.sorcha INFO     " + EMPTY_OUTPUT_MESSAGE + " "
    )
