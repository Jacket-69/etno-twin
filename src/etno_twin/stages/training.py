"""Stage 4 — train the neural posterior estimator and calibrate it.

Boundary measured here: wall-clock against simulation budget, bytes of the persisted
network, and simulation-based calibration ranks and coverage.

Calibration is not a decorative smoke test. It is the measurement that anchors the
simulation budget for the whole project: if the posterior is miscalibrated at 10³
simulations and calibrated at 10⁴, that is what a campaign has to be sized for, and no
amount of argument substitutes for the number.

**Two master seeds, and the reason.** Two trainings were going to happen anyway, one per
simulation budget. Running them under *different* master seeds costs nothing extra and
converts a promise into a measured number: the claim that a fresh master seed yields a
posterior and a coverage compatible within a declared tolerance is what distinguishes
replicability from reproducibility, and it is the answer to the objection that
regenerating results from persisted artifacts is archiving rather than reproducing.

This is the only stage that imports PyTorch, which is why nothing else in the package may
— an import-linter contract keeps the rest of the pipeline runnable on a machine with no
scientific stack.

The prior specification is checked, not assumed. A stored set of pairs is valid only for
the prior its parameters were drawn from, and a training run that silently consumed a
dataset built under a different prior would produce a posterior that looks fine and is
wrong.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import torch
from sbi.diagnostics import check_sbc, run_sbc
from sbi.inference import NPE
from sbi.utils import BoxUniform
from sbi.utils.tracking import TensorBoardTracker
from torch.utils.tensorboard.writer import SummaryWriter

from etno_twin.kernel.config import ExperimentConfig, load_experiment
from etno_twin.kernel.hashing import fingerprint
from etno_twin.kernel.manifest import Manifest, manifest_path, read_manifest
from etno_twin.kernel.measure import ByteLedger, Stopwatch, environment_snapshot

STAGE = "training"
POSTERIOR_FILE = "posterior.pt"
SBC_FILE = "sbc.json"

COVERAGE_LEVELS = (0.5, 0.9)


class PriorMismatch(ValueError):
    """The dataset was generated under a different prior than this run declares."""


def _load_pairs(
    pairs_path: Path, theta_columns: Sequence[str], x_columns: Sequence[str]
) -> tuple[torch.Tensor, torch.Tensor]:
    """Read the dataset artifact into the float32 tensors the SBI library expects."""
    thetas: list[list[float]] = []
    xs: list[list[float]] = []
    with pairs_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            thetas.append([float(row[name]) for name in theta_columns])
            xs.append([float(row[name]) for name in x_columns])
    return (
        torch.tensor(thetas, dtype=torch.float32),
        torch.tensor(xs, dtype=torch.float32),
    )


def _box_prior(config: ExperimentConfig) -> BoxUniform:
    low = torch.tensor(
        [config.prior.component(name).low for name in config.prior.names], dtype=torch.float32
    )
    high = torch.tensor(
        [config.prior.component(name).high for name in config.prior.names], dtype=torch.float32
    )
    return BoxUniform(low=low, high=high)


def _coverage_from_ranks(ranks: torch.Tensor, num_posterior_samples: int) -> dict[str, float]:
    """Empirical coverage of central credible intervals, from calibration ranks.

    Under a calibrated posterior the rank of the true parameter among posterior samples is
    uniform, so the fraction of ranks inside the central band of width ``level`` estimates
    the coverage of the credible interval at that level.
    """
    coverage: dict[str, float] = {}
    normalised = ranks.float() / float(num_posterior_samples)
    for level in COVERAGE_LEVELS:
        margin = (1.0 - level) / 2.0
        inside = ((normalised >= margin) & (normalised <= 1.0 - margin)).float().mean().item()
        coverage[f"central_{int(level * 100)}"] = inside
    return coverage


def _binding_note(binding: str) -> str:
    """Say which simulator produced the pairs, and what that does and does not mean.

    Carried in the manifest rather than left to a reader's assumption. A training figure
    that someone could take for a real-simulator figure is a trap, and this is the
    cheapest place to disarm it.
    """
    if binding == "fake":
        return (
            "These pairs were produced by the fake binding. Wall-clock of training, bytes "
            "of the persisted network and calibration do not depend on which simulator "
            "produced the pairs — the network sees a table of parameters and summary "
            "vectors and cannot know what wrote them — so the measurement keeps its "
            "meaning while its cost falls from tens of hours of real simulator time to "
            "minutes. Nothing here is a measurement of the survey simulator."
        )
    if binding == "sorcha":
        return "These pairs were produced by the real survey simulator."
    return f"Pairs produced by an unrecognised binding: {binding!r}."


def run(
    config: ExperimentConfig,
    pairs_path: Path,
    dataset_manifest: Path,
    outdir: Path,
    *,
    budget: int,
    master_seed: int,
) -> dict[str, Path]:
    """Train one posterior estimator at one budget under one master seed."""
    outdir.mkdir(parents=True, exist_ok=True)
    dataset = read_manifest(dataset_manifest)
    if dataset["experiment"]["prior_fingerprint"] != config.prior.fingerprint():
        raise PriorMismatch(
            "the dataset was generated under a different prior specification than this "
            "training run declares; the stored pairs are not valid for it"
        )

    pairs_binding = str(dataset["parameters"].get("binding", "unrecorded"))
    theta_columns = list(dataset["parameters"]["theta_columns"])
    x_columns = list(dataset["parameters"]["x_columns"])
    thetas, xs = _load_pairs(pairs_path, theta_columns, x_columns)

    available = int(thetas.shape[0])
    sbc_count = min(config.training.sbc_evaluations, max(available // 4, 1))
    train_count = min(budget, available - sbc_count)
    if train_count < 2:
        raise ValueError(
            f"dataset has {available} pairs; not enough to train at a budget of {budget} "
            f"while holding out {sbc_count} for calibration"
        )

    torch.manual_seed(master_seed)
    torch.use_deterministic_algorithms(False)

    train_theta, train_x = thetas[:train_count], xs[:train_count]
    sbc_theta, sbc_x = thetas[-sbc_count:], xs[-sbc_count:]

    # Left to itself the library writes its training curves into an `sbi-logs` directory
    # beside the working directory, in files named after the machine and the process. Both
    # halves are wrong here: an artifact of a run belongs under that run's output
    # directory, and the name of the machine is not something this repository publishes.
    tensorboard = outdir / "tensorboard"
    inference = NPE(
        prior=_box_prior(config),
        density_estimator=config.training.density_estimator,
        device="cpu",
        show_progress_bars=False,
        tracker=TensorBoardTracker(SummaryWriter(str(tensorboard))),
    )
    with Stopwatch("train") as training_watch:
        inference.append_simulations(train_theta, train_x)
        inference.train(max_num_epochs=config.training.max_epochs, show_train_summary=False)
        posterior = inference.build_posterior()

    posterior_path = outdir / POSTERIOR_FILE
    torch.save(posterior, posterior_path)

    with Stopwatch("sbc") as sbc_watch:
        ranks, dap_samples = run_sbc(
            sbc_theta,
            sbc_x,
            posterior,
            num_posterior_samples=config.training.sbc_posterior_samples,
            show_progress_bar=False,
        )
        checks = check_sbc(
            ranks,
            _box_prior(config).sample((sbc_count,)),
            dap_samples,
            num_posterior_samples=config.training.sbc_posterior_samples,
        )

    sbc_payload: dict[str, Any] = {
        "n_evaluations": sbc_count,
        "num_posterior_samples": config.training.sbc_posterior_samples,
        "parameters": [name.removeprefix("theta_") for name in theta_columns],
        "ranks": ranks.tolist(),
        "checks": {key: value.tolist() for key, value in checks.items()},
        "coverage": _coverage_from_ranks(ranks, config.training.sbc_posterior_samples),
    }
    sbc_path = outdir / SBC_FILE
    sbc_path.write_text(json.dumps(sbc_payload, indent=2) + "\n", encoding="utf-8")

    ledger = ByteLedger()
    ledger.record("posterior", posterior_path)
    ledger.record("sbc", sbc_path)

    Manifest(
        stage=STAGE,
        experiment=config.reference(),
        inputs=[
            fingerprint(config.path, "experiment_config"),
            fingerprint(pairs_path, "pairs"),
            fingerprint(dataset_manifest, "dataset_manifest"),
        ],
        outputs=[fingerprint(posterior_path, "posterior"), fingerprint(sbc_path, "sbc")],
        parameters={
            "budget_requested": budget,
            "n_simulations_used": train_count,
            "n_pairs_available": available,
            "master_seed": master_seed,
            "pairs_binding": pairs_binding,
            "pairs_binding_note": _binding_note(pairs_binding),
            "density_estimator": config.training.density_estimator,
            "max_epochs": config.training.max_epochs,
            "theta_columns": theta_columns,
            "x_columns": x_columns,
        },
        prior=config.prior.as_dict(),
        seeds={
            "training_master": master_seed,
            "note": (
                "the trained network is a reproducible artifact; retraining from this seed is "
                "a replication claim, since neither the training loop nor the hardware "
                "guarantees bit-identical results"
            ),
        },
        environment=environment_snapshot(packages=("sbi", "torch")),
        measurements={
            "boundary": "training and calibration",
            "n_simulations_requested": budget,
            "n_simulations_used": train_count,
            "master_seed": master_seed,
            "pairs_binding": pairs_binding,
            "pairs_binding_note": _binding_note(pairs_binding),
            "training": training_watch.as_dict(),
            "calibration": sbc_watch.as_dict(),
            "bytes": ledger.as_dict(),
            "sbc": {
                "n_evaluations": sbc_count,
                "coverage": sbc_payload["coverage"],
                "checks": sbc_payload["checks"],
            },
        },
    ).write(manifest_path(outdir, STAGE))

    return {"posterior": posterior_path, "sbc": sbc_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etno-twin-training", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--pairs", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=int)
    parser.add_argument("--master-seed", required=True, type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(
        load_experiment(args.config),
        args.pairs,
        args.dataset_manifest,
        args.outdir,
        budget=args.budget,
        master_seed=args.master_seed,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
