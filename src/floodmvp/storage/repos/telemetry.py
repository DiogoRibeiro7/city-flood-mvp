from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import TelemetryObservation, TelemetryQaDaily


ALLOWED_AGG = {"avg", "min", "max"}
_CAGG_GRANULARITY = {"5m", "5min", "5minutes", "5 minutes"}


async def list_metrics(
    session: AsyncSession, asset_id: str, scenario_id: str | None = None
) -> list[str]:
    scenario_filter = (
        TelemetryObservation.scenario_id == scenario_id
        if scenario_id is not None
        else TelemetryObservation.scenario_id.is_(None)
    )
    res = await session.execute(
        select(TelemetryObservation.metric)
        .where(TelemetryObservation.asset_id == asset_id)
        .where(scenario_filter)
        .distinct()
        .order_by(TelemetryObservation.metric)
    )
    return [r[0] for r in res.all()]


async def resolve_scenario_id(session: AsyncSession, scenario_id: str) -> str | None:
    if scenario_id == "latest":
        res = await session.execute(
            text("SELECT scenario_id FROM scenario_run ORDER BY created_at DESC LIMIT 1")
        )
        row = res.first()
        return row[0] if row else None
    return scenario_id


async def list_scenarios(session: AsyncSession) -> list[dict]:
    res = await session.execute(
        text(
            "SELECT scenario_id, name, start_ts, end_ts "
            "FROM scenario_run ORDER BY created_at DESC"
        )
    )
    return [
        {"scenario_id": r[0], "name": r[1], "start_ts": r[2], "end_ts": r[3]}
        for r in res.all()
    ]


async def list_qa_daily(
    session: AsyncSession,
    city_id: str,
    day: dt.date | None,
) -> list[TelemetryQaDaily]:
    q = select(TelemetryQaDaily).where(TelemetryQaDaily.city_id == city_id)
    if day is not None:
        q = q.where(TelemetryQaDaily.day == day)
    q = q.order_by(TelemetryQaDaily.day.desc(), TelemetryQaDaily.metric)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_observations(
    session: AsyncSession,
    asset_id: str,
    metric: str,
    start: dt.datetime,
    end: dt.datetime,
    granularity: str,
    agg: str,
    include_gaps: bool = False,
    scenario_id: str | None = None,
) -> list[tuple[dt.datetime, float | None]]:
    if agg not in ALLOWED_AGG:
        raise ValueError(f"agg must be one of {sorted(ALLOWED_AGG)}")
    granularity_key = granularity.strip().lower()
    if granularity_key in _CAGG_GRANULARITY and not include_gaps and scenario_id is None:
        agg_col = {
            "avg": "avg_value",
            "min": "min_value",
            "max": "max_value",
        }[agg]
        q = text(
            """
            SELECT bucket, {agg_col}
            FROM telemetry_observation_5m
            WHERE asset_id = :asset_id
              AND metric = :metric
              AND bucket >= :start
              AND bucket < :end
            ORDER BY bucket
            """.format(agg_col=agg_col)
        )
        res = await session.execute(
            q, {"asset_id": asset_id, "metric": metric, "start": start, "end": end}
        )
        return [(r[0], float(r[1])) for r in res.all()]

    scenario_filter = (
        TelemetryObservation.scenario_id == scenario_id
        if scenario_id is not None
        else TelemetryObservation.scenario_id.is_(None)
    )

    if include_gaps:
        # Use Timescale gapfill to surface missing buckets as nulls.
        bucket = func.time_bucket_gapfill(granularity, TelemetryObservation.ts).label("bucket")
        agg_fn = getattr(func, agg)(TelemetryObservation.value).label("value")
        q = (
            select(bucket, agg_fn)
            .where(TelemetryObservation.asset_id == asset_id)
            .where(TelemetryObservation.metric == metric)
            .where(scenario_filter)
            .where(TelemetryObservation.ts >= start)
            .where(TelemetryObservation.ts < end)
            .group_by(bucket)
            .order_by(bucket)
        )
        res = await session.execute(q)
        return [(r[0], float(r[1]) if r[1] is not None else None) for r in res.all()]

    # fallback to raw telemetry with time_bucket
    bucket = func.time_bucket(granularity, TelemetryObservation.ts).label("bucket")
    agg_fn = getattr(func, agg)(TelemetryObservation.value).label("value")
    q = (
        select(bucket, agg_fn)
        .where(TelemetryObservation.asset_id == asset_id)
        .where(TelemetryObservation.metric == metric)
        .where(scenario_filter)
        .where(TelemetryObservation.ts >= start)
        .where(TelemetryObservation.ts < end)
        .group_by(bucket)
        .order_by(bucket)
    )
    res = await session.execute(q)
    return [(r[0], float(r[1])) for r in res.all()]
