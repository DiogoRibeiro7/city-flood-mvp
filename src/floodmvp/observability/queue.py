"""Read committed backlog independently of worker progress, with bounded query time."""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import JobQueue
from floodmvp.observability.metrics import (
    JOB_TYPES,
    QUEUE_COLLECTION_SUCCESS,
    QUEUE_COLLECTION_TIMESTAMP,
    QUEUE_DUE,
    QUEUE_OLDEST,
)


async def collect_queue_snapshot(session: AsyncSession) -> None:
    """Retain old values on failure but mark them unusable; never make failed reads look empty."""
    now = dt.datetime.now(dt.UTC)
    kind = case((JobQueue.job_type.in_(JOB_TYPES), JobQueue.job_type), else_="other")
    query = (
        select(kind, func.count(), func.min(JobQueue.scheduled_at))
        .where(JobQueue.status.in_(("queued", "running")), JobQueue.scheduled_at <= now)
        .group_by(kind)
    )
    try:
        async with asyncio.timeout(2):
            await session.execute(text("SET LOCAL statement_timeout = '1500ms'"))
            rows = (await session.execute(query)).all()
    except Exception:
        QUEUE_COLLECTION_SUCCESS.set(0)
        return
    values = {
        kind: (count, max(0.0, (now - oldest).total_seconds())) for kind, count, oldest in rows
    }
    for label in JOB_TYPES:
        count, age = values.get(label, (0, 0.0))
        QUEUE_DUE.labels(job_type=label).set(count)
        QUEUE_OLDEST.labels(job_type=label).set(age)
    QUEUE_COLLECTION_TIMESTAMP.set(now.timestamp())
    QUEUE_COLLECTION_SUCCESS.set(1)
