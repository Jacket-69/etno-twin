"""The toy population model, and the importance weights the library measurement rests on."""

from __future__ import annotations

import math

import pytest

from etno_twin.kernel.config import ExperimentConfig
from etno_twin.kernel.population_model import (
    importance_weights,
    object_density,
    read_population,
    sample_population,
)
from etno_twin.kernel.rng import stream
from etno_twin.kernel.schemas import ORBITS, PHYSICAL_PARAMETERS
from etno_twin.kernel.stats import kish_effective_sample_size

REFERENCE = {"size_slope_alpha": 0.6, "inclination_width_deg": 35.0}


def _population(config: ExperimentConfig, n: int = 200, seed: int = 3, theta=None):
    return sample_population(config.population, theta or REFERENCE, n, stream(seed, "test"))


def test_every_object_lands_inside_the_configured_ranges(
    fake_experiment: ExperimentConfig,
) -> None:
    a_low, a_high = fake_experiment.population.semi_major_axis_au
    q_low, q_high = fake_experiment.population.perihelion_au
    h_low, h_high = fake_experiment.population.absolute_magnitude_r
    for obj in _population(fake_experiment):
        assert a_low <= obj.semi_major_axis_au <= a_high
        assert q_low <= obj.perihelion_au <= q_high + 1e-9
        assert h_low <= obj.absolute_magnitude_r <= h_high
        assert 0.0 <= obj.eccentricity < 1.0


def test_the_inclination_support_is_truncated_at_the_configured_multiple(
    fake_experiment: ExperimentConfig,
) -> None:
    limit = (
        REFERENCE["inclination_width_deg"] * fake_experiment.population.inclination_truncation_scale
    )
    assert all(obj.inclination_deg <= limit for obj in _population(fake_experiment))


def test_sampling_is_reproducible_from_its_stream(fake_experiment: ExperimentConfig) -> None:
    first = _population(fake_experiment, n=20, seed=9)
    second = _population(fake_experiment, n=20, seed=9)
    assert [obj.orbit_row() for obj in first] == [obj.orbit_row() for obj in second]


def test_a_steeper_slope_produces_fainter_objects(fake_experiment: ExperimentConfig) -> None:
    """The parameter has to move the population, or the inference has nothing to learn."""
    shallow = _population(fake_experiment, n=400, theta={**REFERENCE, "size_slope_alpha": 0.2})
    steep = _population(fake_experiment, n=400, theta={**REFERENCE, "size_slope_alpha": 1.0})
    mean_shallow = sum(o.absolute_magnitude_r for o in shallow) / len(shallow)
    mean_steep = sum(o.absolute_magnitude_r for o in steep) / len(steep)
    assert mean_steep > mean_shallow


def test_identical_parameters_give_uniform_weights(fake_experiment: ExperimentConfig) -> None:
    objects = _population(fake_experiment, n=50)
    weights = importance_weights(fake_experiment.population, objects, REFERENCE, REFERENCE)
    assert all(w == pytest.approx(1.0) for w in weights.weights)
    assert weights.n_rejected == 0
    assert kish_effective_sample_size(list(weights.weights)) == pytest.approx(50.0)


def test_moving_the_parameters_erodes_the_effective_sample_size(
    fake_experiment: ExperimentConfig,
) -> None:
    """The behaviour the whole ladder is built to quantify."""
    objects = _population(fake_experiment, n=300)
    previous = float(len(objects)) + 1.0
    for target in (
        REFERENCE,
        {"size_slope_alpha": 0.7, "inclination_width_deg": 30.0},
        {"size_slope_alpha": 0.85, "inclination_width_deg": 24.0},
        {"size_slope_alpha": 1.0, "inclination_width_deg": 17.5},
    ):
        weights = importance_weights(fake_experiment.population, objects, target, REFERENCE)
        current = kish_effective_sample_size(list(weights.weights))
        assert current < previous
        previous = current


def test_a_narrower_target_rejects_part_of_the_library(
    fake_experiment: ExperimentConfig,
) -> None:
    """Rejection is a real number, not a column of zeros: the support is parameter-dependent."""
    objects = _population(fake_experiment, n=300)
    weights = importance_weights(
        fake_experiment.population,
        objects,
        {"size_slope_alpha": 0.6, "inclination_width_deg": 10.0},
        REFERENCE,
    )
    assert weights.n_rejected > 0
    assert 0.0 < weights.rejected_fraction < 1.0
    assert all(
        weight == 0.0
        for obj, weight in zip(objects, weights.weights, strict=True)
        if obj.inclination_deg > 30.0
    )


def test_a_library_not_drawn_from_its_declared_reference_is_refused(
    fake_experiment: ExperimentConfig,
) -> None:
    objects = _population(fake_experiment, n=50)
    with pytest.raises(ValueError, match="was not drawn from the reference"):
        importance_weights(
            fake_experiment.population,
            objects,
            REFERENCE,
            {"size_slope_alpha": 0.6, "inclination_width_deg": 5.0},
        )


def test_the_density_is_positive_inside_the_support_and_finite(
    fake_experiment: ExperimentConfig,
) -> None:
    for obj in _population(fake_experiment, n=50):
        density = object_density(fake_experiment.population, REFERENCE, obj)
        assert density > 0.0
        assert math.isfinite(density)


def test_a_population_survives_a_round_trip_through_its_artifacts(
    fake_experiment: ExperimentConfig, tmp_path
) -> None:
    """Stages meet through files; the files must carry everything the next stage needs."""
    objects = _population(fake_experiment, n=25, seed=21)
    ORBITS.write_rows(tmp_path / "orbits.csv", (o.orbit_row() for o in objects))
    PHYSICAL_PARAMETERS.write_rows(
        tmp_path / "physical-parameters.csv",
        (o.parameter_row(fake_experiment.population) for o in objects),
    )
    restored = read_population(tmp_path / "orbits.csv", tmp_path / "physical-parameters.csv")
    assert [o.obj_id for o in restored] == [o.obj_id for o in objects]
    for original, copy in zip(objects, restored, strict=True):
        assert copy.inclination_deg == pytest.approx(original.inclination_deg)
        assert copy.absolute_magnitude_r == pytest.approx(original.absolute_magnitude_r)
