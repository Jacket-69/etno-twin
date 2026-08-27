"""Stage 1 — population parameters to survey-simulator inputs.

Boundary measured here: wall-clock of generation, bytes of the orbit and physical
parameter tables, and the number of objects.

The stage draws the population parameters from the prior when it is not given them, which
is what makes a run of this stage one draw of a campaign. Both the parameters and the
seed of the stream that produced them are written next to the artifacts, because a set of
(parameters, simulated observations) pairs is valid only for the prior its parameters came
from and nothing in the data itself reveals a mismatch.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from etno_twin.kernel import rng as seeds
from etno_twin.kernel.config import ExperimentConfig, load_experiment
from etno_twin.kernel.hashing import fingerprint
from etno_twin.kernel.manifest import Manifest, manifest_path
from etno_twin.kernel.measure import ByteLedger, Stopwatch, environment_snapshot
from etno_twin.kernel.population_model import sample_population
from etno_twin.kernel.schemas import ORBITS, PHYSICAL_PARAMETERS

STAGE = "population"

ORBITS_FILE = "orbits.csv"
PARAMETERS_FILE = "physical-parameters.csv"
THETA_FILE = "theta.json"


def draw_theta(config: ExperimentConfig, label: str) -> tuple[dict[str, float], int]:
    """Draw population parameters from the prior, on the stream derived for ``label``."""
    seed = seeds.derive_seed(config.master_seed, f"theta/{label}")
    stream = seeds.stream(config.master_seed, f"theta/{label}")
    theta = {
        component.name: component.sample(stream.random()) for component in config.prior.components
    }
    return theta, seed


def run(
    config: ExperimentConfig,
    outdir: Path,
    label: str,
    *,
    n_objects: int | None = None,
    theta: Mapping[str, float] | None = None,
) -> dict[str, Path]:
    """Generate one synthetic population and write it in the simulator's input schemas."""
    outdir.mkdir(parents=True, exist_ok=True)
    count = n_objects if n_objects is not None else config.population.n_objects

    if theta is None:
        parameters, theta_seed = draw_theta(config, label)
        theta_source = "prior-draw"
    else:
        parameters, theta_seed = dict(theta), -1
        theta_source = "given"

    population_seed = seeds.derive_seed(config.master_seed, f"population/{label}")
    stream = seeds.stream(config.master_seed, f"population/{label}")

    with Stopwatch("generate") as watch:
        objects = sample_population(
            config.population, parameters, count, stream, id_prefix=label.replace("/", "_")
        )
        orbits = ORBITS.write_rows(outdir / ORBITS_FILE, (obj.orbit_row() for obj in objects))
        physical = PHYSICAL_PARAMETERS.write_rows(
            outdir / PARAMETERS_FILE,
            (obj.parameter_row(config.population) for obj in objects),
        )

    theta_path = outdir / THETA_FILE
    theta_path.write_text(
        json.dumps(
            {
                "label": label,
                "parameters": parameters,
                "source": theta_source,
                "theta_seed": theta_seed,
                "population_seed": population_seed,
                "prior": config.prior.as_dict(),
                "prior_fingerprint": config.prior.fingerprint(),
                "n_objects": count,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ledger = ByteLedger()
    ledger.record("orbits", orbits)
    ledger.record("physical_parameters", physical)
    ledger.record("parameters", theta_path)

    Manifest(
        stage=STAGE,
        experiment=config.reference(),
        inputs=[fingerprint(config.path, "experiment_config")],
        outputs=[
            fingerprint(orbits, "orbits"),
            fingerprint(physical, "physical_parameters"),
            fingerprint(theta_path, "parameters"),
        ],
        parameters={
            "label": label,
            "n_objects": count,
            "theta": parameters,
            "theta_source": theta_source,
            "population_model": config.population.as_dict(),
        },
        prior=config.prior.as_dict(),
        seeds={"master": config.master_seed, "theta": theta_seed, "population": population_seed},
        schemas=[ORBITS.as_dict(), PHYSICAL_PARAMETERS.as_dict()],
        environment=environment_snapshot(),
        measurements={
            "boundary": "population -> simulator inputs",
            "n_objects": count,
            "generation": watch.as_dict(),
            "bytes": ledger.as_dict(),
            "bytes_per_object": ledger.total() / count if count else 0.0,
        },
    ).write(manifest_path(outdir, STAGE))

    return {"orbits": orbits, "physical_parameters": physical, "parameters": theta_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etno-twin-population", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--n-objects", type=int, default=None)
    parser.add_argument(
        "--theta",
        default=None,
        help="JSON object of population parameters; omitted means draw from the prior.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_experiment(args.config)
    theta: dict[str, Any] | None = json.loads(args.theta) if args.theta else None
    run(config, args.outdir, args.label, n_objects=args.n_objects, theta=theta)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
