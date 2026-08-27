"""The fake binding, exercised the way the pipeline exercises it — as a child process.

Calling `main()` in-process would be a cheaper test and a worse one: the seam the
architectural decision is about is a process and file boundary, so the test crosses it
too.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from etno_twin.kernel.config import ExperimentConfig
from etno_twin.kernel.population_model import sample_population
from etno_twin.kernel.rng import stream
from etno_twin.kernel.schemas import DETECTIONS, ORBITS, PHYSICAL_PARAMETERS
from etno_twin.simulators.base import find_log, parse_seeds, phase_profile
from etno_twin.simulators.fake import FAKE_PHASE_MARKERS, build_argv, read_survey_config


def _write_population(config: ExperimentConfig, outdir: Path, n_objects: int, seed: int) -> None:
    objects = sample_population(
        config.population,
        dict(config.library.reference),
        n_objects,
        stream(seed, "test"),
        id_prefix="test",
    )
    ORBITS.write_rows(outdir / "orbits.csv", (obj.orbit_row() for obj in objects))
    PHYSICAL_PARAMETERS.write_rows(
        outdir / "physical-parameters.csv",
        (obj.parameter_row(config.population) for obj in objects),
    )


def _run(config: ExperimentConfig, run_dir: Path, extra: list[str] | None = None) -> None:
    argv = build_argv(
        config_ini=config.campaign.fake.config_ini,
        orbits=run_dir / "orbits.csv",
        physical_parameters=run_dir / "physical-parameters.csv",
        pointing_table=config.campaign.fake.pointing_table,
        run_dir=run_dir,
        stem="detections",
        field_probability=config.campaign.fake.field_probability,
    )
    completed = subprocess.run([*argv, *(extra or [])], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_the_fake_binding_honours_the_declared_detections_schema(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    _write_population(fake_experiment, tmp_path, n_objects=20, seed=7)
    _run(fake_experiment, tmp_path)
    rows = DETECTIONS.read_rows(tmp_path / "detections.csv")
    assert rows, "the fixture and configuration should yield some detections"
    assert all(row["ObjID"].startswith("test_") for row in rows)


def test_the_fake_binding_records_a_seed_the_shared_parser_recovers(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    _write_population(fake_experiment, tmp_path, n_objects=5, seed=11)
    _run(fake_experiment, tmp_path)
    assert parse_seeds(find_log(tmp_path, "detections").read_text(encoding="utf-8")).base > 0


def test_the_fake_binding_draws_its_own_seed_like_the_real_one(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    """Neither binding takes a seed from the caller; both record what they drew."""
    seeds = set()
    for index in range(2):
        run_dir = tmp_path / f"run-{index}"
        run_dir.mkdir()
        _write_population(fake_experiment, run_dir, n_objects=5, seed=3)
        _run(fake_experiment, run_dir)
        seeds.add(parse_seeds(find_log(run_dir, "detections").read_text(encoding="utf-8")).base)
    assert len(seeds) == 2


def test_pinning_the_seed_makes_a_run_repeatable(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    """Available for debugging, never used by a campaign — as the real simulator advises."""
    outputs = []
    for index in range(2):
        run_dir = tmp_path / f"run-{index}"
        run_dir.mkdir()
        _write_population(fake_experiment, run_dir, n_objects=8, seed=5)
        _run(fake_experiment, run_dir, extra=["--seed", "424242"])
        outputs.append((run_dir / "detections.csv").read_text(encoding="utf-8"))
    assert outputs[0] == outputs[1]


def test_an_empty_catalogue_is_a_valid_result(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    """Parts of the parameter space are genuinely invisible to the survey."""
    _write_population(fake_experiment, tmp_path, n_objects=3, seed=13)
    argv = build_argv(
        config_ini=fake_experiment.campaign.fake.config_ini,
        orbits=tmp_path / "orbits.csv",
        physical_parameters=tmp_path / "physical-parameters.csv",
        pointing_table=fake_experiment.campaign.fake.pointing_table,
        run_dir=tmp_path,
        stem="detections",
        field_probability=0.0,
    )
    assert subprocess.run(argv, capture_output=True).returncode == 0
    assert DETECTIONS.read_rows(tmp_path / "detections.csv") == []


def test_the_fake_phase_markers_appear_in_its_own_log(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    _write_population(fake_experiment, tmp_path, n_objects=4, seed=17)
    _run(fake_experiment, tmp_path)
    profile = phase_profile(
        find_log(tmp_path, "detections").read_text(encoding="utf-8"), FAKE_PHASE_MARKERS
    )
    assert set(profile.phases) == {name for name, _ in FAKE_PHASE_MARKERS}


def test_both_bindings_read_their_filters_from_the_same_configuration_file(
    fake_experiment: ExperimentConfig,
) -> None:
    """The mitigation against the fake and the real simulator drifting apart."""
    assert fake_experiment.campaign.fake.config_ini == fake_experiment.campaign.sorcha.config_ini
    survey = read_survey_config(fake_experiment.campaign.fake.config_ini)
    assert survey.ssp_number_tracklets >= 1
    assert survey.bright_limit > 0.0
    assert "r" in survey.observing_filters


def test_the_fake_binding_is_spawned_not_imported(fake_experiment: ExperimentConfig) -> None:
    argv = build_argv(
        config_ini=Path("a.ini"),
        orbits=Path("b.csv"),
        physical_parameters=Path("c.csv"),
        pointing_table=Path("d.csv"),
        run_dir=Path("out"),
        stem="detections",
        field_probability=0.1,
    )
    assert argv[:3] == [sys.executable, "-m", "etno_twin.simulators.fake"]


@pytest.mark.parametrize("n_objects", [1, 12])
def test_detection_depends_on_the_population_not_its_parameters(
    fake_experiment: ExperimentConfig, tmp_path: Path, n_objects: int
) -> None:
    """Whatever the population size, every detected object is one that was put in."""
    _write_population(fake_experiment, tmp_path, n_objects=n_objects, seed=19)
    _run(fake_experiment, tmp_path)
    submitted = {row["ObjID"] for row in ORBITS.read_rows(tmp_path / "orbits.csv")}
    detected = {row["ObjID"] for row in DETECTIONS.read_rows(tmp_path / "detections.csv")}
    assert detected <= submitted
