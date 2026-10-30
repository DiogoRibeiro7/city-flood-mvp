"""Maintenance operations for durable ingestion idempotency keys."""

from __future__ import annotations

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import IngestIdempotency


async def prune_expired_idempotency(session: AsyncSession, *, batch_size: int = 500) -> int:
    """Delete at most ``batch_size`` keys older than seven days.

    PostgreSQL row-level locks and ``SKIP LOCKED`` prevent the maintenance
    process from waiting on keys being handled by concurrent ingestion requests.
    The caller owns the transaction and must commit it.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")

    expired_keys = (
        select(IngestIdempotency.idempotency_key)
        .where(IngestIdempotency.created_at < func.now() - text("interval '7 days'"))
        .order_by(IngestIdempotency.created_at, IngestIdempotency.idempotency_key)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
        .cte("expired_ingest_keys")
    )
    deleted = await session.execute(
        delete(IngestIdempotency).where(
            IngestIdempotency.idempotency_key.in_(select(expired_keys.c.idempotency_key))
        )
    )
    return max(int(getattr(deleted, "rowcount", 0) or 0), 0)
