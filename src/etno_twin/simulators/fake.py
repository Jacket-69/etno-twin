"""A fake survey simulator: the selection function without the astronomy.

**What this is.** A stand-in that honours the survey-simulator port so the whole chain
can be exercised on a machine with no Fortran toolchain, no network and none of the
780 MB of ephemeris kernels — which is what lets continuous integration run the same
directed acyclic graph the workstation runs.

**What this is not.** An astronomical model. Sky positions are not computed: an object's
presence in a field is drawn, not derived from where the object actually is, and the
geocentric distance is approximated by the heliocentric one. Any stage that consumes
detections from both bindings may therefore read only the columns the port declares as
meaningful in both — `schemas.DETECTIONS.cross_port_columns`.

**What it does reproduce**, because the pipeline's correctness depends on it:

* Detection depends on the orbit and the absolute magnitude, never on the population
  parameters directly. Population parameters decide which objects exist; the survey
  decides which of them it sees.
* The same three filters the real simulator applies, read from the *same* configuration
  file: a saturation limit, a fading function of magnitude against the visit's depth, and
  a linking filter requiring several tracklets inside a time window.
* Stochasticity seeded from the operating system, with the seed recorded in the log and
  recoverable by the same parser the real binding uses.

Orbital motion is a two-body Kepler propagation, which is enough for heliocentric
distance to vary across a year and therefore for the fading function to have something to
bite on.
"""

from __future__ import annotations

import argparse
import configparser
import csv
import logging
import math
import os
import random
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from etno_twin.kernel.schemas import DETECTIONS, ORBITS, PHYSICAL_PARAMETERS, POINTING_TABLE

GAUSSIAN_GRAVITATIONAL_CONSTANT = 0.01720209895
"""Gauss's constant, in radians per day; mean motion is this over ``a**1.5``."""

AU_KM = 1.495978707e8
SECONDS_PER_DAY = 86400.0
_KEPLER_TOLERANCE = 1e-10
_KEPLER_MAX_ITERATIONS = 64

FAKE_PHASE_MARKERS: tuple[tuple[str, str], ...] = (
    ("startup", "Fake survey simulator start"),
    ("pointing_table", "Reading pointing table..."),
    ("propagation", "Propagating orbits..."),
    ("selection", "Applying selection function..."),
    ("linking", "Applying linking filter..."),
    ("shutdown", "Fake survey simulator completed."),
)

LOG_FORMAT = "%(asctime)s %(name)-12s %(levelname)-8s %(message)s "
"""Deliberately the layout the real binding emits, so one parser reads both logs."""


@dataclass(frozen=True)
class SurveyConfig:
    """The subset of the shared configuration file this binding understands.

    Read from the *same* file the real simulator reads. A filter that both bindings apply
    is a filter neither can quietly redefine.
    """

    observing_filters: tuple[str, ...]
    bright_limit: float
    fading_function_width: float
    fading_function_peak_efficiency: float
    ssp_detection_efficiency: float
    ssp_number_observations: int
    ssp_number_tracklets: int
    ssp_track_window_days: float
    night_start_utc_hours: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "observing_filters": list(self.observing_filters),
            "bright_limit": self.bright_limit,
            "fading_function_width": self.fading_function_width,
            "fading_function_peak_efficiency": self.fading_function_peak_efficiency,
            "ssp_detection_efficiency": self.ssp_detection_efficiency,
            "ssp_number_observations": self.ssp_number_observations,
            "ssp_number_tracklets": self.ssp_number_tracklets,
            "ssp_track_window_days": self.ssp_track_window_days,
        }


def read_survey_config(path: Path) -> SurveyConfig:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    return SurveyConfig(
        observing_filters=tuple(
            token.strip() for token in parser["FILTERS"]["observing_filters"].split(",")
        ),
        bright_limit=parser.getfloat("SATURATION", "bright_limit", fallback=-99.0),
        fading_function_width=parser.getfloat("FADINGFUNCTION", "fading_function_width"),
        fading_function_peak_efficiency=parser.getfloat(
            "FADINGFUNCTION", "fading_function_peak_efficiency"
        ),
        ssp_detection_efficiency=parser.getfloat("LINKINGFILTER", "SSP_detection_efficiency"),
        ssp_number_observations=parser.getint("LINKINGFILTER", "SSP_number_observations"),
        ssp_number_tracklets=parser.getint("LINKINGFILTER", "SSP_number_tracklets"),
        ssp_track_window_days=parser.getfloat("LINKINGFILTER", "SSP_track_window"),
        night_start_utc_hours=parser.getfloat("LINKINGFILTER", "SSP_night_start_utc"),
    )


def solve_kepler(mean_anomaly_rad: float, eccentricity: float) -> float:
    """Eccentric anomaly from the mean anomaly, by Newton iteration."""
    eccentric = mean_anomaly_rad if eccentricity < 0.8 else math.pi
    for _ in range(_KEPLER_MAX_ITERATIONS):
        residual = eccentric - eccentricity * math.sin(eccentric) - mean_anomaly_rad
        derivative = 1.0 - eccentricity * math.cos(eccentric)
        step = residual / derivative
        eccentric -= step
        if abs(step) < _KEPLER_TOLERANCE:
            break
    return eccentric


@dataclass(frozen=True)
class OrbitState:
    """Heliocentric distance and its rate, at one instant."""

    distance_au: float
    range_rate_km_s: float


def propagate(orbit: dict[str, str], mjd: float) -> OrbitState:
    """Two-body propagation of one orbit to one epoch."""
    semi_major_axis = float(orbit["a"])
    eccentricity = float(orbit["e"])
    epoch = float(orbit["epochMJD_TDB"])
    mean_motion = GAUSSIAN_GRAVITATIONAL_CONSTANT / semi_major_axis**1.5
    mean_anomaly = math.radians(float(orbit["ma"])) + mean_motion * (mjd - epoch)
    mean_anomaly = math.fmod(mean_anomaly, 2.0 * math.pi)
    eccentric = solve_kepler(mean_anomaly, eccentricity)
    distance = semi_major_axis * (1.0 - eccentricity * math.cos(eccentric))
    rate_au_day = (semi_major_axis * eccentricity * math.sin(eccentric) * mean_motion) / (
        1.0 - eccentricity * math.cos(eccentric)
    )
    return OrbitState(
        distance_au=distance,
        range_rate_km_s=rate_au_day * AU_KM / SECONDS_PER_DAY,
    )


def apparent_magnitude(absolute_magnitude_r: float, distance_au: float) -> float:
    """Apparent magnitude in r, in the opposition approximation.

    ``m = H + 5·log10(r·Δ)`` with the geocentric distance ``Δ`` taken equal to the
    heliocentric distance. For objects tens of astronomical units away the error is a few
    per cent of a magnitude; for a binding whose sky positions are drawn rather than
    computed, modelling it more carefully would be false precision.
    """
    return absolute_magnitude_r + 5.0 * math.log10(max(distance_au, 1e-6) ** 2)


def fading_efficiency(magnitude: float, five_sigma_depth: float, config: SurveyConfig) -> float:
    """Detection probability of one observation, after Chesley and Vereš (2017)."""
    exponent = (magnitude - five_sigma_depth) / config.fading_function_width
    if exponent > 500.0:
        return 0.0
    return config.fading_function_peak_efficiency / (1.0 + math.exp(exponent))


def night_index(mjd: float, config: SurveyConfig) -> int:
    return math.floor(mjd - config.night_start_utc_hours / 24.0)


def _colour_offset(parameters: dict[str, str], band: str) -> float:
    if band == "r":
        return 0.0
    return float(parameters.get(f"{band}-r", 0.0))


@dataclass
class _Candidate:
    visit: dict[str, str]
    state: OrbitState
    magnitude: float


def simulate(
    orbits: Sequence[dict[str, str]],
    parameters: dict[str, dict[str, str]],
    visits: Sequence[dict[str, str]],
    config: SurveyConfig,
    field_probability: float,
    rng: random.Random,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """Run the fake survey over a population and return the detections of linked objects."""
    nights: dict[int, list[dict[str, str]]] = {}
    for visit in visits:
        if visit["filter"] not in config.observing_filters:
            continue
        nights.setdefault(night_index(float(visit["observationStartMJD_TAI"]), config), []).append(
            visit
        )

    # Three passes over the whole population rather than one pass per object. The real
    # simulator is structured the same way — propagate, filter, link — and running the
    # passes separately is what lets the log say where a run's time actually went, with
    # the same phase profiler reading both bindings' logs.
    logger.info("Propagating orbits...")
    candidates: dict[str, list[_Candidate]] = {}
    for orbit in orbits:
        obj_id = orbit["ObjID"]
        physical = parameters[obj_id]
        absolute_magnitude = float(physical["H_r"])
        observable: list[_Candidate] = []
        for visits_of_night in nights.values():
            if rng.random() >= field_probability:
                continue
            for visit in visits_of_night:
                state = propagate(orbit, float(visit["observationStartMJD_TAI"]))
                magnitude = apparent_magnitude(absolute_magnitude, state.distance_au)
                magnitude += _colour_offset(physical, visit["filter"])
                observable.append(_Candidate(visit=visit, state=state, magnitude=magnitude))
        candidates[obj_id] = observable

    logger.info("Applying selection function...")
    detected = {
        obj_id: _detect(observable, config, rng) for obj_id, observable in candidates.items()
    }

    logger.info("Applying linking filter...")
    rows: list[dict[str, Any]] = []
    for obj_id, observations in detected.items():
        if not _links(observations, config, rng):
            continue
        rows.extend(_detection_row(obj_id, candidate) for candidate in observations)
    return rows


def _detect(
    candidates: Sequence[_Candidate], config: SurveyConfig, rng: random.Random
) -> list[_Candidate]:
    """Saturation limit and fading function, in the order the real simulator applies them."""
    detected: list[_Candidate] = []
    for candidate in candidates:
        if candidate.magnitude < config.bright_limit:
            continue
        depth = float(candidate.visit["fieldFiveSigmaDepth_mag"])
        if rng.random() < fading_efficiency(candidate.magnitude, depth, config):
            detected.append(candidate)
    return detected


def _links(detected: Sequence[_Candidate], config: SurveyConfig, rng: random.Random) -> bool:
    """Whether an object's detections form enough tracklets to be linked into a track."""
    by_night: dict[int, list[_Candidate]] = {}
    for candidate in detected:
        moment = float(candidate.visit["observationStartMJD_TAI"])
        by_night.setdefault(night_index(moment, config), []).append(candidate)
    tracklet_nights = [
        night
        for night, members in by_night.items()
        if len(members) >= config.ssp_number_observations
    ]
    if not _linked(sorted(tracklet_nights), config):
        return False
    return rng.random() < config.ssp_detection_efficiency


def _linked(tracklet_nights: Sequence[int], config: SurveyConfig) -> bool:
    """Whether enough tracklets fall inside one tracking window."""
    required = config.ssp_number_tracklets
    if len(tracklet_nights) < required:
        return False
    for start in range(len(tracklet_nights) - required + 1):
        window = tracklet_nights[start + required - 1] - tracklet_nights[start]
        if window <= config.ssp_track_window_days:
            return True
    return False


def _detection_row(obj_id: str, candidate: _Candidate) -> dict[str, Any]:
    visit = candidate.visit
    distance_km = candidate.state.distance_au * AU_KM
    return {
        "ObjID": obj_id,
        "fieldMJD_TAI": float(visit["observationStartMJD_TAI"]),
        "fieldRA_deg": float(visit["fieldRA_deg"]),
        "fieldDec_deg": float(visit["fieldDec_deg"]),
        # Sky positions are not modelled by this binding; the field centre is written so
        # the schema is honoured. See `cross_port_columns`.
        "RA_deg": float(visit["fieldRA_deg"]),
        "Dec_deg": float(visit["fieldDec_deg"]),
        "astrometricSigma_deg": 0.0,
        "optFilter": visit["filter"],
        "trailedSourceMag": candidate.magnitude,
        "trailedSourceMagSigma": 0.0,
        "fiveSigmaDepth_mag": float(visit["fieldFiveSigmaDepth_mag"]),
        "phase_deg": 0.0,
        "Range_LTC_km": distance_km,
        "RangeRate_LTC_km_s": candidate.state.range_rate_km_s,
        "Obj_Sun_LTC_km": distance_km,
    }


def _read_indexed(path: Path, schema: Any, key: str = "ObjID") -> dict[str, dict[str, str]]:
    return {row[key]: row for row in schema.read_rows(path)}


def _configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fake.survey")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def build_parser() -> argparse.ArgumentParser:
    """The same flags the real binding is driven with, so one adapter builds both."""
    parser = argparse.ArgumentParser(
        prog="etno-twin-fake-simulator",
        description="Fake survey simulator honouring the etno-twin simulator port.",
    )
    parser.add_argument("-c", "--config", required=True, type=Path)
    parser.add_argument("--ob", "--orbits", dest="orbits", required=True, type=Path)
    parser.add_argument(
        "-p", "--physical-parameters", dest="physical_parameters", required=True, type=Path
    )
    parser.add_argument("--pd", "--pointing-table", dest="pointing_table", required=True, type=Path)
    parser.add_argument("-o", "--outfile", dest="outdir", required=True, type=Path)
    parser.add_argument("-t", "--stem", default="detections")
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("--field-probability", type=float, default=0.05)
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Pin the seed. Left unset in every campaign invocation: like the real "
            "simulator, this binding draws from the operating system and records what it "
            "drew. Pinning exists for tests, never for a measurement."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)
    logger = _configure_logging(args.outdir / f"{args.stem}.log")
    logger.info("Fake survey simulator start")

    seed = args.seed if args.seed is not None else int.from_bytes(os.urandom(4), "big")
    logger.info("the base rng seed is %d", seed)
    rng = random.Random(seed)

    config = read_survey_config(args.config)
    logger.info("Reading pointing table...")
    visits = POINTING_TABLE.read_rows(args.pointing_table)
    orbits = ORBITS.read_rows(args.orbits)
    parameters = _read_indexed(args.physical_parameters, PHYSICAL_PARAMETERS)

    rows = simulate(
        orbits=orbits,
        parameters=parameters,
        visits=visits,
        config=config,
        field_probability=args.field_probability,
        rng=rng,
        logger=logger,
    )
    output = args.outdir / f"{args.stem}.csv"
    if output.exists() and not args.force:
        logger.error("refusing to overwrite %s without --force", output)
        return 1
    DETECTIONS.write_rows(output, rows)
    logger.info("wrote %d detections of %d objects", len(rows), len({row["ObjID"] for row in rows}))
    logger.info("Fake survey simulator completed.")
    return 0


def build_argv(
    *,
    config_ini: Path,
    orbits: Path,
    physical_parameters: Path,
    pointing_table: Path,
    run_dir: Path,
    stem: str,
    field_probability: float,
    executable: Sequence[str] = (),
) -> list[str]:
    """Command line for one fake run, as a child process.

    A fake that ran in-process would validate nothing about the architecture: the seam
    between a stage and a simulator has to cross a process and a file boundary, or the
    experiment cannot discriminate between the options ADR-0001 is choosing among. So the
    fake is spawned exactly like the real one.
    """
    head = list(executable) if executable else [sys.executable, "-m", "etno_twin.simulators.fake"]
    return [
        *head,
        "-c",
        str(config_ini),
        "--ob",
        str(orbits),
        "-p",
        str(physical_parameters),
        "--pd",
        str(pointing_table),
        "-o",
        str(run_dir),
        "-t",
        stem,
        "-f",
        "--field-probability",
        repr(field_probability),
    ]


def write_pointing_table(path: Path, visits: Iterable[dict[str, Any]]) -> Path:
    """Helper for building fixtures; the schema is the one sorcha's own query projects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(POINTING_TABLE.columns))
        writer.writeheader()
        for visit in visits:
            writer.writerow(visit)
    return path


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
