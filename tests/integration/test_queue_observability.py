"""Actual committed backlog semantics on the guarded isolated PostgreSQL server."""

import datetime as dt

from prometheus_client import REGISTRY

from floodmvp.models.db import JobQueue
from floodmvp.observability.queue import collect_queue_snapshot


async def test_due_snapshot_excludes_future_and_terminal_work_and_bounds_types(db_session):
    now = dt.datetime.now(dt.UTC)
    for name, kind, status, seconds in (
        ("due", "analytics_run", "queued", -700),
        ("running", "analytics_run", "running", -400),
        ("future", "analytics_run", "queued", 600),
        ("done", "analytics_run", "completed", -2000),
        ("cancelled", "analytics_run", "cancelled", -3000),
        ("private", "private-user-type", "queued", -100),
    ):
        db_session.add(
            JobQueue(
                job_id=name,
                job_type=kind,
                status=status,
                payload={},
                attempts=0,
                max_attempts=3,
                scheduled_at=now + dt.timedelta(seconds=seconds),
            )
        )
    await db_session.commit()
    await collect_queue_snapshot(db_session)
    assert REGISTRY.get_sample_value("job_queue_collection_success") == 1
    assert REGISTRY.get_sample_value("job_queue_due_jobs", {"job_type": "analytics_run"}) == 2
    assert REGISTRY.get_sample_value("job_queue_due_jobs", {"job_type": "other"}) == 1
    assert REGISTRY.get_sample_value("job_queue_due_jobs", {"job_type": "export_csv"}) == 0
    age = REGISTRY.get_sample_value(
        "job_queue_oldest_due_age_seconds", {"job_type": "analytics_run"}
    )
    assert 700 <= age < 730
