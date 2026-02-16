from __future__ import annotations

import argparse
import asyncio

from floodmvp.config.cities import get_city_configs
from floodmvp.storage.db import SessionLocal
from floodmvp.storage.repos.jobs import enqueue_job


async def run() -> int:
    parser = argparse.ArgumentParser(description="Enqueue analytics runs")
    parser.add_argument("--city-id", help="Limit to a single city")
    args = parser.parse_args()

    cities = get_city_configs(args.city_id)
    if not cities:
        raise ValueError("No cities matched")

    async with SessionLocal() as session:
        for city in cities:
            await enqueue_job(session, job_type="analytics_run", payload={"city_id": city.city_id})
        await session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
