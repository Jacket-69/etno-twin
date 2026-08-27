"""The experiment configuration: one file as the root of the manifest.

The point these tests defend is that the arguments of the measurement — the ladder of
population sizes and the ladder of parameter distances — live in the configuration and
nowhere else. A constant that crept into a stage would still produce numbers; it would
just produce numbers nobody can change without editing code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etno_twin.kernel.config import (
    ConfigError,
    ExperimentConfig,
    clamp_to_prior,
    load_experiment,
    theta_columns,
    theta_from_scale,
    theta_vector,
)


def test_both_shipped_experiments_load(repo_root: Path) -> None:
    for name in ("smoke-fake", "smoke-sorcha"):
        assert load_experiment(repo_root / "experiments" / f"{name}.toml").name == name


def test_the_two_smoke_experiments_differ_only_in_their_binding(repo_root: Path) -> None:
    """Same graph, different port — the claim, asserted rather than described."""
    fake = load_experiment(repo_root / "experiments" / "smoke-fake.toml")
    sorcha = load_experiment(repo_root / "experiments" / "smoke-sorcha.toml")
    assert fake.campaign.binding == "fake"
    assert sorcha.campaign.binding == "sorcha"
    assert fake.population.as_dict() == sorcha.population.as_dict()
    assert fake.prior.as_dict() == sorcha.prior.as_dict()
    assert fake.dataset.as_dict() == sorcha.dataset.as_dict()
    assert fake.training.as_dict() == sorcha.training.as_dict()
    assert fake.library.as_dict() == sorcha.library.as_dict()
    assert fake.campaign.sweep_objects == sorcha.campaign.sweep_objects
    assert fake.campaign.n_draws == sorcha.campaign.n_draws


def test_the_configuration_digest_identifies_the_file(fake_experiment: ExperimentConfig) -> None:
    reference = fake_experiment.reference()
    assert len(reference["config_sha256"]) == 64
    assert reference["prior_fingerprint"] != reference["config_sha256"]


def test_the_ladders_come_from_the_configuration(fake_experiment: ExperimentConfig) -> None:
    assert len(fake_experiment.library.theta_ladder_scale) > 1
    assert fake_experiment.library.theta_ladder_scale[0] == 0.0
    assert fake_experiment.campaign.sweep_objects


def test_the_first_rung_of_the_ladder_is_the_library_itself(
    fake_experiment: ExperimentConfig,
) -> None:
    assert theta_from_scale(fake_experiment, 0.0) == fake_experiment.library.reference


def test_a_full_prior_width_of_distance_is_one_width_in_total(
    fake_experiment: ExperimentConfig,
) -> None:
    """Normalised direction: adding a parameter must not silently change the step size."""
    reference = fake_experiment.library.reference
    moved = theta_from_scale(fake_experiment, 1.0)
    total = sum(
        abs(moved[name] - reference[name]) / fake_experiment.prior.component(name).width
        for name in reference
    )
    assert total == pytest.approx(1.0)


def test_the_ladder_walks_away_from_the_reference_monotonically(
    fake_experiment: ExperimentConfig,
) -> None:
    distances = []
    for scale in fake_experiment.library.theta_ladder_scale:
        theta = theta_from_scale(fake_experiment, scale)
        distances.append(
            sum(abs(theta[name] - fake_experiment.library.reference[name]) for name in theta)
        )
    assert distances == sorted(distances)


def test_the_ladder_stays_inside_the_prior_support(fake_experiment: ExperimentConfig) -> None:
    for scale in fake_experiment.library.theta_ladder_scale:
        theta = theta_from_scale(fake_experiment, scale)
        assert clamp_to_prior(fake_experiment.prior, theta) == theta


def test_parameters_have_a_canonical_order(fake_experiment: ExperimentConfig) -> None:
    """The dataset columns and the network's input must not depend on dictionary order."""
    names = fake_experiment.prior.names
    assert names == tuple(sorted(names))
    assert theta_columns(fake_experiment.prior) == tuple(f"theta_{n}" for n in names)
    theta = theta_from_scale(fake_experiment, 0.0)
    assert theta_vector(fake_experiment.prior, theta) == tuple(theta[n] for n in names)


def test_a_prior_change_changes_the_fingerprint(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    """A stored dataset is valid only for the prior it was drawn from."""
    text = fake_experiment.path.read_text(encoding="utf-8").replace("high = 1.0", "high = 1.2", 1)
    altered = tmp_path / "altered.toml"
    altered.write_text(text, encoding="utf-8")
    assert load_experiment(altered).prior.fingerprint() != fake_experiment.prior.fingerprint()


@pytest.mark.parametrize(
    ("substitution", "message"),
    [
        (('binding = "fake"', 'binding = "invented"'), "must be 'fake' or 'sorcha'"),
        (
            ("size_slope_alpha = 0.6", "size_slope_alpha = 9.9"),
            "outside its prior support",
        ),
        (
            ("semi_major_axis_au = [50.0, 150.0]", "semi_major_axis_au = [150.0, 50.0]"),
            "must be increasing",
        ),
    ],
)
def test_a_malformed_configuration_is_refused_with_a_reason(
    fake_experiment: ExperimentConfig, tmp_path: Path, substitution: tuple[str, str], message: str
) -> None:
    text = fake_experiment.path.read_text(encoding="utf-8").replace(*substitution, 1)
    broken = tmp_path / "broken.toml"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_experiment(broken)


def test_a_prior_parameter_missing_from_the_ladder_is_refused(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    text = fake_experiment.path.read_text(encoding="utf-8").replace(
        '[prior.inclination_width_deg]\ndistribution = "uniform"\nlow = 5.0\nhigh = 40.0',
        '[prior.inclination_width_deg]\ndistribution = "uniform"\nlow = 5.0\nhigh = 40.0\n\n'
        '[prior.unused_parameter]\ndistribution = "uniform"\nlow = 0.0\nhigh = 1.0',
        1,
    )
    broken = tmp_path / "broken.toml"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="omits prior parameters"):
        load_experiment(broken)


def test_the_criterion_is_evaluated_against_several_declared_catalogue_sizes(
    fake_experiment: ExperimentConfig,
) -> None:
    """Fixing one N_obs would turn a published threshold into an arbitrary verdict."""
    scenarios = fake_experiment.library.n_obs_scenarios
    assert len(scenarios) >= 2
    assert [s.n_obs for s in scenarios] == sorted(s.n_obs for s in scenarios)
    assert all(s.provenance.strip() for s in scenarios), (
        "a scenario without provenance is a number chosen by hand"
    )


def test_the_reference_analysis_scenario_is_present(fake_experiment: ExperimentConfig) -> None:
    """The sample the reference analysis actually measured with anchors the smallest rung."""
    smallest = fake_experiment.library.n_obs_scenarios[0]
    assert smallest.n_obs == 14
    assert "Napier" in smallest.provenance


def test_a_scenario_without_provenance_is_refused(
    fake_experiment: ExperimentConfig, tmp_path: Path
) -> None:
    text = fake_experiment.path.read_text(encoding="utf-8").replace(
        "[[library.n_obs_scenarios]]\nn_obs = 14\nprovenance = ",
        "[[library.n_obs_scenarios]]\nn_obs = 14\nunlabelled = ",
        1,
    )
    broken = tmp_path / "broken.toml"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="provenance"):
        load_experiment(broken)


def test_the_budget_experiment_runs_against_the_fake_binding(repo_root: Path) -> None:
    """The 10³-versus-10⁴ comparison is measured on the fake binding, by decision."""
    budget = load_experiment(repo_root / "experiments" / "sp1-training-budget.toml")
    assert budget.campaign.binding == "fake"
    assert budget.training.n_simulations == (1000, 10000)
    assert len(budget.training.master_seeds) == 2
    assert budget.campaign.n_draws >= max(budget.training.n_simulations)


def test_the_sweep_experiment_runs_against_the_real_simulator(repo_root: Path) -> None:
    sweep = load_experiment(repo_root / "experiments" / "sp1-sweep.toml")
    assert sweep.campaign.binding == "sorcha"
    assert sweep.campaign.sweep_objects == (10, 100, 1000)
    assert sweep.campaign.sweep_repetitions >= 3
    assert sweep.library.n_objects == max(sweep.campaign.sweep_objects), (
        "the library is built at the largest size of the sweep, so its detected subset is "
        "large enough for the criterion to bite"
    )
