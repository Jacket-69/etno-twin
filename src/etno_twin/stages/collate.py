"""Final stage — fold every stage manifest into one ``measurements.json``.

Each stage records its own measurements next to its own artifacts, which is what keeps
the stages independent. This stage is the other half of that arrangement: it reads the
manifests back and produces the single artifact ADR-0001 cites, with the cost model
fitted and the two independent estimates of fixed cost placed side by side.

Nothing is measured here and nothing is printed. Collation reads files and writes one.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from etno_twin.kernel.config import ExperimentConfig, load_experiment
from etno_twin.kernel.manifest import MANIFEST_SUFFIX, read_manifest
from etno_twin.kernel.measure import utc_now
from etno_twin.kernel.stats import ols_line_fit

STAGE = "collate"
MEASUREMENTS_FILE = "measurements.json"
MEASUREMENTS_SCHEMA = "etno-twin/measurements@1"


def _collect(experiment_dir: Path) -> dict[str, list[dict[str, Any]]]:
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(experiment_dir.rglob(f"*{MANIFEST_SUFFIX}")):
        payload = read_manifest(path)
        payload["_manifest_path"] = str(path)
        by_stage.setdefault(str(payload["stage"]), []).append(payload)
    return by_stage


def fit_cost_model(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Separate fixed from marginal cost, by two routes, and put them side by side.

    **Route one — the ladder.** Fit ``T = T_fixed + N · t_marginal`` across the sweep of
    population sizes. Repetitions at the same size are reduced by their median rather than
    their mean, so one descheduled run does not move the estimate.

    **Route two — the log.** Each run's own log attributes its wall-clock to named phases,
    and the phases that do not depend on population size are added up. The two routes use
    different data; agreement is evidence the classification of phases is right, and
    disagreement says it is not, which is worth knowing before a campaign is sized on it.
    """
    measured = [run for run in runs if not run["measurements"].get("warmup", False)]
    warmups = [run for run in runs if run["measurements"].get("warmup", False)]

    by_size: dict[int, list[float]] = {}
    for run in measured:
        size = int(run["measurements"]["n_objects"])
        by_size.setdefault(size, []).append(float(run["measurements"]["process"]["wall_seconds"]))

    points = sorted((size, statistics.median(times)) for size, times in by_size.items())
    summary: dict[str, Any] = {
        "model": "T(N) = T_fixed + N * t_marginal",
        "points": [
            {
                "n_objects": size,
                "repetitions": len(by_size[size]),
                "median_wall_seconds": median,
                "wall_seconds": sorted(by_size[size]),
            }
            for size, median in points
        ],
        "warmup_runs_excluded": [
            {
                "label": run["parameters"]["label"],
                "n_objects": run["measurements"]["n_objects"],
                "wall_seconds": run["measurements"]["process"]["wall_seconds"],
            }
            for run in warmups
        ],
    }

    if len(points) < 2:
        summary["fit"] = {
            "available": False,
            "reason": (
                "a straight-line fit needs at least two distinct population sizes; this "
                "experiment ran one, which is exactly the defect the sweep exists to remove"
            ),
        }
    else:
        fit = ols_line_fit([float(size) for size, _ in points], [value for _, value in points])
        summary["fit"] = {
            "available": True,
            "fixed_seconds": fit.intercept,
            "marginal_seconds_per_object": fit.slope,
            "r_squared": fit.r_squared,
            "n_points": fit.n_points,
        }

    from_log = [
        run["measurements"]["fixed_cost_from_log"]
        for run in measured
        if run["measurements"].get("fixed_cost_from_log", {}).get("applicable")
    ]
    if from_log:
        summary["fixed_cost_from_log"] = {
            "available": True,
            "n_runs": len(from_log),
            "median_fixed_seconds": statistics.median(
                float(item["fixed_seconds"]) for item in from_log
            ),
            "median_size_independent_seconds": statistics.median(
                float(item["size_independent_seconds"]) for item in from_log
            ),
            "median_interpreter_startup_seconds": statistics.median(
                float(item["interpreter_startup_seconds"]) for item in from_log
            ),
            "phases_treated_as_size_independent": from_log[0]["size_independent_phases"],
        }
        if summary["fit"].get("available"):
            summary["fixed_cost_agreement"] = {
                "from_sweep_seconds": summary["fit"]["fixed_seconds"],
                "from_log_seconds": summary["fixed_cost_from_log"]["median_fixed_seconds"],
                "difference_seconds": summary["fit"]["fixed_seconds"]
                - summary["fixed_cost_from_log"]["median_fixed_seconds"],
            }
    else:
        summary["fixed_cost_from_log"] = {
            "available": False,
            "reason": "phase classification is pinned to the sorcha binding",
        }
    return summary


def _peak_rss(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Largest worker footprint, over the runs whose memory figure is worth reporting.

    A run too short for the probe to sample properly is excluded rather than averaged in:
    its figure is an underestimate taken before the process allocated anything, and one
    such number folded into a maximum would understate the constraint that decides how
    many campaign workers fit on a machine.
    """
    reliable = [
        int(run["measurements"]["process"]["peak_rss_bytes"] or 0)
        for run in runs
        if run["measurements"]["process"].get("peak_rss_reliable")
    ]
    if not reliable:
        return {
            "available": False,
            "reason": (
                "every run was too short for the memory probe to sample; the figures "
                "recorded per run are underestimates, not measurements"
            ),
            "n_runs": len(runs),
        }
    return {
        "available": True,
        "max": max(reliable),
        "n_runs_measured": len(reliable),
        "n_runs_excluded_as_too_short": len(runs) - len(reliable),
        "source": "proc_vm_hwm, largest single process in the run's process tree",
    }


EXAMPLE_LIMIT = 10
"""How many individual records a summary quotes before it starts counting instead.

An experiment of ten thousand draws has ten thousand seeds and twenty thousand manifests.
Enumerating them turns the artifact the ADR cites into several megabytes of paths, and the
per-run detail is already durable in the manifests themselves. The summary therefore
reports the count, the property that must hold across all of them, and a handful of
examples.
"""


def _seeds_recovered(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """That every run recorded its seed, how many did, and a few of them.

    The claim that matters at this level is *all of them* — a run whose seed was not
    recovered never reaches a manifest, because the campaign stage raises. The individual
    values live in the per-run manifests.
    """
    records = [
        {
            "label": run["parameters"]["label"],
            "base_seed": run["seeds"]["simulator"]["base"],
            "source": run["seeds"]["recovered_from"],
        }
        for run in runs
    ]
    return {
        "n_runs": len(records),
        "all_recovered": all(int(record["base_seed"]) > 0 for record in records),
        "distinct_seeds": len({record["base_seed"] for record in records}),
        "examples": records[:EXAMPLE_LIMIT],
    }


def _population_section(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The population boundary, aggregated rather than enumerated."""
    measurements = [entry["measurements"] for entry in entries]
    return {
        "boundary": "population -> simulator inputs",
        "n_runs": len(measurements),
        "total_objects": sum(int(item["n_objects"]) for item in measurements),
        "median_generation_seconds": statistics.median(
            float(item["generation"]["wall_seconds"]) for item in measurements
        ),
        "total_bytes": sum(int(item["bytes"]["total_bytes"]) for item in measurements),
        "median_bytes_per_object": statistics.median(
            float(item["bytes_per_object"]) for item in measurements
        ),
    }


def _campaign_section(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    sweep = [run for run in runs if str(run["parameters"]["label"]).startswith("sweep")]
    draws = [run for run in runs if str(run["parameters"]["label"]).startswith("draw")]
    library = [run for run in runs if str(run["parameters"]["label"]).startswith("library")]
    timing_source = sweep or draws or library

    efficiencies = [run["measurements"]["detection_efficiency"] for run in draws or runs]
    section: dict[str, Any] = {
        "boundary": "simulator run",
        "binding": runs[0]["parameters"]["binding"] if runs else None,
        "n_runs": len(runs),
        "cost_model": fit_cost_model(timing_source),
        "seeds_recovered": _seeds_recovered(runs),
        "peak_rss_bytes": _peak_rss(runs),
    }
    if efficiencies:
        section["detection_efficiency"] = {
            "n_runs": len(efficiencies),
            "median_fraction_objects_detected": statistics.median(
                float(item["fraction_objects_detected"]) for item in efficiencies
            ),
            "median_detections_per_object": statistics.median(
                float(item["detections_per_object"]) for item in efficiencies
            ),
            "total_objects": sum(int(item["n_objects"]) for item in efficiencies),
            "total_objects_detected": sum(int(item["n_objects_detected"]) for item in efficiencies),
            "total_detections": sum(int(item["n_detections"]) for item in efficiencies),
        }
    bytes_per_detection = [
        float(run["measurements"]["bytes_per_detection"])
        for run in runs
        if run["measurements"].get("bytes_per_detection")
    ]
    if bytes_per_detection:
        section["bytes_per_detection"] = {
            "median": statistics.median(bytes_per_detection),
            "n_runs": len(bytes_per_detection),
        }
    return section


def run(config: ExperimentConfig, experiment_dir: Path) -> dict[str, Path]:
    """Read every manifest under an experiment directory and write the measurements."""
    by_stage = _collect(experiment_dir)
    boundaries: dict[str, Any] = {}

    if by_stage.get("population"):
        boundaries["population"] = _population_section(by_stage["population"])
    for stage in ("dataset", "library", "training"):
        entries = by_stage.get(stage, [])
        if entries:
            boundaries[stage] = [entry["measurements"] for entry in entries]
    if by_stage.get("campaign"):
        boundaries["campaign"] = _campaign_section(by_stage["campaign"])

    payload = {
        "schema": MEASUREMENTS_SCHEMA,
        "generated_utc": utc_now(),
        "experiment": config.reference(),
        "binding": config.campaign.binding,
        "external_data": [
            entry["external_data"]
            for entry in by_stage.get("snapshot", [])
            if entry.get("external_data")
        ],
        "boundaries": boundaries,
        "manifests": {
            "root": str(experiment_dir),
            "n_manifests": sum(len(entries) for entries in by_stage.values()),
            "by_stage": {stage: len(entries) for stage, entries in sorted(by_stage.items())},
            "examples": [
                entry["_manifest_path"] for entries in by_stage.values() for entry in entries
            ][:EXAMPLE_LIMIT],
        },
    }
    output = experiment_dir / MEASUREMENTS_FILE
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"measurements": output}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etno-twin-collate", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--experiment-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(load_experiment(args.config), args.experiment_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
