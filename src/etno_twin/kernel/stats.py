"""The two estimators the spike reports numbers from.

Both are written out here rather than pulled from a library so that the formula the
ADR cites is the formula the code runs, visible in one place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LineFit:
    """Ordinary least squares fit of ``y = intercept + slope * x``."""

    intercept: float
    slope: float
    r_squared: float
    n_points: int


def ols_line_fit(xs: Sequence[float], ys: Sequence[float]) -> LineFit:
    """Fit a straight line, which is how fixed cost is separated from marginal cost.

    The cost model of a simulator run is ``T(N) = T_fixed + N * t_marginal``: reading the
    pointing database, loading ephemeris kernels and importing the package are paid once
    per process, and only the per-object work scales. A single N cannot separate the two
    terms, which is the known defect of the extrapolation this spike replaces, so the
    sweep measures several N and the intercept is read off the fit.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have the same length")
    n = len(xs)
    if n < 2:
        raise ValueError("a line fit needs at least two points")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0.0:
        raise ValueError("all x values are identical; the fit is undetermined")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_total = sum((y - mean_y) ** 2 for y in ys)
    ss_residual = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    r_squared = 1.0 if ss_total == 0.0 else 1.0 - ss_residual / ss_total
    return LineFit(intercept=intercept, slope=slope, r_squared=r_squared, n_points=n)


def kish_effective_sample_size(weights: Sequence[float]) -> float:
    """Effective sample size of a weighted sample, by **Kish's formula**.

        N_eff = (Σ w_i)² / Σ w_i²

    This is the quantity the reweighted-library measurement reports, and it is stated
    explicitly because "effective sample size" names several different estimators in the
    literature. It equals the sample size when all weights are equal and collapses
    towards one as a single weight comes to dominate.

    The published criterion the spike reports against is ``N_eff > 4 * N_obs``
    (Farr 2019, arXiv:1904.10879, after equation 12): below it, a reweighted library is
    no longer a trustworthy stand-in for simulating that parameter value directly.
    """
    if not weights:
        return 0.0
    if any(w < 0.0 for w in weights):
        raise ValueError("importance weights must be non-negative")
    total = sum(weights)
    if total == 0.0:
        return 0.0
    return total**2 / sum(w * w for w in weights)


def neff_criterion_met(n_eff: float, n_obs: int, factor: float = 4.0) -> bool:
    """Whether ``N_eff`` clears the Farr 2019 threshold for a given observed sample."""
    return n_eff > factor * n_obs
