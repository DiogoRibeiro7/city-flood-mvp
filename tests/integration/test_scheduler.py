from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.jobs.scheduler import _should_enqueue
from floodmvp.models.db import AnalyticsRun, City, JobQueue
from floodmvp.storage.repos.jobs import enqueue_job


@pytest.mark.parametrize("pending_status", ["queued", "running"])
async def test_scheduler_uses_json_city_scope_and_respects_recent_runs(
    db_session: AsyncSession,
    pending_status: str,
) -> None:
    city_id = "city_scheduler"
    assert await _should_enqueue(db_session, city_id, 60)
    queued = await enqueue_job(db_session, "analytics_run", {"city_id": city_id})
    job = await db_session.get(JobQueue, queued.job_id)
    assert job is not None
    job.status = pending_status
    await db_session.flush()
    assert not await _should_enqueue(db_session, city_id, 60)
    assert await _should_enqueue(db_session, "different_city", 60)

    job.status = "completed"
    await db_session.flush()
    assert await _should_enqueue(db_session, city_id, 60)

    now = dt.datetime.now(dt.UTC)
    db_session.add(City(city_id=city_id, name="Scheduler test", country="PT"))
    await db_session.flush()
    run = AnalyticsRun(
        run_id="scheduler_run",
        city_id=city_id,
        start_ts=now - dt.timedelta(hours=1),
        end_ts=now,
        status="completed",
        version="v1",
        params={},
        metrics={},
    )
    db_session.add(run)
    await db_session.flush()
    assert not await _should_enqueue(db_session, city_id, 60)
    run.end_ts = now - dt.timedelta(hours=2)
    await db_session.flush()
    assert await _should_enqueue(db_session, city_id, 60)
