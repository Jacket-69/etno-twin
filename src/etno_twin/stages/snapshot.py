"""Stage 0 — fingerprint the external data an experiment depends on.

The survey simulator's demo files are snapshots like any other, and so is the ephemeris
cache: a result depends on which planetary ephemerides produced it, so the ephemeris
version is provenance. Hashing them is a stage of its own for two reasons.

**Correctness.** `docs/data/provenance.md` requires content-addressed inputs with a
manifest. Using the demo files without hashing them into the manifest is one of the
failure modes the design names explicitly.

**Measurement hygiene.** The ephemeris cache is 780 MB; hashing it costs a second or two.
Doing that once, in its own node of the graph, keeps it out of every timed region — a
campaign run measures the simulator, not the harness around it.

Nothing here downloads anything. The cache is expected to exist; a missing cache is an
error that names the problem rather than a silent fetch of 780 MB.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from etno_twin.kernel.config import ExperimentConfig, load_experiment
from etno_twin.kernel.hashing import fingerprint, fingerprint_directory
from etno_twin.kernel.manifest import Manifest, manifest_path
from etno_twin.kernel.measure import Stopwatch, environment_snapshot
from etno_twin.simulators.sorcha_adapter import resolve_pointing_db, sorcha_version

STAGE = "snapshot"


class MissingExternalData(FileNotFoundError):
    """An external input the experiment declares is not on this machine."""


def run(config: ExperimentConfig, outdir: Path) -> dict[str, Path]:
    """Fingerprint every external input of the configured binding."""
    outdir.mkdir(parents=True, exist_ok=True)
    binding = config.campaign.binding
    external: dict[str, Any] = {"binding": binding}

    with Stopwatch("fingerprint") as watch:
        if binding == "sorcha":
            sorcha = config.campaign.sorcha
            if not sorcha.config_ini.exists():
                raise MissingExternalData(f"survey configuration not found: {sorcha.config_ini}")
            pointing = resolve_pointing_db(sorcha.pointing_db)
            inputs = [
                fingerprint(sorcha.config_ini, "survey_config"),
                fingerprint(pointing, "pointing_database"),
            ]
            if not sorcha.ephemeris_cache.exists():
                raise MissingExternalData(
                    f"ephemeris cache not found at {sorcha.ephemeris_cache}. It is an external, "
                    "versioned dependency of roughly 780 MB and is not fetched by this pipeline."
                )
            cache = fingerprint_directory(sorcha.ephemeris_cache)
            external["ephemeris"] = cache.as_dict()
            external["sorcha_version"] = sorcha_version()
        else:
            fake = config.campaign.fake
            for path, role in (
                (fake.config_ini, "survey_config"),
                (fake.pointing_table, "pointing_table"),
            ):
                if not path.exists():
                    raise MissingExternalData(f"{role} not found: {path}")
            inputs = [
                fingerprint(fake.config_ini, "survey_config"),
                fingerprint(fake.pointing_table, "pointing_table"),
            ]
            external["ephemeris"] = {
                "applicable": False,
                "reason": "the fake binding computes no ephemerides",
            }

    manifest = Manifest(
        stage=STAGE,
        experiment=config.reference(),
        inputs=[fingerprint(config.path, "experiment_config"), *inputs],
        outputs=[],
        parameters={"binding": binding},
        prior=config.prior.as_dict(),
        environment=environment_snapshot(packages=("sorcha", "sbi", "snakemake")),
        external_data=external,
        measurements={"fingerprint": watch.as_dict()},
    )
    path = manifest_path(outdir, STAGE)
    manifest.write(path)
    return {"manifest": path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etno-twin-snapshot", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(load_experiment(args.config), args.outdir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
