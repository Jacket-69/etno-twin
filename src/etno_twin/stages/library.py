"""Stage 5 — is a reweighted library a valid substitute for simulating?

The cheapest measurement of the whole spike and the one with the largest consequence.
Whether an object is detected depends on its orbit and its absolute magnitude, not on the
population parameters; the parameters only decide *which objects exist*. So one could pay
the survey simulator once, over a large library drawn from a broad reference
distribution, and compose the observations for any other parameter value by reweighting
that library — collapsing the cost from draws times population to library size.

The idea is not new. A simulation bank built once and importance-sampled from is a working
part of at least one published neural-posterior-estimation pipeline. What is missing from
that genealogy is a **quantitative criterion for when the substitution stops being
valid**, and supplying one is where this thesis has something of its own to say.

The criterion reported here is imported from hierarchical inference, where it is
established, and applied to this use, where it has not been:

    N_eff > 4 · N_obs        (Farr 2019, arXiv:1904.10879, after equation 12)

with ``N_eff`` Kish's effective sample size, ``(Σw)² / Σw²`` — stated explicitly in
`etno_twin.kernel.stats` and again here, because "effective sample size" names several
different estimators in the literature and the ADR will cite this one.

**``N_obs`` is not a single number here.** The threshold moves with the size of the
observed catalogue the inference would be applied to, and fixing one value would turn a
published criterion into an arbitrary verdict. The effective sample size is reported raw,
and the criterion is evaluated against every catalogue size the configuration declares —
each with its provenance — so the reader can see where the answer changes rather than
being handed one.

What the stage does: take one library, walk a ladder of parameter values at increasing
distance from the library's reference, and record for each rung the effective sample
size, the fraction of the library the target parameters exclude outright, and the
wall-clock saved against simulating that rung from scratch.

The consequence for the architecture is direct. If the effective sample size collapses
before the parameters reach the edge of the prior, the campaign stays one monolithic
stage. If it holds, the campaign splits into library-build and composition, with an
artifact boundary between them.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from etno_twin.kernel.config import (
    ExperimentConfig,
    clamp_to_prior,
    load_experiment,
    theta_from_scale,
)
from etno_twin.kernel.hashing import fingerprint
from etno_twin.kernel.manifest import Manifest, manifest_path, read_manifest
from etno_twin.kernel.measure import ByteLedger, Stopwatch, environment_snapshot
from etno_twin.kernel.population_model import importance_weights, read_population
from etno_twin.kernel.schemas import DATASET_PAIRS, DETECTIONS
from etno_twin.kernel.stats import kish_effective_sample_size, neff_criterion_met
from etno_twin.kernel.summary import summary_columns, weighted_summary

STAGE = "library"
LADDER_FILE = "ladder.json"
COMPOSED_FILE = "composed-x.csv"


def _reference_wall_clock(campaign_manifest: Path) -> float:
    """Wall-clock of the run that built the library, from its own manifest.

    This is the number a composed rung is compared against: simulating a population of
    this size costs that, composing one by reweighting costs what the stopwatch below
    reports. Reading it from the manifest rather than re-running is deliberate — the
    comparison must not itself pay for a simulation.
    """
    payload = read_manifest(campaign_manifest)
    return float(payload["measurements"]["process"]["wall_seconds"])


def _criterion_table(config: ExperimentConfig, n_eff: float) -> list[dict[str, Any]]:
    """Whether the criterion holds, for every declared size of observed catalogue.

    The threshold is ``4 · N_obs``, so the verdict moves with the sample the inference
    would be applied to. Fixing one ``N_obs`` would turn a published criterion into an
    arbitrary answer — large enough and a library that serves the catalogue which actually
    exists is declared unusable. Reporting the whole table, next to the raw effective
    sample size, leaves the reader able to see exactly where the answer changes.
    """
    factor = config.library.neff_criterion_factor
    return [
        {
            "n_obs": scenario.n_obs,
            "provenance": scenario.provenance,
            "threshold": factor * scenario.n_obs,
            "met": neff_criterion_met(n_eff, scenario.n_obs, factor),
        }
        for scenario in config.library.n_obs_scenarios
    ]


def run(
    config: ExperimentConfig,
    library_population_dir: Path,
    library_campaign_dir: Path,
    outdir: Path,
    *,
    stem: str = "detections",
) -> dict[str, Path]:
    """Walk the ladder and record the viability of reweighting at each rung."""
    outdir.mkdir(parents=True, exist_ok=True)
    objects = read_population(
        library_population_dir / "orbits.csv",
        library_population_dir / "physical-parameters.csv",
    )
    detections_file = library_campaign_dir / f"{stem}.csv"
    detections = DETECTIONS.read_rows(detections_file)
    detected_ids = {row["ObjID"] for row in detections}

    campaign_manifest = manifest_path(library_campaign_dir, "campaign")
    simulation_seconds = _reference_wall_clock(campaign_manifest)

    reference_theta = dict(config.library.reference)
    factor = config.library.neff_criterion_factor

    schema = DATASET_PAIRS.extended_with(
        [
            "scale",
            "n_eff_detected",
            *[f"theta_{name}" for name in config.prior.names],
            *summary_columns(config),
        ]
    )
    rungs: list[dict[str, Any]] = []
    composed_rows: list[dict[str, Any]] = []

    for scale in config.library.theta_ladder_scale:
        requested = theta_from_scale(config, scale)
        target = clamp_to_prior(config.prior, requested)
        clamped = target != requested

        with Stopwatch("compose") as watch:
            weight_set = importance_weights(config.population, objects, target, reference_theta)
            by_id = {
                obj.obj_id: weight for obj, weight in zip(objects, weight_set.weights, strict=True)
            }
            detected_weights = [by_id[obj_id] for obj_id in detected_ids]
            n_eff_all = kish_effective_sample_size(list(weight_set.weights))
            n_eff_detected = kish_effective_sample_size(detected_weights)
            composed = weighted_summary(config, detections, by_id, float(len(objects)))

        rungs.append(
            {
                "scale": scale,
                "theta_requested": requested,
                "theta": target,
                "clamped_to_prior": clamped,
                "library_size": len(objects),
                "n_detected_in_library": len(detected_ids),
                "n_eff_formula": "kish: (sum w)^2 / sum w^2",
                "n_eff_library": n_eff_all,
                "n_eff_detected": n_eff_detected,
                "n_eff_criterion": {
                    "reported_against": "n_eff_detected",
                    "factor": factor,
                    "source": "Farr 2019, arXiv:1904.10879, after equation 12",
                    "scenarios": _criterion_table(config, n_eff_detected),
                },
                "rejected_out_of_support": {
                    "count": weight_set.n_rejected,
                    "fraction": weight_set.rejected_fraction,
                },
                "composition_wall_seconds": watch.seconds,
                "simulation_wall_seconds": simulation_seconds,
                "wall_seconds_saved": simulation_seconds - watch.seconds,
                "speedup": (simulation_seconds / watch.seconds) if watch.seconds > 0 else None,
            }
        )
        row: dict[str, Any] = {
            "draw": f"rung-{scale:g}",
            "scale": scale,
            "n_objects": len(objects),
            "n_detected": len(detected_ids),
            "n_detections": len(detections),
            "n_eff_detected": n_eff_detected,
        }
        for name, value in target.items():
            row[f"theta_{name}"] = value
        row.update(composed)
        composed_rows.append(row)

    composed_path = schema.write_rows(outdir / COMPOSED_FILE, composed_rows)
    ladder_path = outdir / LADDER_FILE
    ladder_path.write_text(
        json.dumps(
            {
                "reference_theta": reference_theta,
                "ladder_direction": config.library.ladder_direction,
                "rungs": rungs,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ledger = ByteLedger()
    ledger.record("composed_x", composed_path)
    ledger.record("ladder", ladder_path)

    Manifest(
        stage=STAGE,
        experiment=config.reference(),
        inputs=[
            fingerprint(config.path, "experiment_config"),
            fingerprint(library_population_dir / "orbits.csv", "library_orbits"),
            fingerprint(detections_file, "library_detections"),
            fingerprint(campaign_manifest, "library_campaign_manifest"),
        ],
        outputs=[fingerprint(composed_path, "composed_x"), fingerprint(ladder_path, "ladder")],
        parameters=config.library.as_dict(),
        prior=config.prior.as_dict(),
        schemas=[schema.as_dict()],
        environment=environment_snapshot(),
        measurements={
            "boundary": "reweighted-library viability",
            "n_eff_formula": "kish: (sum w)^2 / sum w^2",
            "criterion": f"n_eff > {factor} * n_obs (Farr 2019, arXiv:1904.10879)",
            "n_obs_scenarios": [s.as_dict() for s in config.library.n_obs_scenarios],
            "library_size": len(objects),
            "n_detected_in_library": len(detected_ids),
            "simulation_wall_seconds": simulation_seconds,
            "rungs": rungs,
            "bytes": ledger.as_dict(),
        },
    ).write(manifest_path(outdir, STAGE))

    return {"composed_x": composed_path, "ladder": ladder_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etno-twin-library", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--population-dir", required=True, type=Path)
    parser.add_argument("--campaign-dir", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--stem", default="detections")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(
        load_experiment(args.config),
        args.population_dir,
        args.campaign_dir,
        args.outdir,
        stem=args.stem,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
