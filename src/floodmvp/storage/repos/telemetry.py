from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import TelemetryObservation


ALLOWED_AGG = {"avg", "min", "max"}


async def list_metrics(session: AsyncSession, asset_id: str) -> list[str]:
    res = await session.execute(
        select(TelemetryObservation.metric)
        .where(TelemetryObservation.asset_id == asset_id)
        .distinct()
        .order_by(TelemetryObservation.metric)
    )
    return [r[0] for r in res.all()]


async def get_observations(
    session: AsyncSession,
    asset_id: str,
    metric: str,
    start: dt.datetime,
    end: dt.datetime,
    granularity: str,
    agg: str,
) -> list[tuple[dt.datetime, float]]:
    if agg not in ALLOWED_AGG:
        raise ValueError(f"agg must be one of {sorted(ALLOWED_AGG)}")
    # timescaledb time_bucket
    bucket = func.time_bucket(granularity, TelemetryObservation.ts).label("bucket")
    agg_fn = getattr(func, agg)(TelemetryObservation.value).label("value")
    q = (
        select(bucket, agg_fn)
        .where(TelemetryObservation.asset_id == asset_id)
        .where(TelemetryObservation.metric == metric)
        .where(TelemetryObservation.ts >= start)
        .where(TelemetryObservation.ts < end)
        .group_by(bucket)
        .order_by(bucket)
    )
    res = await session.execute(q)
    return [(r[0], float(r[1])) for r in res.all()]
