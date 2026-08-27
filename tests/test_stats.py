"""The two estimators the spike reports numbers from."""

from __future__ import annotations

import pytest

from etno_twin.kernel.stats import (
    kish_effective_sample_size,
    neff_criterion_met,
    ols_line_fit,
)


def test_equal_weights_give_the_full_sample_size() -> None:
    assert kish_effective_sample_size([1.0] * 40) == pytest.approx(40.0)


def test_effective_sample_size_is_invariant_to_a_common_scale() -> None:
    weights = [0.3, 1.7, 4.0, 0.9]
    assert kish_effective_sample_size(weights) == pytest.approx(
        kish_effective_sample_size([w * 1000.0 for w in weights])
    )


def test_one_dominant_weight_collapses_the_effective_sample_size() -> None:
    weights = [1e6, *([1.0] * 99)]
    assert kish_effective_sample_size(weights) < 1.001


def test_zero_weights_do_not_count_towards_the_effective_sample_size() -> None:
    assert kish_effective_sample_size([1.0, 1.0, 0.0, 0.0]) == pytest.approx(2.0)


def test_all_weights_zero_gives_no_effective_sample() -> None:
    assert kish_effective_sample_size([0.0, 0.0]) == 0.0


def test_negative_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        kish_effective_sample_size([1.0, -1.0])


def test_the_published_criterion_is_four_times_the_observed_sample() -> None:
    assert neff_criterion_met(n_eff=41.0, n_obs=10)
    assert not neff_criterion_met(n_eff=40.0, n_obs=10)


def test_the_line_fit_recovers_a_known_cost_model() -> None:
    fixed, marginal = 12.5, 1.4
    sizes = [10.0, 100.0, 1000.0]
    fit = ols_line_fit(sizes, [fixed + marginal * n for n in sizes])
    assert fit.intercept == pytest.approx(fixed)
    assert fit.slope == pytest.approx(marginal)
    assert fit.r_squared == pytest.approx(1.0)


def test_a_single_population_size_cannot_separate_fixed_from_marginal() -> None:
    """The defect the sweep exists to remove, stated as a test."""
    with pytest.raises(ValueError, match="identical"):
        ols_line_fit([10.0, 10.0], [28.9, 29.1])
