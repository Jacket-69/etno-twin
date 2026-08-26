"""The experiment configuration file, and the typed view of it the stages read.

One file is the root of the manifest: it is what "one command" points at, it is hashed
into every stage's manifest, and nothing that decides the shape of a result is allowed to
live anywhere else. The ladders in particular — the sweep over population size and the
ladder of parameter distances for the reweighted library — are configuration, not
constants in code, because their values are the argument of the measurement.

TOML, parsed with the standard library's ``tomllib``. The orchestrator reads the same
file through the same parser, so there is exactly one description of an experiment
rather than one for the pipeline and one for the workflow engine.

Relative paths resolve against the current working directory, which is the repository
root for every documented invocation.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from etno_twin.kernel.hashing import sha256_bytes


class ConfigError(ValueError):
    """The experiment configuration is missing something a stage needs."""


def _section(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"missing or malformed [{name}] section")
    return value


def _require(section: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in section:
        raise ConfigError(f"[{where}] is missing required key '{key}'")
    return section[key]


def _pair(section: Mapping[str, Any], key: str, where: str) -> tuple[float, float]:
    value = _require(section, key, where)
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"[{where}].{key} must be a two-element range")
    low, high = float(value[0]), float(value[1])
    if not low < high:
        raise ConfigError(f"[{where}].{key} must be increasing, got {value}")
    return low, high


@dataclass(frozen=True)
class PriorComponent:
    """One parameter of the population model, with the support it is drawn from."""

    name: str
    distribution: str
    low: float
    high: float

    @property
    def width(self) -> float:
        return self.high - self.low

    def sample(self, uniform_variate: float) -> float:
        if self.distribution != "uniform":
            raise ConfigError(f"prior '{self.name}': unsupported distribution")
        return self.low + uniform_variate * self.width

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high

    def as_dict(self) -> dict[str, Any]:
        return {"distribution": self.distribution, "low": self.low, "high": self.high}


@dataclass(frozen=True)
class PriorSpec:
    """The prior over population parameters.

    Recorded in full in every manifest that touches simulations. A stored set of
    (parameters, simulated observations) pairs is valid **only** for the prior its
    parameters were drawn from, and nothing in the data itself reveals a mismatch — so
    the training stage refuses to consume a dataset whose prior differs from the one it
    declares.
    """

    components: tuple[PriorComponent, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(component.name for component in self.components)

    def component(self, name: str) -> PriorComponent:
        for candidate in self.components:
            if candidate.name == name:
                return candidate
        raise ConfigError(f"no prior component named '{name}'")

    def as_dict(self) -> dict[str, Any]:
        return {component.name: component.as_dict() for component in self.components}

    def fingerprint(self) -> str:
        """Stable digest of the prior, for equality checks across stages."""
        parts = [
            f"{c.name}:{c.distribution}:{c.low!r}:{c.high!r}"
            for c in sorted(self.components, key=lambda item: item.name)
        ]
        return sha256_bytes("|".join(parts).encode())


@dataclass(frozen=True)
class PopulationConfig:
    """Ranges of the toy parametric population model.

    Deliberately a toy: it exists to give the pipeline something to carry, and the real
    population model arrives in a later phase. Every range is configuration so that no
    number about the population is buried in code.
    """

    model: str
    n_objects: int
    semi_major_axis_au: tuple[float, float]
    perihelion_au: tuple[float, float]
    absolute_magnitude_r: tuple[float, float]
    inclination_truncation_scale: float
    epoch_mjd_tdb: float
    phase_slope_g: float
    colours: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "n_objects": self.n_objects,
            "semi_major_axis_au": list(self.semi_major_axis_au),
            "perihelion_au": list(self.perihelion_au),
            "absolute_magnitude_r": list(self.absolute_magnitude_r),
            "inclination_truncation_scale": self.inclination_truncation_scale,
            "epoch_mjd_tdb": self.epoch_mjd_tdb,
            "phase_slope_g": self.phase_slope_g,
            "colours": dict(self.colours),
        }


@dataclass(frozen=True)
class SorchaBinding:
    """Where the sorcha binding finds its inputs."""

    config_ini: Path
    pointing_db: str
    ephemeris_cache: Path
    executable: str


@dataclass(frozen=True)
class FakeBinding:
    """Where the fake binding finds its inputs."""

    config_ini: Path
    pointing_table: Path
    field_probability: float


@dataclass(frozen=True)
class CampaignConfig:
    """How many populations get simulated, and how the timing runs are laid out."""

    binding: str
    n_draws: int
    sweep_objects: tuple[int, ...]
    sweep_repetitions: int
    warmup_runs: int
    sorcha: SorchaBinding
    fake: FakeBinding

    def as_dict(self) -> dict[str, Any]:
        return {
            "binding": self.binding,
            "n_draws": self.n_draws,
            "sweep_objects": list(self.sweep_objects),
            "sweep_repetitions": self.sweep_repetitions,
            "warmup_runs": self.warmup_runs,
        }


@dataclass(frozen=True)
class DatasetConfig:
    """How a detection catalogue is summarised into the vector the network sees."""

    magnitude_bins: tuple[float, ...]
    distance_bins_au: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "magnitude_bins": list(self.magnitude_bins),
            "distance_bins_au": list(self.distance_bins_au),
        }


@dataclass(frozen=True)
class TrainingConfig:
    """Simulation budgets, master seeds and calibration effort."""

    n_simulations: tuple[int, ...]
    master_seeds: tuple[int, ...]
    sbc_evaluations: int
    sbc_posterior_samples: int
    max_epochs: int
    density_estimator: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_simulations": list(self.n_simulations),
            "master_seeds": list(self.master_seeds),
            "sbc_evaluations": self.sbc_evaluations,
            "sbc_posterior_samples": self.sbc_posterior_samples,
            "max_epochs": self.max_epochs,
            "density_estimator": self.density_estimator,
        }


@dataclass(frozen=True)
class LibraryConfig:
    """The reweighted-library measurement: one library, a ladder of parameter distances.

    ``theta_ladder_scale`` is expressed in units of the prior width per component, so a
    rung of 0 is the library's own reference parameters and a rung of 1 is a full prior
    width away. Keeping the ladder here, rather than in code, is what lets the ladder be
    extended without touching a stage.
    """

    n_objects: int
    n_obs: int
    reference: dict[str, float]
    ladder_direction: dict[str, float]
    theta_ladder_scale: tuple[float, ...]
    neff_criterion_factor: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_objects": self.n_objects,
            "n_obs": self.n_obs,
            "reference": dict(self.reference),
            "ladder_direction": dict(self.ladder_direction),
            "theta_ladder_scale": list(self.theta_ladder_scale),
            "neff_criterion_factor": self.neff_criterion_factor,
        }


@dataclass(frozen=True)
class ExperimentConfig:
    """A whole experiment, and the digest that identifies it in every manifest."""

    path: Path
    sha256: str
    raw: dict[str, Any]
    name: str
    description: str
    master_seed: int
    outdir: Path
    population: PopulationConfig
    prior: PriorSpec
    campaign: CampaignConfig
    dataset: DatasetConfig
    training: TrainingConfig
    library: LibraryConfig

    def reference(self) -> dict[str, Any]:
        """The block every manifest carries to identify which experiment produced it."""
        return {
            "name": self.name,
            "config_path": str(self.path),
            "config_sha256": self.sha256,
            "master_seed": self.master_seed,
            "prior_fingerprint": self.prior.fingerprint(),
        }


def _resolve(value: str) -> Path:
    return Path(value).expanduser()


def load_experiment(path: Path) -> ExperimentConfig:
    """Read and validate an experiment configuration file."""
    payload = path.read_bytes()
    raw: dict[str, Any] = tomllib.loads(payload.decode("utf-8"))

    experiment = _section(raw, "experiment")
    population = _section(raw, "population")
    prior_raw = _section(raw, "prior")
    campaign = _section(raw, "campaign")
    dataset = _section(raw, "dataset")
    training = _section(raw, "training")
    library = _section(raw, "library")

    components: list[PriorComponent] = []
    for name, spec in prior_raw.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"[prior.{name}] must be a table")
        components.append(
            PriorComponent(
                name=name,
                distribution=str(_require(spec, "distribution", f"prior.{name}")),
                low=float(_require(spec, "low", f"prior.{name}")),
                high=float(_require(spec, "high", f"prior.{name}")),
            )
        )
    if not components:
        raise ConfigError("[prior] declares no parameters")
    prior = PriorSpec(components=tuple(sorted(components, key=lambda item: item.name)))

    sorcha_raw = _section(campaign, "sorcha")
    fake_raw = _section(campaign, "fake")

    config = ExperimentConfig(
        path=path.resolve(),
        sha256=sha256_bytes(payload),
        raw=raw,
        name=str(_require(experiment, "name", "experiment")),
        description=str(experiment.get("description", "")),
        master_seed=int(_require(experiment, "master_seed", "experiment")),
        outdir=_resolve(str(_require(experiment, "outdir", "experiment"))),
        population=PopulationConfig(
            model=str(_require(population, "model", "population")),
            n_objects=int(_require(population, "n_objects", "population")),
            semi_major_axis_au=_pair(population, "semi_major_axis_au", "population"),
            perihelion_au=_pair(population, "perihelion_au", "population"),
            absolute_magnitude_r=_pair(population, "absolute_magnitude_r", "population"),
            inclination_truncation_scale=float(
                _require(population, "inclination_truncation_scale", "population")
            ),
            epoch_mjd_tdb=float(_require(population, "epoch_mjd_tdb", "population")),
            phase_slope_g=float(_require(population, "phase_slope_g", "population")),
            colours={k: float(v) for k, v in _section(population, "colours").items()},
        ),
        prior=prior,
        campaign=CampaignConfig(
            binding=str(_require(campaign, "binding", "campaign")),
            n_draws=int(_require(campaign, "n_draws", "campaign")),
            sweep_objects=tuple(int(n) for n in _require(campaign, "sweep_objects", "campaign")),
            sweep_repetitions=int(_require(campaign, "sweep_repetitions", "campaign")),
            warmup_runs=int(_require(campaign, "warmup_runs", "campaign")),
            sorcha=SorchaBinding(
                config_ini=_resolve(str(_require(sorcha_raw, "config_ini", "campaign.sorcha"))),
                pointing_db=str(_require(sorcha_raw, "pointing_db", "campaign.sorcha")),
                ephemeris_cache=_resolve(
                    str(_require(sorcha_raw, "ephemeris_cache", "campaign.sorcha"))
                ),
                executable=str(sorcha_raw.get("executable", "sorcha-run")),
            ),
            fake=FakeBinding(
                config_ini=_resolve(str(_require(fake_raw, "config_ini", "campaign.fake"))),
                pointing_table=_resolve(str(_require(fake_raw, "pointing_table", "campaign.fake"))),
                field_probability=float(_require(fake_raw, "field_probability", "campaign.fake")),
            ),
        ),
        dataset=DatasetConfig(
            magnitude_bins=tuple(float(v) for v in _require(dataset, "magnitude_bins", "dataset")),
            distance_bins_au=tuple(
                float(v) for v in _require(dataset, "distance_bins_au", "dataset")
            ),
        ),
        training=TrainingConfig(
            n_simulations=tuple(int(v) for v in _require(training, "n_simulations", "training")),
            master_seeds=tuple(int(v) for v in _require(training, "master_seeds", "training")),
            sbc_evaluations=int(_require(training, "sbc_evaluations", "training")),
            sbc_posterior_samples=int(training.get("sbc_posterior_samples", 100)),
            max_epochs=int(_require(training, "max_epochs", "training")),
            density_estimator=str(training.get("density_estimator", "maf")),
        ),
        library=LibraryConfig(
            n_objects=int(_require(library, "n_objects", "library")),
            n_obs=int(_require(library, "n_obs", "library")),
            reference={k: float(v) for k, v in _section(library, "reference").items()},
            ladder_direction={
                k: float(v) for k, v in _section(library, "ladder_direction").items()
            },
            theta_ladder_scale=tuple(
                float(v) for v in _require(library, "theta_ladder_scale", "library")
            ),
            neff_criterion_factor=float(library.get("neff_criterion_factor", 4.0)),
        ),
    )
    _validate_cross_section(config)
    return config


def _validate_cross_section(config: ExperimentConfig) -> None:
    """Checks that only make sense once every section has been read."""
    if config.campaign.binding not in {"fake", "sorcha"}:
        raise ConfigError(
            f"[campaign].binding must be 'fake' or 'sorcha', got {config.campaign.binding!r}"
        )
    names = set(config.prior.names)
    for label, mapping in (
        ("library.reference", config.library.reference),
        ("library.ladder_direction", config.library.ladder_direction),
    ):
        unknown = set(mapping) - names
        if unknown:
            raise ConfigError(f"[{label}] names parameters absent from [prior]: {sorted(unknown)}")
        missing = names - set(mapping)
        if missing:
            raise ConfigError(f"[{label}] omits prior parameters: {sorted(missing)}")
    for value_name, value in config.library.reference.items():
        if not config.prior.component(value_name).contains(value):
            raise ConfigError(f"[library.reference].{value_name} lies outside its prior support")


def theta_from_scale(config: ExperimentConfig, scale: float) -> dict[str, float]:
    """Parameters of one rung of the ladder, ``scale`` prior widths from the reference.

    The direction is normalised so that a scale of 1 moves one prior width in total, not
    one width per component: otherwise the ladder's step size would depend silently on
    how many parameters the model has.
    """
    direction = config.library.ladder_direction
    norm = sum(abs(v) for v in direction.values()) or 1.0
    theta: dict[str, float] = {}
    for name, reference_value in config.library.reference.items():
        component = config.prior.component(name)
        step = scale * (direction[name] / norm) * component.width
        theta[name] = reference_value + step
    return theta


def clamp_to_prior(prior: PriorSpec, theta: Mapping[str, float]) -> dict[str, float]:
    """Fold parameters back inside the prior support, reporting nothing.

    Used only where a ladder rung would step outside the prior; the stage that calls it
    records both the requested and the clamped values so the ladder stays legible.
    """
    clamped: dict[str, float] = {}
    for name, value in theta.items():
        component = prior.component(name)
        clamped[name] = min(max(value, component.low), component.high)
    return clamped


def theta_vector(prior: PriorSpec, theta: Mapping[str, float]) -> tuple[float, ...]:
    """Parameters in the canonical order the dataset and the network use."""
    return tuple(float(theta[name]) for name in prior.names)


def theta_columns(prior: PriorSpec) -> tuple[str, ...]:
    return tuple(f"theta_{name}" for name in prior.names)


def sequence_of_int(values: Sequence[Any]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)
