"""The toy parametric population model.

**This is a placeholder with a job, not science.** The tracer bullet needs a generator
that turns population parameters into objects a survey simulator can consume, and the
real population model belongs to a later phase. What this one has to get right is the
*structure* the pipeline depends on:

* Parameters control **which objects exist**, never whether a given object is detected —
  detection depends on the orbit and the absolute magnitude. That asymmetry is the whole
  premise of the reweighted-library measurement.
* Every density is analytic and normalised, so importance weights between two parameter
  values are exact rather than estimated.
* The support is parameter-dependent: the inclination distribution is truncated at a
  multiple of its own width. That is what makes "fraction of proposals rejected as out
  of range" a real measurement instead of a column of zeros.

Two parameters, both standard in the trans-Neptunian literature:

``size_slope_alpha``
    Slope of the differential absolute-magnitude distribution,
    ``p(H) ∝ 10^(α·H)`` on ``[H_min, H_max]``.

``inclination_width_deg``
    Width of the inclination distribution, ``p(i) ∝ sin(i)·exp(-i²/2σ²)`` on
    ``[0, k·σ]`` — the functional form introduced by Brown (2001), truncated at ``k``
    widths.

The remaining orbital elements are drawn from parameter-independent ranges, so they
cancel exactly in any weight ratio and never have to be modelled.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from etno_twin.kernel.config import PopulationConfig
from etno_twin.kernel.schemas import ORBITS, PHYSICAL_PARAMETERS

_INCLINATION_GRID = 1024
_MAX_REJECTION_TRIES = 10_000


@dataclass(frozen=True)
class SyntheticObject:
    """One object of a synthetic population, in the elements the simulator reads."""

    obj_id: str
    semi_major_axis_au: float
    eccentricity: float
    inclination_deg: float
    node_deg: float
    arg_peri_deg: float
    mean_anomaly_deg: float
    epoch_mjd_tdb: float
    absolute_magnitude_r: float

    @property
    def perihelion_au(self) -> float:
        return self.semi_major_axis_au * (1.0 - self.eccentricity)

    def orbit_row(self) -> dict[str, Any]:
        return {
            "ObjID": self.obj_id,
            "FORMAT": "KEP",
            "a": self.semi_major_axis_au,
            "e": self.eccentricity,
            "inc": self.inclination_deg,
            "node": self.node_deg,
            "argPeri": self.arg_peri_deg,
            "ma": self.mean_anomaly_deg,
            "epochMJD_TDB": self.epoch_mjd_tdb,
        }

    def parameter_row(self, config: PopulationConfig) -> dict[str, Any]:
        row: dict[str, Any] = {
            "ObjID": self.obj_id,
            "H_r": self.absolute_magnitude_r,
            "GS": config.phase_slope_g,
        }
        row.update(config.colours)
        return row


def _magnitude_density(h: float, alpha: float, h_low: float, h_high: float) -> float:
    """Normalised ``p(H) ∝ 10^(α(H - H_low))`` on ``[H_low, H_high]``."""
    if not h_low <= h <= h_high:
        return 0.0
    span = h_high - h_low
    if alpha == 0.0:
        return 1.0 / span
    ln10 = math.log(10.0)
    normalisation = (math.pow(10.0, alpha * span) - 1.0) / (alpha * ln10)
    return math.pow(10.0, alpha * (h - h_low)) / normalisation


def _sample_magnitude(rng: random.Random, alpha: float, h_low: float, h_high: float) -> float:
    """Inverse-CDF draw from the magnitude distribution."""
    span = h_high - h_low
    if alpha == 0.0:
        return rng.uniform(h_low, h_high)
    total = math.pow(10.0, alpha * span) - 1.0
    return h_low + math.log10(1.0 + rng.random() * total) / alpha


def _inclination_shape(inclination_deg: float, width_deg: float) -> float:
    radians = math.radians(inclination_deg)
    return math.sin(radians) * math.exp(-0.5 * (inclination_deg / width_deg) ** 2)


def _inclination_normalisation(width_deg: float, truncation_scale: float) -> tuple[float, float]:
    """Integral of the unnormalised shape and its maximum, by grid quadrature.

    Returned together because the sampler needs the maximum for rejection sampling and
    the density needs the integral; computing them in one pass keeps the two consistent.
    """
    upper = truncation_scale * width_deg
    step = upper / _INCLINATION_GRID
    integral = 0.0
    peak = 0.0
    previous = _inclination_shape(0.0, width_deg)
    for index in range(1, _INCLINATION_GRID + 1):
        current = _inclination_shape(index * step, width_deg)
        integral += 0.5 * (previous + current) * step
        peak = max(peak, current)
        previous = current
    return integral, peak


def _inclination_density(
    inclination_deg: float, width_deg: float, truncation_scale: float
) -> float:
    upper = truncation_scale * width_deg
    if not 0.0 <= inclination_deg <= upper:
        return 0.0
    integral, _ = _inclination_normalisation(width_deg, truncation_scale)
    if integral <= 0.0:
        return 0.0
    return _inclination_shape(inclination_deg, width_deg) / integral


def _sample_inclination(rng: random.Random, width_deg: float, truncation_scale: float) -> float:
    upper = truncation_scale * width_deg
    _, peak = _inclination_normalisation(width_deg, truncation_scale)
    for _ in range(_MAX_REJECTION_TRIES):
        candidate = rng.uniform(0.0, upper)
        if rng.random() * peak <= _inclination_shape(candidate, width_deg):
            return candidate
    raise RuntimeError("inclination rejection sampling failed to converge")


def object_density(
    config: PopulationConfig, theta: Mapping[str, float], obj: SyntheticObject
) -> float:
    """Joint density of the parameter-dependent object properties.

    Only the magnitude and the inclination depend on the parameters, so only those two
    factors appear. The semi-major axis, perihelion, angles and epoch are drawn from
    fixed ranges and cancel identically in any ratio of two densities — which is why the
    importance weights below are exact and not an approximation.
    """
    h_low, h_high = config.absolute_magnitude_r
    magnitude = _magnitude_density(
        obj.absolute_magnitude_r, theta["size_slope_alpha"], h_low, h_high
    )
    inclination = _inclination_density(
        obj.inclination_deg,
        theta["inclination_width_deg"],
        config.inclination_truncation_scale,
    )
    return magnitude * inclination


def sample_population(
    config: PopulationConfig,
    theta: Mapping[str, float],
    n_objects: int,
    rng: random.Random,
    id_prefix: str = "toy",
) -> list[SyntheticObject]:
    """Draw ``n_objects`` from the model at the given parameters."""
    a_low, a_high = config.semi_major_axis_au
    q_low, q_high = config.perihelion_au
    h_low, h_high = config.absolute_magnitude_r
    alpha = theta["size_slope_alpha"]
    width = theta["inclination_width_deg"]

    objects: list[SyntheticObject] = []
    for index in range(n_objects):
        semi_major_axis = rng.uniform(a_low, a_high)
        perihelion = rng.uniform(q_low, min(q_high, semi_major_axis * 0.999))
        objects.append(
            SyntheticObject(
                obj_id=f"{id_prefix}_{index:06d}",
                semi_major_axis_au=semi_major_axis,
                eccentricity=1.0 - perihelion / semi_major_axis,
                inclination_deg=_sample_inclination(
                    rng, width, config.inclination_truncation_scale
                ),
                node_deg=rng.uniform(0.0, 360.0),
                arg_peri_deg=rng.uniform(0.0, 360.0),
                mean_anomaly_deg=rng.uniform(0.0, 360.0),
                epoch_mjd_tdb=config.epoch_mjd_tdb,
                absolute_magnitude_r=_sample_magnitude(rng, alpha, h_low, h_high),
            )
        )
    return objects


def read_population(orbits_path: Path, parameters_path: Path) -> list[SyntheticObject]:
    """Rebuild a population from the two artifacts the population stage wrote.

    Reading the population back from files rather than regenerating it is the point: the
    stage that reweights a library never re-runs the stage that produced it, and the only
    thing they share is a pair of tables with declared schemas.
    """
    magnitudes = {
        row["ObjID"]: float(row["H_r"]) for row in PHYSICAL_PARAMETERS.read_rows(parameters_path)
    }
    objects: list[SyntheticObject] = []
    for row in ORBITS.read_rows(orbits_path):
        obj_id = row["ObjID"]
        objects.append(
            SyntheticObject(
                obj_id=obj_id,
                semi_major_axis_au=float(row["a"]),
                eccentricity=float(row["e"]),
                inclination_deg=float(row["inc"]),
                node_deg=float(row["node"]),
                arg_peri_deg=float(row["argPeri"]),
                mean_anomaly_deg=float(row["ma"]),
                epoch_mjd_tdb=float(row["epochMJD_TDB"]),
                absolute_magnitude_r=magnitudes[obj_id],
            )
        )
    return objects


@dataclass(frozen=True)
class WeightSet:
    """Importance weights of a library under a target set of parameters."""

    weights: tuple[float, ...]
    n_rejected: int
    """Library members outside the target's support — the truncated inclination tail."""

    @property
    def rejected_fraction(self) -> float:
        return self.n_rejected / len(self.weights) if self.weights else 0.0


def importance_weights(
    config: PopulationConfig,
    objects: Sequence[SyntheticObject],
    target_theta: Mapping[str, float],
    reference_theta: Mapping[str, float],
) -> WeightSet:
    """``w_i = p_target(z_i) / p_reference(z_i)`` for every object of a library.

    An object the target's support excludes gets weight zero and is counted as rejected:
    the model at those parameters says the object does not exist, so no amount of
    reweighting can make the library speak for it. Weights are left unnormalised, since
    Kish's effective sample size is invariant to a common scale factor.
    """
    weights: list[float] = []
    rejected = 0
    for obj in objects:
        reference_density = object_density(config, reference_theta, obj)
        if reference_density <= 0.0:
            raise ValueError(
                f"object {obj.obj_id} has zero density under the library's own parameters; "
                "the library was not drawn from the reference distribution it declares"
            )
        target_density = object_density(config, target_theta, obj)
        if target_density <= 0.0:
            rejected += 1
            weights.append(0.0)
            continue
        weights.append(target_density / reference_density)
    return WeightSet(weights=tuple(weights), n_rejected=rejected)
