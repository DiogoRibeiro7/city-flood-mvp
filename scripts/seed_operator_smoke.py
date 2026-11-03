"""Add explicit synthetic comparison data to the owned smoke fixture, never a user DB."""

from __future__ import annotations

import asyncio
import datetime as dt
import os

from floodmvp.config.settings import settings
from floodmvp.models.db import ScenarioRun, TelemetryObservation
from scripts.database_test_support import validate_test_database_url
from scripts.seed_smoke import require_smoke_database, seed
from scripts.smoke_fixture import PIPE_ID, START


async def main() -> None:
    validate_test_database_url(settings.database_url)
    require_smoke_database(
        settings.database_url, settings.app_env, os.environ.get("SMOKE_PROJECT", "")
    )
    from floodmvp.storage.db import SessionLocal

    async with SessionLocal() as session:
        # Verify the exact baseline first. Refuse pre-existing extra records; no resets.
        await seed(session)
        start = START + dt.timedelta(days=1)
        for index, scenario_id in enumerate(("operator-base", "operator-test")):
            session.add(
                ScenarioRun(
                    scenario_id=scenario_id,
                    name=f"Synthetic operator fixture {index + 1}",
                    start_ts=start,
                    end_ts=start + dt.timedelta(hours=1),
                )
            )
            await session.flush()
            for minute in range(0, 60 - 5 * index, 5):
                # Timestamp is part of the existing observation primary key (scenario is not).
                # A one-second offset preserves distinct records in the same five-minute bucket.
                session.add(
                    TelemetryObservation(
                        asset_id=PIPE_ID,
                        metric="fill_ratio",
                        scenario_id=scenario_id,
                        ts=start + dt.timedelta(minutes=minute, seconds=index),
                        value=0.5 + index,
                        quality_flag="suspect" if minute == 15 else "ok",
                        source="synthetic",
                        source_type="synthetic",
                        source_id="operator-smoke-v1",
                        lineage={"fixture": "operator-smoke-v1"},
                    )
                )
        await session.commit()
    print("Added operator-smoke-v1: 2 synthetic scenarios, 23 observations, 2026-01-02 UTC")


if __name__ == "__main__":
    asyncio.run(main())
