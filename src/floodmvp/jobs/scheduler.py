from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from sqlalchemy import select

from floodmvp.config.cities import get_city_configs
from floodmvp.models.db import AnalyticsRun, JobQueue
from floodmvp.storage.db import SessionLocal
from floodmvp.storage.repos.jobs import enqueue_job


async def _should_enqueue(session, city_id: str, interval_minutes: int) -> bool:
    queued = await session.execute(
        select(JobQueue.job_id)
        .where(JobQueue.job_type == "analytics_run")
        .where(JobQueue.status.in_(["queued", "running"]))
        .where(JobQueue.payload["city_id"].astext == city_id)
        .limit(1)
    )
    if queued.scalar_one_or_none() is not None:
        return False
    res = await session.execute(
        select(AnalyticsRun.end_ts)
        .where(AnalyticsRun.city_id == city_id)
        .order_by(AnalyticsRun.end_ts.desc())
        .limit(1)
    )
    row = res.scalar_one_or_none()
    if row is None:
        return True
    return row < dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=interval_minutes)


async def run(interval_minutes: int, poll_seconds: int) -> None:
    while True:
        cities = get_city_configs()
        async with SessionLocal() as session:
            for city in cities:
                if await _should_enqueue(session, city.city_id, interval_minutes):
                    await enqueue_job(
                        session,
                        job_type="analytics_run",
                        payload={"city_id": city.city_id},
                    )
            await session.commit()
        await asyncio.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Periodic analytics scheduler")
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()

    asyncio.run(run(args.interval_minutes, args.poll_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
