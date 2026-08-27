"""Declared schemas for every artifact that crosses a stage boundary.

Stages do not import each other. They meet here: a stage writes a file whose schema is
declared in this module, and the next stage reads it back through the same declaration.
That is what makes the boundary a contract rather than a convention, and it is the
mitigation for the second failure mode the design names — letting the fake simulator and
the real one drift apart.

Formats are deliberately dull. CSV with a header, read and written with the standard
library, so an artifact can be inspected with `head` and diffed by a reviewer who has
none of this installed.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SchemaError(ValueError):
    """An artifact does not match the schema it declares."""


@dataclass(frozen=True)
class ArtifactSchema:
    """Identity and required columns of a tabular artifact."""

    schema_id: str
    columns: tuple[str, ...]
    description: str
    cross_port_columns: tuple[str, ...] = ()
    """Columns whose values carry the same meaning in every binding of the port.

    The fake simulator models a selection function, not the sky: it fills sky positions
    so the schema is honoured, but those numbers mean nothing. Any stage that consumes
    detections from *either* binding may read only these columns. Stages that read the
    rest are, by construction, sorcha-only.
    """

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "columns": list(self.columns),
            "cross_port_columns": list(self.cross_port_columns),
        }

    def validate_header(self, header: Sequence[str]) -> None:
        missing = [column for column in self.columns if column not in header]
        if missing:
            raise SchemaError(f"{self.schema_id}: missing columns {missing}")

    def extended_with(self, extra: Sequence[str]) -> ArtifactSchema:
        """The same schema plus columns an experiment declares.

        The dataset artifact has a fixed spine and a variable body: the population model
        decides how many parameter columns there are and the summary decides how many
        feature columns. Extending a declared schema keeps that variability inside the
        declaration instead of turning the artifact into a free-form table.
        """
        additions = tuple(column for column in extra if column not in self.columns)
        return ArtifactSchema(
            schema_id=self.schema_id,
            columns=self.columns + additions,
            description=self.description,
            cross_port_columns=self.cross_port_columns,
        )

    def read_rows(self, path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise SchemaError(f"{self.schema_id}: {path} has no header")
            self.validate_header(reader.fieldnames)
            return list(reader)

    def write_rows(self, path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.columns), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path


ORBITS = ArtifactSchema(
    schema_id="etno-twin/orbits@1",
    columns=(
        "ObjID",
        "FORMAT",
        "a",
        "e",
        "inc",
        "node",
        "argPeri",
        "ma",
        "epochMJD_TDB",
    ),
    description=(
        "Heliocentric Keplerian elements of a synthetic population, in the column names "
        "the survey simulator expects. FORMAT is the simulator's element-set tag; KEP "
        "throughout this spike."
    ),
)

PHYSICAL_PARAMETERS = ArtifactSchema(
    schema_id="etno-twin/physical-parameters@1",
    columns=("ObjID", "H_r", "GS", "u-r", "g-r", "i-r", "z-r", "y-r"),
    description=(
        "Absolute magnitude in r, phase-curve slope and colours relative to r, one row "
        "per object of the population."
    ),
)

POINTING_TABLE = ArtifactSchema(
    schema_id="etno-twin/pointing-table@1",
    columns=(
        "observationId",
        "observationStartMJD_TAI",
        "visitTime",
        "visitExposureTime",
        "filter",
        "seeingFwhmGeom_arcsec",
        "seeingFwhmEff_arcsec",
        "fieldFiveSigmaDepth_mag",
        "fieldRA_deg",
        "fieldDec_deg",
        "fieldRotSkyPos_deg",
    ),
    description=(
        "Survey cadence as one row per visit. The column names are exactly the aliases "
        "sorcha's own pointing_sql_query projects out of the Rubin OpSim database, so a "
        "fixture extracted through that query is schema-identical to what sorcha reads. "
        "The pointing *source* is per-binding — sorcha reads the SQLite database, the "
        "fake reads this table — which is why it is not part of the shared port "
        "contract; the shared contract is orbits and physical parameters in, detections "
        "out."
    ),
)

DETECTIONS = ArtifactSchema(
    schema_id="etno-twin/detections@1",
    columns=(
        "ObjID",
        "fieldMJD_TAI",
        "fieldRA_deg",
        "fieldDec_deg",
        "RA_deg",
        "Dec_deg",
        "astrometricSigma_deg",
        "optFilter",
        "trailedSourceMag",
        "trailedSourceMagSigma",
        "fiveSigmaDepth_mag",
        "phase_deg",
        "Range_LTC_km",
        "RangeRate_LTC_km_s",
        "Obj_Sun_LTC_km",
    ),
    cross_port_columns=(
        "ObjID",
        "fieldMJD_TAI",
        "optFilter",
        "trailedSourceMag",
        "fiveSigmaDepth_mag",
        "Range_LTC_km",
    ),
    description=(
        "One row per detected observation, in sorcha's `output_columns = basic` layout. "
        "An empty table — a population nothing was detected from — is a valid artifact "
        "and the expected outcome for parts of the parameter space; it is never an "
        "error."
    ),
)

DATASET_PAIRS = ArtifactSchema(
    schema_id="etno-twin/dataset-pairs@1",
    columns=("draw", "n_objects", "n_detected", "n_detections"),
    description=(
        "One row per (parameters, simulated observations) pair. Parameter columns are "
        "prefixed `theta_` and summary columns `x_`; both sets are declared by the "
        "experiment configuration rather than fixed here, because the population model "
        "and the summary are what the experiment varies. The header of the written file "
        "is therefore the authoritative column list, and the dataset manifest records it."
    ),
)

REGISTRY: dict[str, ArtifactSchema] = {
    schema.schema_id: schema
    for schema in (ORBITS, PHYSICAL_PARAMETERS, POINTING_TABLE, DETECTIONS, DATASET_PAIRS)
}
