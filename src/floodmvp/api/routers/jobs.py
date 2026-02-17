from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.errors import AppError
from floodmvp.config.settings import settings
from floodmvp.models.domain import JobQueueOut
from floodmvp.storage.db import get_session
from floodmvp.models.db import JobQueue
from floodmvp.storage.repos.jobs import cancel_job, get_job, list_jobs, retry_job

router = APIRouter(tags=["jobs"])


def _require_admin_key(x_api_key: str | None) -> None:
    if not settings.analytics_api_key:
        return
    if not x_api_key:
        raise AppError(code="UNAUTHORIZED", message="Missing API key", status_code=401)
    if x_api_key != settings.analytics_api_key:
        raise AppError(code="FORBIDDEN", message="Invalid API key", status_code=403)


def _to_out(job: JobQueue) -> JobQueueOut:
    return JobQueueOut(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        payload=job.payload or {},
        attempts=int(job.attempts or 0),
        max_attempts=int(job.max_attempts or 0),
        scheduled_at=job.scheduled_at,
        locked_at=job.locked_at,
        locked_by=job.locked_by,
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs/queue", response_model=list[JobQueueOut])
async def queue_list(
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> list[JobQueueOut]:
    _require_admin_key(x_api_key)
    rows = await list_jobs(session, status=status, job_type=job_type, limit=limit)
    return [_to_out(j) for j in rows]


@router.get("/jobs/queue/{job_id}", response_model=JobQueueOut)
async def queue_get(
    job_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> JobQueueOut:
    _require_admin_key(x_api_key)
    job = await get_job(session, job_id)
    if job is None:
        raise AppError(code="JOB_NOT_FOUND", message="Job not found", status_code=404)
    return _to_out(job)


@router.post("/jobs/queue/{job_id}/retry", response_model=JobQueueOut)
async def queue_retry(
    job_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> JobQueueOut:
    _require_admin_key(x_api_key)
    updated = await retry_job(session, job_id)
    if not updated:
        raise AppError(code="JOB_NOT_RETRYABLE", message="Job not retryable", status_code=400)
    await session.commit()
    job = await get_job(session, job_id)
    assert job is not None
    return _to_out(job)


@router.post("/jobs/queue/{job_id}/cancel", response_model=JobQueueOut)
async def queue_cancel(
    job_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> JobQueueOut:
    _require_admin_key(x_api_key)
    updated = await cancel_job(session, job_id)
    if not updated:
        raise AppError(code="JOB_NOT_CANCELLABLE", message="Job not cancellable", status_code=400)
    await session.commit()
    job = await get_job(session, job_id)
    assert job is not None
    return _to_out(job)
