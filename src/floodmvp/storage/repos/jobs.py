from __future__ import annotations

import datetime as dt
import os
import socket
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.ids import new_id
from floodmvp.models.db import JobQueue
from floodmvp.observability.metrics import JOB_COMPLETED, JOB_ENQUEUED, JOB_FAILED, JOB_RETRIED


@dataclass(frozen=True)
class EnqueuedJob:
    job_id: str
    job_type: str
    payload: dict


async def enqueue_job(
    session: AsyncSession,
    job_type: str,
    payload: dict,
    max_attempts: int = 5,
    run_at: dt.datetime | None = None,
) -> EnqueuedJob:
    if run_at is None:
        run_at = dt.datetime.now(dt.UTC)
    job_id = new_id("job")
    session.add(
        JobQueue(
            job_id=job_id,
            job_type=job_type,
            status="queued",
            payload=payload,
            attempts=0,
            max_attempts=max_attempts,
            scheduled_at=run_at,
        )
    )
    await session.flush()
    JOB_ENQUEUED.labels(job_type=job_type).inc()
    return EnqueuedJob(job_id=job_id, job_type=job_type, payload=payload)


async def fetch_next_job(session: AsyncSession, worker_id: str) -> JobQueue | None:
    now = dt.datetime.now(dt.UTC)
    q = (
        select(JobQueue)
        .where(JobQueue.status == "queued")
        .where(JobQueue.scheduled_at <= now)
        .order_by(JobQueue.scheduled_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    res = await session.execute(q)
    job = res.scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts = int(job.attempts or 0) + 1
    await session.flush()
    return job


async def mark_job_success(session: AsyncSession, job: JobQueue) -> None:
    job.status = "completed"
    job.last_error = None
    await session.flush()
    JOB_COMPLETED.labels(job_type=job.job_type).inc()


async def mark_job_failed(session: AsyncSession, job: JobQueue, error: str, backoff_seconds: int) -> None:
    job.last_error = error
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        JOB_FAILED.labels(job_type=job.job_type).inc()
    else:
        job.status = "queued"
        job.scheduled_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=backoff_seconds)
        JOB_RETRIED.labels(job_type=job.job_type).inc()
    await session.flush()


async def list_jobs(
    session: AsyncSession,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 100,
) -> list[JobQueue]:
    q = select(JobQueue).order_by(JobQueue.created_at.desc()).limit(limit)
    if status:
        q = q.where(JobQueue.status == status)
    if job_type:
        q = q.where(JobQueue.job_type == job_type)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_job(session: AsyncSession, job_id: str) -> JobQueue | None:
    res = await session.execute(select(JobQueue).where(JobQueue.job_id == job_id))
    return res.scalar_one_or_none()


async def retry_job(session: AsyncSession, job_id: str) -> bool:
    now = dt.datetime.now(dt.UTC)
    res = await session.execute(
        update(JobQueue)
        .where(JobQueue.job_id == job_id)
        .where(JobQueue.status.in_(["failed", "cancelled"]))
        .values(status="queued", attempts=0, last_error=None, scheduled_at=now, locked_at=None, locked_by=None)
    )
    return (res.rowcount or 0) > 0


async def cancel_job(session: AsyncSession, job_id: str) -> bool:
    res = await session.execute(
        update(JobQueue)
        .where(JobQueue.job_id == job_id)
        .where(JobQueue.status == "queued")
        .values(status="cancelled", locked_at=None, locked_by=None)
    )
    return (res.rowcount or 0) > 0


def build_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"
