"""Copy an experiment's collated measurements into the versioned evidence directory.

An ADR that cites evidence living in a gitignored directory is not citable. Experiment
output trees are regenerable and stay out of version control; the **collated summary** —
the one artifact an ADR points at — is copied here and committed.

What is *not* copied: detection catalogues, run logs, per-run manifests, trained networks.
Those stay in the run tree. The summary carries their counts, their hashes by reference,
and the path they were produced under, which is what makes the claim checkable without
putting hundreds of megabytes into a repository a preprint will cite.

    uv run python scripts/publish_evidence.py runs/sp1-sweep

The destination filename is the experiment's own name, so republishing an experiment
overwrites its evidence rather than accumulating copies, and the diff shows what moved.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

from etno_twin.kernel.hashing import sha256_file

EVIDENCE_DIR = Path("docs/architecture/evidence/sp1-step2")
SIZE_WARNING_BYTES = 1_000_000


def publish(experiment_dir: Path, evidence_dir: Path = EVIDENCE_DIR) -> Path:
    source = experiment_dir / "measurements.json"
    if not source.exists():
        raise SystemExit(f"no collated measurements at {source}; run the experiment first")
    payload = json.loads(source.read_text(encoding="utf-8"))
    name = payload["experiment"]["name"]
    evidence_dir.mkdir(parents=True, exist_ok=True)
    destination = evidence_dir / f"{name}.measurements.json"
    shutil.copy2(source, destination)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE_DIR)
    args = parser.parse_args(argv)

    destination = publish(args.experiment_dir, args.evidence_dir)
    size = destination.stat().st_size
    print(f"published  {destination}")
    print(f"bytes      {size}")
    print(f"sha256     {sha256_file(destination)}")
    if size > SIZE_WARNING_BYTES:
        print(
            "\nWARNING: this summary is over a megabyte. Check that the collation is "
            "aggregating rather than enumerating before committing it."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
