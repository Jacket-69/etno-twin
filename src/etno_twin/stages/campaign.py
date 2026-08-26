"""Stage 2 — run the survey simulator over one population.

Boundary measured here, and it is the expensive one:

* **Wall-clock**, from the parent process, so interpreter start-up counts as the fixed
  cost it is. Repeated across a ladder of population sizes, this is what separates
  ``T_fixed`` from ``N · t_marginal`` — the split the earlier extrapolation could not
  make, having measured a single size.
* **Peak resident set size**, polled from the child's own high-water mark.
* **Output bytes**, and bytes per detection.
* **Detection efficiency** — the fraction of objects detected and the detections per
  object — which feeds the dominant unknown of the whole cost estimate: how many objects
  a single set of population parameters has to contain before there is anything to infer
  from.
* **The seed**, parsed from the run log. Neither binding takes a seed from the caller.
* **The phase profile**, from the timestamps in the same log, which estimates fixed cost
  a second time and independently of the ladder.

The simulator always runs as a child process. That is not caution about a crash-prone
dependency, though it is also that: it is the seam the architectural decision is about.
A stage that called the simulator in-process would work and would prove nothing.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from etno_twin.kernel.config import ExperimentConfig, load_experiment
from etno_twin.kernel.hashing import fingerprint
from etno_twin.kernel.manifest import Manifest, inputs_by_role, manifest_path
from etno_twin.kernel.measure import ByteLedger, environment_snapshot, run_measured
from etno_twin.kernel.schemas import DETECTIONS, ORBITS
from etno_twin.simulators import fake as fake_binding
from etno_twin.simulators import sorcha_adapter
from etno_twin.simulators.base import (
    PhaseProfile,
    SimulatorContractError,
    detections_path,
    find_log,
    parse_seeds,
    phase_profile,
)

STAGE = "campaign"
DEFAULT_STEM = "detections"


class SimulatorFailed(RuntimeError):
    """The simulator exited non-zero.

    A dead worker is a missing artifact plus a recorded reason — exit code, log path —
    which is what makes a long campaign resumable instead of merely restartable.
    """


def _argv_for(
    config: ExperimentConfig, population_dir: Path, run_dir: Path, stem: str
) -> tuple[list[str], list[tuple[str, str]], dict[str, Any]]:
    orbits = population_dir / "orbits.csv"
    physical = population_dir / "physical-parameters.csv"
    if config.campaign.binding == "sorcha":
        sorcha = config.campaign.sorcha
        pointing = sorcha_adapter.resolve_pointing_db(sorcha.pointing_db)
        argv = sorcha_adapter.build_argv(
            executable=sorcha.executable,
            config_ini=sorcha.config_ini,
            orbits=orbits,
            physical_parameters=physical,
            pointing_db=pointing,
            run_dir=run_dir,
            stem=stem,
            ephemeris_cache=sorcha.ephemeris_cache,
        )
        return argv, list(sorcha_adapter.PHASE_MARKERS), {"pointing_source": str(pointing)}
    fake = config.campaign.fake
    argv = fake_binding.build_argv(
        config_ini=fake.config_ini,
        orbits=orbits,
        physical_parameters=physical,
        pointing_table=fake.pointing_table,
        run_dir=run_dir,
        stem=stem,
        field_probability=fake.field_probability,
    )
    return (
        argv,
        list(fake_binding.FAKE_PHASE_MARKERS),
        {
            "pointing_source": str(fake.pointing_table),
            "field_probability": fake.field_probability,
        },
    )


def _fixed_cost_estimate(
    config: ExperimentConfig, profile: PhaseProfile, wall_seconds: float
) -> dict[str, Any]:
    """Fixed cost of this single run, as read from its own log.

    ``interpreter_startup`` is the difference between what the parent measured and the
    span the log covers: importing the simulator's package happens before its first log
    line, and it is paid once per process like everything else in this block.
    """
    if config.campaign.binding != "sorcha":
        return {
            "applicable": False,
            "reason": "phase classification is pinned to the sorcha binding",
        }
    size_independent = profile.total_of(sorcha_adapter.SIZE_INDEPENDENT_PHASES)
    startup = max(wall_seconds - profile.log_span_seconds, 0.0)
    return {
        "applicable": True,
        "size_independent_phases": list(sorcha_adapter.SIZE_INDEPENDENT_PHASES),
        "size_independent_seconds": size_independent,
        "interpreter_startup_seconds": startup,
        "fixed_seconds": size_independent + startup,
        "size_dependent_phases": list(sorcha_adapter.SIZE_DEPENDENT_PHASES),
        "size_dependent_seconds": profile.total_of(sorcha_adapter.SIZE_DEPENDENT_PHASES),
    }


def _clear_previous_run(outdir: Path, stem: str) -> list[str]:
    """Remove any artifact a previous attempt at this run left behind.

    A stage owns its output directory: given the same inputs it rebuilds it, rather than
    adding to it. That is not tidiness. The real simulator decorates its log filename with
    a timestamp and a process id, so a retried run leaves the earlier log in place, and a
    directory holding two logs is a directory where "which seed did this run use?" has two
    answers. Overwriting the output file — which the simulator's own force flag does — is
    not enough.

    Only artifacts named after this run's stem are removed, so the population tables the
    previous stage wrote are untouched.
    """
    removed: list[str] = []
    for path in sorted(outdir.glob(f"{stem}*")):
        if path.is_file():
            path.unlink()
            removed.append(path.name)
    return removed


def _normalise_empty_output(config: ExperimentConfig, output: Path, log_text: str) -> bool:
    """Give a run that detected nothing the empty artifact the port promises.

    The two bindings disagree here and the port is where the disagreement is settled: one
    writes an empty table, the other writes no table. Downstream stages are entitled to
    exactly one detections file per run, and a population the survey could not see is a
    measurement, not a gap.
    """
    if output.exists():
        return False
    if config.campaign.binding == "sorcha" and sorcha_adapter.explains_empty_output(log_text):
        DETECTIONS.write_rows(output, [])
        return True
    raise SimulatorContractError(
        f"binding produced no detections table at {output}, and its log does not account "
        "for the absence"
    )


def run(
    config: ExperimentConfig,
    population_dir: Path,
    outdir: Path,
    label: str,
    *,
    snapshot_manifest: Path | None = None,
    stem: str = DEFAULT_STEM,
    warmup: bool = False,
) -> dict[str, Path]:
    """Simulate one population and record what the run cost."""
    outdir.mkdir(parents=True, exist_ok=True)
    orbits_path = population_dir / "orbits.csv"
    parameters_path = population_dir / "theta.json"
    n_objects = len(ORBITS.read_rows(orbits_path))
    theta_payload = json.loads(parameters_path.read_text(encoding="utf-8"))

    argv, markers, binding_details = _argv_for(config, population_dir, outdir, stem)
    cleared = _clear_previous_run(outdir, stem)

    # Everything above and below the call to run_measured is harness: hashing, reading
    # manifests, counting rows. Only the child process is inside the timed region.
    measurement = run_measured(argv, stdout_path=outdir / f"{stem}.stdout.txt")
    if measurement.exit_code != 0:
        raise SimulatorFailed(
            f"{config.campaign.binding} binding exited {measurement.exit_code} for {label}; "
            f"see {outdir}"
        )

    log_path = find_log(outdir, stem)
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    seeds = parse_seeds(log_text)
    profile = phase_profile(log_text, markers)

    output = detections_path(outdir, stem)
    synthesised_empty = _normalise_empty_output(config, output, log_text)
    detections = DETECTIONS.read_rows(output)
    detected_objects = {row["ObjID"] for row in detections}

    ledger = ByteLedger()
    ledger.record("detections", output)
    ledger.record("run_log", log_path)

    external = inputs_by_role(snapshot_manifest) if snapshot_manifest else {}

    Manifest(
        stage=STAGE,
        experiment=config.reference(),
        inputs=[
            fingerprint(config.path, "experiment_config"),
            fingerprint(orbits_path, "orbits"),
            fingerprint(population_dir / "physical-parameters.csv", "physical_parameters"),
            fingerprint(parameters_path, "parameters"),
        ],
        outputs=[fingerprint(output, "detections"), fingerprint(log_path, "run_log")],
        parameters={
            "label": label,
            "binding": config.campaign.binding,
            "warmup": warmup,
            "n_objects": n_objects,
            "theta": theta_payload.get("parameters", {}),
            "detections_table_synthesised_empty": synthesised_empty,
            "cleared_before_run": cleared,
            **binding_details,
        },
        prior=config.prior.as_dict(),
        seeds={
            "master": config.master_seed,
            "simulator": seeds.as_dict(),
            "recovered_from": str(log_path),
        },
        schemas=[DETECTIONS.as_dict()],
        environment=environment_snapshot(packages=("sorcha",)),
        external_data={role: item for role, item in external.items()},
        measurements={
            "boundary": "simulator run",
            "warmup": warmup,
            "n_objects": n_objects,
            "process": measurement.as_dict(),
            "phase_profile": profile.as_dict(),
            "fixed_cost_from_log": _fixed_cost_estimate(config, profile, measurement.wall_seconds),
            "seconds_per_object": measurement.wall_seconds / n_objects if n_objects else 0.0,
            "bytes": ledger.as_dict(),
            "detections_table_synthesised_empty": synthesised_empty,
            "detection_efficiency": {
                "n_objects": n_objects,
                "n_objects_detected": len(detected_objects),
                "fraction_objects_detected": len(detected_objects) / n_objects
                if n_objects
                else 0.0,
                "n_detections": len(detections),
                "detections_per_object": len(detections) / n_objects if n_objects else 0.0,
                "detections_per_detected_object": (
                    len(detections) / len(detected_objects) if detected_objects else 0.0
                ),
            },
            "bytes_per_detection": (
                output.stat().st_size / len(detections) if detections else None
            ),
        },
    ).write(manifest_path(outdir, STAGE))

    return {"detections": output, "run_log": log_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etno-twin-campaign", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--population-dir", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--snapshot-manifest", type=Path, default=None)
    parser.add_argument("--stem", default=DEFAULT_STEM)
    parser.add_argument(
        "--warmup",
        action="store_true",
        help=(
            "Mark this run as a warm-up. It is recorded in full and excluded from the cost "
            "fit: the first run of a session pays for page cache the rest do not."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(
        load_experiment(args.config),
        args.population_dir,
        args.outdir,
        args.label,
        snapshot_manifest=args.snapshot_manifest,
        stem=args.stem,
        warmup=args.warmup,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
