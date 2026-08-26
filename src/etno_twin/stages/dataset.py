"""Stage 3 — detections to (parameters, simulated observations) pairs.

Boundary measured here: wall-clock of composition, and the bytes of the simulated
observations **both raw and summarised**. Pricing both is the point. Persisting only
hand-made summary statistics closes the door on training an embedding network later
without re-running the entire campaign, so the intended default is to keep the
detections at the rawest affordable level — and "affordable" is a number this stage
produces rather than a judgement made in advance.

The summary reads only the columns the simulator port declares meaningful in every
binding. Reaching for a sky position would work perfectly against the real simulator and
produce nonsense against the fake, which is exactly the class of divergence the declared
schema exists to prevent.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from etno_twin.kernel.config import ExperimentConfig, load_experiment, theta_columns
from etno_twin.kernel.hashing import fingerprint
from etno_twin.kernel.manifest import Manifest, manifest_path
from etno_twin.kernel.measure import ByteLedger, Stopwatch, environment_snapshot
from etno_twin.kernel.schemas import DATASET_PAIRS, DETECTIONS
from etno_twin.kernel.summary import summarise, summary_columns

STAGE = "dataset"
PAIRS_FILE = "pairs.csv"

TORCH_DTYPE_NOTE = (
    "The SBI library consumes float32 tensors; this artifact is written as text and cast "
    "at load time, which costs a conversion pass and keeps the artifact readable by "
    "anything. Storing float32 directly would save roughly half the bytes of the "
    "summarised table and none of the raw table, which dominates."
)


def run(
    config: ExperimentConfig,
    draw_dirs: Sequence[Path],
    outdir: Path,
    *,
    stem: str = "detections",
) -> dict[str, Path]:
    """Compose the training dataset from every draw of the campaign."""
    outdir.mkdir(parents=True, exist_ok=True)
    schema = DATASET_PAIRS.extended_with([*theta_columns(config.prior), *summary_columns(config)])

    ledger = ByteLedger()
    rows: list[dict[str, Any]] = []
    prior_fingerprints: set[str] = set()

    with Stopwatch("compose") as watch:
        for draw_dir in sorted(draw_dirs):
            parameters = json.loads((draw_dir / "theta.json").read_text(encoding="utf-8"))
            prior_fingerprints.add(str(parameters["prior_fingerprint"]))
            detections_file = draw_dir / f"{stem}.csv"
            detections = DETECTIONS.read_rows(detections_file)
            ledger.record("detections_raw", detections_file)
            row: dict[str, Any] = {
                "draw": parameters["label"],
                "n_objects": parameters["n_objects"],
                "n_detected": len({item["ObjID"] for item in detections}),
                "n_detections": len(detections),
            }
            for name, value in parameters["parameters"].items():
                row[f"theta_{name}"] = value
            row.update(summarise(config, detections))
            rows.append(row)
        pairs = schema.write_rows(outdir / PAIRS_FILE, rows)

    if len(prior_fingerprints) > 1:
        raise ValueError(
            "draws were generated under different priors; a dataset mixing them is invalid: "
            f"{sorted(prior_fingerprints)}"
        )
    ledger.record("pairs_summarised", pairs)

    Manifest(
        stage=STAGE,
        experiment=config.reference(),
        inputs=[
            fingerprint(config.path, "experiment_config"),
            *[fingerprint(d / f"{stem}.csv", "detections") for d in sorted(draw_dirs)],
        ],
        outputs=[fingerprint(pairs, "pairs")],
        parameters={
            "n_pairs": len(rows),
            # Which simulator produced these pairs travels with them. A training run
            # measured on one binding must not be readable as if it came from the other.
            "binding": config.campaign.binding,
            "theta_columns": list(theta_columns(config.prior)),
            "x_columns": list(summary_columns(config)),
            "summary": config.dataset.as_dict(),
            "columns": list(schema.columns),
        },
        prior=config.prior.as_dict(),
        schemas=[schema.as_dict(), DETECTIONS.as_dict()],
        environment=environment_snapshot(),
        measurements={
            "boundary": "detections -> (parameters, observations) pairs",
            "n_pairs": len(rows),
            "composition": watch.as_dict(),
            "bytes": ledger.as_dict(),
            "bytes_raw_per_pair": (
                ledger.entries.get("detections_raw", 0) / len(rows) if rows else 0.0
            ),
            "bytes_summarised_per_pair": (
                ledger.entries.get("pairs_summarised", 0) / len(rows) if rows else 0.0
            ),
            "raw_to_summary_ratio": (
                ledger.entries.get("detections_raw", 0) / ledger.entries.get("pairs_summarised", 1)
            ),
            "dtype_note": TORCH_DTYPE_NOTE,
        },
    ).write(manifest_path(outdir, STAGE))

    return {"pairs": pairs}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etno-twin-dataset", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--draw-dir", dest="draw_dirs", action="append", default=[], type=Path)
    parser.add_argument(
        "--draw-dirs-from",
        type=Path,
        default=None,
        help=(
            "File listing one draw directory per line. The budget experiment composes ten "
            "thousand draws, whose paths do not belong on a command line."
        ),
    )
    parser.add_argument("--stem", default="detections")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    draw_dirs = list(args.draw_dirs)
    if args.draw_dirs_from is not None:
        draw_dirs.extend(
            Path(line.strip())
            for line in args.draw_dirs_from.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if not draw_dirs:
        raise SystemExit("no draws given: pass --draw-dir or --draw-dirs-from")
    run(load_experiment(args.config), draw_dirs, args.outdir, stem=args.stem)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
