"""Build the committed pointing fixture the fake binding runs against.

The fixture is a subsample of the one-year Rubin cadence database that ships inside the
sorcha wheel, extracted with **sorcha's own SQL projection** so the fixture is
schema-identical to what the real binding reads rather than merely similar.

Subsampling is not uniform, and the reason matters. The linking filter requires several
tracklets inside a short tracking window, so a fixture of nights spread evenly across the
year would make linking impossible by construction and the fake would detect nothing.
Nights are therefore drawn in **blocks of consecutive observing nights**, spread across
the year, with a fixed number of visits kept per night.

Run from the repository root:

    uv run python scripts/build_pointing_fixture.py

The output is committed; this script exists so that its provenance is reproducible rather
than asserted.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from etno_twin.kernel.hashing import sha256_file
from etno_twin.kernel.schemas import POINTING_TABLE
from etno_twin.simulators.fake import write_pointing_table
from etno_twin.simulators.sorcha_adapter import resolve_pointing_db

POINTING_SQL = (
    "SELECT observationId, observationStartMJD as observationStartMJD_TAI, visitTime, "
    "visitExposureTime, filter, seeingFwhmGeom as seeingFwhmGeom_arcsec, "
    "seeingFwhmEff as seeingFwhmEff_arcsec, fiveSigmaDepth as fieldFiveSigmaDepth_mag, "
    "fieldRA as fieldRA_deg, fieldDec as fieldDec_deg, rotSkyPos as fieldRotSkyPos_deg "
    "FROM observations order by observationId"
)
"""Copied from the ``pointing_sql_query`` key of the shared configuration file."""

NIGHT_START_UTC_HOURS = 16.0


def _night(mjd: float) -> int:
    return math.floor(mjd - NIGHT_START_UTC_HOURS / 24.0)


def subsample(
    rows: Sequence[dict[str, object]], blocks: int, nights_per_block: int, visits_per_night: int
) -> list[dict[str, object]]:
    by_night: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        by_night.setdefault(_night(float(str(row["observationStartMJD_TAI"]))), []).append(row)
    nights = sorted(by_night)
    span = nights_per_block * blocks
    if len(nights) < span:
        raise SystemExit(f"database has {len(nights)} nights, fixture needs {span}")
    stride = (len(nights) - nights_per_block) // max(blocks - 1, 1)

    selected: list[dict[str, object]] = []
    for block in range(blocks):
        start = block * stride
        for night in nights[start : start + nights_per_block]:
            visits = by_night[night]
            step = max(len(visits) // visits_per_night, 1)
            selected.extend(visits[::step][:visits_per_night])
    return selected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="auto")
    parser.add_argument(
        "--output", type=Path, default=Path("fixtures/pointing/rubin-baseline-1yr-subsample.csv")
    )
    parser.add_argument("--blocks", type=int, default=8)
    parser.add_argument("--nights-per-block", type=int, default=6)
    parser.add_argument("--visits-per-night", type=int, default=10)
    args = parser.parse_args(argv)

    database = resolve_pointing_db(args.source)
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = [dict(row) for row in connection.execute(POINTING_SQL)]
    connection.close()

    selected = subsample(rows, args.blocks, args.nights_per_block, args.visits_per_night)
    write_pointing_table(args.output, selected)
    POINTING_TABLE.read_rows(args.output)

    print(f"source           {database}")
    print(f"source sha256    {sha256_file(database)}")
    print(f"source visits    {len(rows)}")
    print(f"fixture visits   {len(selected)}")
    nights = {_night(float(str(row["observationStartMJD_TAI"]))) for row in selected}
    print(f"fixture nights   {len(nights)}")
    print(f"fixture bytes    {args.output.stat().st_size}")
    print(f"fixture sha256   {sha256_file(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
