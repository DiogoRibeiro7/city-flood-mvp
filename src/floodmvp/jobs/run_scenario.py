from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from floodmvp.common.ids import new_id
from floodmvp.generators.scenarios import SCENARIOS
from floodmvp.jobs.seed_telemetry import main as seed_telemetry
from floodmvp.models.db import ScenarioRun
from floodmvp.storage.db import SessionLocal


async def run(name: str, days: int) -> None:
    if name not in SCENARIOS:
        raise ValueError(f"scenario name must be one of {sorted(SCENARIOS)}")

    scenario_id = new_id("scenario")
    now = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    start = now - dt.timedelta(days=days)

    async with SessionLocal() as session:
        session.add(
            ScenarioRun(
                scenario_id=scenario_id,
                name=name,
                start_ts=start,
                end_ts=now,
            )
        )
        await session.commit()

    import os
    os.environ["TELEMETRY_SCENARIO"] = name
    await seed_telemetry(scenario_id=scenario_id)

    print(f"Scenario run created: {scenario_id} ({name})")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a telemetry scenario.")
    parser.add_argument("--name", required=True, help="scenario name")
    parser.add_argument("--days", type=int, default=2, help="days of telemetry")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(run(args.name, args.days))
