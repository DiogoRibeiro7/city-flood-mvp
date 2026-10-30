"""Seed fixed smoke data without deleting tables or invoking the demo resetter."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.config.settings import settings
from floodmvp.models.db import Asset, City, TelemetryObservation
from scripts.smoke_fixture import (
    CITY_ID,
    END,
    FIXTURE_VERSION,
    PIPE_ID,
    RAIN_ID,
    RIVER_ID,
    START,
    fixture_digest,
    measurements,
)


def require_smoke_database(database_url: str, app_env: str, project: str) -> None:
    """Reject any target other than the runner's dedicated test database."""
    url = make_url(database_url)
    if (
        app_env != "test"
        or re.fullmatch(r"city-flood-smoke-[a-f0-9]{12}", project) is None
        or url.get_backend_name() != "postgresql"
        or url.host != "db"
        or url.database != "floodmvp_smoke_test"
    ):
        raise ValueError("Smoke seeding requires the isolated Compose test database and project")


async def seed(session: AsyncSession) -> dict[str, int | str]:
    """Insert only fixture IDs; prove that a repeat seed preserves exact input."""
    await session.execute(
        insert(City)
        .values(city_id=CITY_ID, name="Porto (synthetic smoke)", country="PT")
        .on_conflict_do_nothing(index_elements=["city_id"])
    )
    for asset_id, asset_type, geometry in (
        (RAIN_ID, "rain_gauge", "POINT(-8.61 41.15)"),
        (RIVER_ID, "river_gauge", "POINT(-8.612 41.152)"),
        (PIPE_ID, "pipe", "LINESTRING(-8.61 41.15, -8.612 41.152)"),
    ):
        await session.execute(
            insert(Asset)
            .values(
                asset_id=asset_id,
                city_id=CITY_ID,
                asset_type=asset_type,
                name=asset_id,
                geom=WKTElement(geometry, srid=4326),
                props={"fixture": FIXTURE_VERSION},
            )
            .on_conflict_do_nothing(index_elements=["asset_id"])
        )
    rows = [
        {
            **row,
            "ts": dt.datetime.fromisoformat(str(row["ts"])),
            "quality_flag": "ok",
            "source": "synthetic",
            "source_type": "synthetic",
            "source_id": row["asset_id"],
            "lineage": {"fixture": FIXTURE_VERSION, "sha256": fixture_digest()},
        }
        for row in measurements()
    ]
    await session.execute(
        insert(TelemetryObservation)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["asset_id", "metric", "ts"])
    )
    result = await session.execute(
        select(TelemetryObservation).where(
            TelemetryObservation.asset_id.in_([RAIN_ID, RIVER_ID, PIPE_ID])
        )
    )
    actual = {(row.asset_id, row.metric, row.ts.isoformat(), row.value) for row in result.scalars()}
    expected = {(row["asset_id"], row["metric"], row["ts"], row["value"]) for row in measurements()}
    if actual != expected:
        raise ValueError("Stored smoke measurements differ from the deterministic fixture")
    cities = await session.scalar(select(func.count()).select_from(City))
    assets = await session.scalar(select(func.count()).select_from(Asset))
    observations = await session.scalar(select(func.count()).select_from(TelemetryObservation))
    if (cities, assets, observations) != (1, 3, 36):
        raise ValueError("Smoke database contains unexpected data; refusing to reset it")
    await session.commit()
    return {"cities": 1, "assets": 3, "observations": 36, "sha256": fixture_digest()}


async def main(analytics: bool) -> None:
    require_smoke_database(
        settings.database_url, settings.app_env, os.environ.get("SMOKE_PROJECT", "")
    )
    # Import the connection factory only after validating the target.
    from floodmvp.storage.db import SessionLocal

    async with SessionLocal() as session:
        report = await seed(session)
        if analytics:
            from floodmvp.config.cities import get_city_config
            from floodmvp.jobs.run_analytics import run_city_analytics

            city = get_city_config(CITY_ID)
            assert city is not None
            report["analytics_run_id"] = await run_city_analytics(
                session,
                city,
                END,
                START,
                {
                    "rain_event_threshold_mmph": 5.0,
                    "rain_event_min_duration_minutes": 15,
                    "overflow_fill_threshold": 1.0,
                    "overflow_min_duration_minutes": 10,
                    "risk_fill_watch": 1.15,
                    "risk_fill_warning": 1.4,
                },
            )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analytics", action="store_true")
    asyncio.run(main(parser.parse_args().analytics))
