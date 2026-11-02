"""Verify case-study readback against the real migration head in an isolated child DB."""

import asyncio
from pathlib import Path

from floodmvp.adapters.noaa_ghcnh import GHCNhRequest, acquire
from floodmvp.analytics.rain_intervals import describe_rain_intervals
from scripts import noaa_case_study as case


def test_case_study_ingests_replays_and_analyzes_committed_rows(migrated_db):
    migrated_db.upgrade()
    batch = acquire(
        GHCNhRequest(case.STATION, case.ASSET, case.START, case.END),
        fixture_manifest=Path(__file__).resolve().parents[1]
        / "fixtures/real_sources/noaa_ghcnh/provenance.json",
    )
    records, receipt = asyncio.run(case.ingest_and_readback(migrated_db.url, batch))
    assert receipt["first_import"]["inserted"] == 2
    assert receipt["replay"]["inserted"] == 0 and receipt["replay"]["existing"] == 2
    assert receipt["stored_import_audits"] == 2 and receipt["provenance_preserved"]
    assert receipt["migration_revision"] == "0018_ingest_expiry"
    assert describe_rain_intervals(records, case.START, case.END)["reported_wet_intervals"] == 2
