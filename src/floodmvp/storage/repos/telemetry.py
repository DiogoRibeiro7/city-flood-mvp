from __future__ import annotations

import datetime as dt
import math
from typing import Any, cast

from sqlalchemy import DateTime, Interval, bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.time import parse_bucket_interval
from floodmvp.models.db import ScenarioRun, TelemetryObservation, TelemetryQaDaily

ALLOWED_AGG = {"avg", "min", "max"}
_CAGG_GRANULARITY = {"5m", "5min", "5minutes", "5 minutes"}
_MAX_GAP_BUCKETS = 10_000


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
    """Resolve ``latest`` or check that an explicitly named scenario exists."""
    if scenario_id == "latest":
        query = (
            select(ScenarioRun.scenario_id)
            .order_by(ScenarioRun.created_at.desc(), ScenarioRun.scenario_id.desc())
            .limit(1)
        )
    else:
        query = select(ScenarioRun.scenario_id).where(ScenarioRun.scenario_id == scenario_id)
    # SQLAlchemy's async scalar method is typed as Any by some mypy versions.
    return cast(str | None, await session.scalar(query))


async def list_scenarios(session: AsyncSession) -> list[dict[str, Any]]:
    res = await session.execute(
        text(
            "SELECT scenario_id, name, start_ts, end_ts FROM scenario_run ORDER BY created_at DESC"
        )
    )
    return [
        {"scenario_id": r[0], "name": r[1], "start_ts": r[2], "end_ts": r[3]} for r in res.all()
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
    interval = parse_bucket_interval(granularity)
    granularity_key = granularity.strip().lower()
    if granularity_key in _CAGG_GRANULARITY and not include_gaps and scenario_id is None:
        agg_col = {
            "avg": "avg_value",
            "min": "min_value",
            "max": "max_value",
        }[agg]
        q_text = text(
            f"""
            SELECT bucket, {agg_col}
            FROM telemetry_observation_5m
            WHERE asset_id = :asset_id
              AND metric = :metric
              AND bucket >= :start
              AND bucket < :end
            ORDER BY bucket
            """
        )
        res = await session.execute(
            q_text, {"asset_id": asset_id, "metric": metric, "start": start, "end": end}
        )
        return [(r[0], float(r[1])) for r in res.all()]

    scenario_filter = (
        TelemetryObservation.scenario_id == scenario_id
        if scenario_id is not None
        else TelemetryObservation.scenario_id.is_(None)
    )
    bucket_interval = bindparam("bucket_interval", value=interval, type_=Interval())

    if include_gaps:
        # Bound the generated grid before querying to avoid unbounded responses.
        if math.ceil((end - start) / interval) + 1 > _MAX_GAP_BUCKETS:
            raise ValueError(f"include_gaps supports at most {_MAX_GAP_BUCKETS} buckets")

        # Generate the full grid in PostgreSQL. TimescaleDB's gapfill function
        # is unavailable in the project's Apache-licensed OSS image.
        first_bucket = func.time_bucket(
            bucket_interval, bindparam("gap_start", start, type_=DateTime(timezone=True))
        )
        last_bucket = func.time_bucket(
            bucket_interval,
            bindparam("gap_end", end - dt.timedelta(microseconds=1), type_=DateTime(timezone=True)),
        )
        buckets = select(
            func.generate_series(first_bucket, last_bucket, bucket_interval).label("bucket")
        ).subquery("buckets")
        bucket = func.time_bucket(bucket_interval, TelemetryObservation.ts).label("bucket")
        agg_fn = getattr(func, agg)(TelemetryObservation.value).label("value")
        observed = (
            select(bucket, agg_fn)
            .where(TelemetryObservation.asset_id == asset_id)
            .where(TelemetryObservation.metric == metric)
            .where(scenario_filter)
            .where(TelemetryObservation.ts >= start)
            .where(TelemetryObservation.ts < end)
            .group_by(bucket)
            .subquery("observed")
        )
        q_gap = (
            select(buckets.c.bucket, observed.c.value)
            .select_from(buckets.outerjoin(observed, buckets.c.bucket == observed.c.bucket))
            .order_by(buckets.c.bucket)
        )
        res = await session.execute(q_gap)
        return [(r[0], float(r[1]) if r[1] is not None else None) for r in res.all()]

    # fallback to raw telemetry with time_bucket
    bucket = func.time_bucket(bucket_interval, TelemetryObservation.ts).label("bucket")
    agg_fn = getattr(func, agg)(TelemetryObservation.value).label("value")
    q_raw = (
        select(bucket, agg_fn)
        .where(TelemetryObservation.asset_id == asset_id)
        .where(TelemetryObservation.metric == metric)
        .where(scenario_filter)
        .where(TelemetryObservation.ts >= start)
        .where(TelemetryObservation.ts < end)
        .group_by(bucket)
        .order_by(bucket)
    )
    res = await session.execute(q_raw)
    return [(r[0], float(r[1])) for r in res.all()]


async def get_observations_map(
    session: AsyncSession,
    asset_id: str,
    metric: str,
    start: dt.datetime,
    end: dt.datetime,
    granularity: str,
    agg: str,
    scenario_id: str | None = None,
) -> dict[dt.datetime, float | None]:
    rows = await get_observations(
        session,
        asset_id,
        metric,
        start,
        end,
        granularity,
        agg,
        include_gaps=True,
        scenario_id=scenario_id,
    )
    return {t: v for t, v in rows}
