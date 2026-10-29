"""Queue transitions must never expose a stale active worker lock."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import JobQueue
from floodmvp.storage.repos.jobs import mark_job_failed, mark_job_success


def running_job(attempts: int = 1, max_attempts: int = 3) -> JobQueue:
    """Construct an already claimed job with explicit lock metadata."""
    now = dt.datetime(2026, 10, 29, tzinfo=dt.UTC)
    return JobQueue(
        job_id="job_lock_test",
        job_type="export_csv",
        status="running",
        payload={},
        attempts=attempts,
        max_attempts=max_attempts,
        scheduled_at=now,
        locked_at=now,
        locked_by="worker-a",
        last_error="old error",
    )


@pytest.mark.asyncio
async def test_success_clears_worker_lock_and_previous_error() -> None:
    session = AsyncMock(spec=AsyncSession)
    job = running_job()

    await mark_job_success(session, job)

    assert job.status == "completed"
    assert job.locked_at is None
    assert job.locked_by is None
    assert job.last_error is None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempts", "max_attempts", "expected_status"),
    [(1, 3, "queued"), (3, 3, "failed")],
)
async def test_failure_releases_lock_for_retries_and_exhausted_jobs(
    attempts: int, max_attempts: int, expected_status: str
) -> None:
    session = AsyncMock(spec=AsyncSession)
    job = running_job(attempts=attempts, max_attempts=max_attempts)
    original_schedule = job.scheduled_at

    await mark_job_failed(session, job, error="temporary outage", backoff_seconds=10)

    assert job.status == expected_status
    assert job.locked_at is None
    assert job.locked_by is None
    assert job.last_error == "temporary outage"
    if expected_status == "queued":
        assert job.scheduled_at > original_schedule
    else:
        assert job.scheduled_at == original_schedule
    session.flush.assert_awaited_once()
