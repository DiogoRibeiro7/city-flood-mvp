"""Verify claimed, retried, and completed worker locks in PostgreSQL."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import JobQueue
from floodmvp.storage.repos.jobs import fetch_next_job, mark_job_failed, mark_job_success


@pytest.mark.asyncio
async def test_worker_lock_lifecycle_persists_in_database(db_session: AsyncSession) -> None:
    """A retried/completed job must not retain the claiming worker's lock."""
    now = dt.datetime.now(dt.UTC)
    job = JobQueue(
        job_id="job_lock_lifecycle",
        job_type="export_csv",
        status="queued",
        payload={},
        attempts=0,
        max_attempts=2,
        scheduled_at=now - dt.timedelta(minutes=1),
    )
    db_session.add(job)
    await db_session.commit()

    claimed = await fetch_next_job(db_session, "worker-first")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.locked_by == "worker-first"
    assert claimed.locked_at is not None

    await mark_job_failed(db_session, claimed, "temporary failure", backoff_seconds=0)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == "queued"
    assert job.locked_at is None
    assert job.locked_by is None
    assert job.last_error == "temporary failure"

    claimed_again = await fetch_next_job(db_session, "worker-second")
    assert claimed_again is not None
    assert claimed_again.job_id == job.job_id
    assert claimed_again.attempts == 2
    assert claimed_again.locked_by == "worker-second"

    await mark_job_success(db_session, claimed_again)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == "completed"
    assert job.locked_at is None
    assert job.locked_by is None
    assert job.last_error is None


@pytest.mark.asyncio
async def test_exhausted_job_releases_worker_lock(db_session: AsyncSession) -> None:
    """Terminal failed jobs must release their lock and retain the error."""
    job = JobQueue(
        job_id="job_terminal_failure",
        job_type="analytics_run",
        status="queued",
        payload={},
        attempts=0,
        max_attempts=1,
        scheduled_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
    )
    db_session.add(job)
    await db_session.commit()

    claimed = await fetch_next_job(db_session, "worker-final")
    assert claimed is not None
    assert claimed.job_id == job.job_id
    await mark_job_failed(db_session, claimed, "unrecoverable failure", backoff_seconds=15)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.status == "failed"
    assert job.locked_at is None
    assert job.locked_by is None
    assert job.last_error == "unrecoverable failure"
