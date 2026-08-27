"""Artifact schemas: the only place two stages are allowed to meet."""

from __future__ import annotations

from pathlib import Path

import pytest

from etno_twin.kernel.schemas import (
    DATASET_PAIRS,
    DETECTIONS,
    ORBITS,
    POINTING_TABLE,
    REGISTRY,
    SchemaError,
)


def test_a_table_round_trips_through_its_schema(tmp_path: Path) -> None:
    rows = [
        {
            "ObjID": "a",
            "FORMAT": "KEP",
            "a": 100.0,
            "e": 0.5,
            "inc": 12.0,
            "node": 1.0,
            "argPeri": 2.0,
            "ma": 3.0,
            "epochMJD_TDB": 60200.0,
        }
    ]
    path = ORBITS.write_rows(tmp_path / "orbits.csv", rows)
    assert ORBITS.read_rows(path)[0]["ObjID"] == "a"


def test_a_missing_column_is_refused_rather_than_read_as_blank(tmp_path: Path) -> None:
    path = tmp_path / "orbits.csv"
    path.write_text("ObjID,a,e\nx,100,0.5\n", encoding="utf-8")
    with pytest.raises(SchemaError, match="missing columns"):
        ORBITS.read_rows(path)


def test_an_extra_column_is_tolerated(tmp_path: Path) -> None:
    """A simulator may add columns; the contract is what must be present, not what must not."""
    path = tmp_path / "detections.csv"
    header = ",".join([*DETECTIONS.columns, "someNewColumn"])
    path.write_text(header + "\n", encoding="utf-8")
    assert DETECTIONS.read_rows(path) == []


def test_a_headerless_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(SchemaError, match="no header"):
        DETECTIONS.read_rows(path)


def test_extending_a_schema_keeps_the_spine_first() -> None:
    extended = DATASET_PAIRS.extended_with(["theta_alpha", "x_n_detections", "draw"])
    assert extended.columns[: len(DATASET_PAIRS.columns)] == DATASET_PAIRS.columns
    assert extended.columns.count("draw") == 1, "an existing column must not be duplicated"
    assert "theta_alpha" in extended.columns


def test_the_cross_port_columns_are_a_subset_of_the_declared_ones() -> None:
    assert set(DETECTIONS.cross_port_columns) <= set(DETECTIONS.columns)


def test_sky_positions_are_not_cross_port() -> None:
    """The fake fills them so the schema is honoured; the values mean nothing."""
    for column in ("RA_deg", "Dec_deg", "fieldRA_deg", "fieldDec_deg"):
        assert column not in DETECTIONS.cross_port_columns


def test_the_committed_pointing_fixture_matches_the_declared_schema(repo_root: Path) -> None:
    rows = POINTING_TABLE.read_rows(
        repo_root / "fixtures" / "pointing" / "rubin-baseline-1yr-subsample.csv"
    )
    assert len(rows) > 100
    nights = {int(float(row["observationStartMJD_TAI"]) - 16.0 / 24.0) for row in rows}
    assert len(nights) > 10, "the fixture must span enough nights for tracklets to link"


def test_every_schema_is_registered_under_its_own_identifier() -> None:
    for schema_id, schema in REGISTRY.items():
        assert schema.schema_id == schema_id
        assert "@" in schema_id, "a schema identifier carries its version"
