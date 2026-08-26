"""The manifest every stage writes.

`docs/data/provenance.md` requires that every input to an experiment be an immutable,
content-addressed snapshot carrying a manifest, and that campaign artifacts additionally
record the random seed, the prior specification and the ephemeris version. This module is
where that requirement stops being prose: a stage that produces an artifact without a
manifest cannot get its outputs past the next stage, because reading one is how the next
stage learns what it is looking at.

The manifest is also where measurements live. Each stage writes its own, and a final
collation folds them into one `measurements.json` for the experiment — which keeps the
stages independent while still giving the ADR a single artifact to cite.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from etno_twin import __version__
from etno_twin.kernel.hashing import FileFingerprint
from etno_twin.kernel.measure import utc_now

MANIFEST_SCHEMA = "etno-twin/manifest@1"
MANIFEST_SUFFIX = ".manifest.json"


def code_version() -> dict[str, Any]:
    """Package version plus the git commit, when the code is running from a checkout."""
    info: dict[str, Any] = {"package_version": __version__}
    try:
        commit = subprocess.run(  # fixed argv, never a shell
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parent,
        )
        status = subprocess.run(  # fixed argv, never a shell
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parent,
        )
    except OSError:
        return info
    if commit.returncode == 0:
        info["git_commit"] = commit.stdout.strip()
        info["git_dirty"] = bool(status.stdout.strip())
    return info


@dataclass
class Manifest:
    """Everything needed to say what an artifact is and where it came from."""

    stage: str
    experiment: dict[str, Any]
    inputs: list[FileFingerprint] = field(default_factory=list)
    outputs: list[FileFingerprint] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    prior: dict[str, Any] = field(default_factory=dict)
    seeds: dict[str, Any] = field(default_factory=dict)
    schemas: list[dict[str, Any]] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    external_data: dict[str, Any] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "stage": self.stage,
            "created_utc": utc_now(),
            "code": code_version(),
            "experiment": self.experiment,
            "inputs": [item.as_dict() for item in self.inputs],
            "outputs": [item.as_dict() for item in self.outputs],
            "parameters": self.parameters,
            "prior": self.prior,
            "seeds": self.seeds,
            "schemas": self.schemas,
            "environment": self.environment,
            "external_data": self.external_data,
            "measurements": self.measurements,
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2, sort_keys=False) + "\n", "utf-8")
        return path


def read_manifest(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"{path}: not an {MANIFEST_SCHEMA} manifest")
    return payload


def manifest_path(outdir: Path, stage: str) -> Path:
    return outdir / f"{stage}{MANIFEST_SUFFIX}"


def inputs_by_role(path: Path) -> dict[str, dict[str, Any]]:
    """Fingerprints recorded by another stage, keyed by role.

    How a stage cites what an earlier stage established without importing it: the
    earlier stage hashed the external inputs once and wrote them down, and this reads
    them back off disk.
    """
    return {item["role"]: item for item in read_manifest(path)["inputs"]}
