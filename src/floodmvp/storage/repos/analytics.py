from __future__ import annotations

import datetime as dt
import pathlib

from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.config.settings import settings
from floodmvp.models.db import (
    AnalyticsEvent,
    AnalyticsHotspotDaily,
    AnalyticsRun,
    Asset,
    AssetStatusLatest,
    ExportJob,
    TelemetryObservation,
)
from floodmvp.models.domain import ExportJobQuery


async def get_city_status(session: AsyncSession, city_id: str) -> dict:
    # cheap summary for dashboards
    now = dt.datetime.now(dt.timezone.utc)
    events_res = await session.execute(
        select(func.count(AnalyticsEvent.event_id)).where(AnalyticsEvent.city_id == city_id)
    )
    active_events = int(events_res.scalar_one() or 0)

    hs_res = await session.execute(
        select(func.count(AnalyticsHotspotDaily.asset_id)).where(AnalyticsHotspotDaily.city_id == city_id)
    )
    hotspots = int(hs_res.scalar_one() or 0)

    # risk based on count of "warning" assets
    warn_res = await session.execute(
        select(func.count(AssetStatusLatest.asset_id)).where(
            and_(AssetStatusLatest.city_id == city_id, AssetStatusLatest.status == "warning")
        )
    )
    warn_assets = int(warn_res.scalar_one() or 0)
    if warn_assets >= 20:
        risk = "high"
    elif warn_assets >= 5:
        risk = "medium"
    else:
        risk = "low"

    return {
        "city_id": city_id,
        "risk": risk,
        "active_events": active_events,
        "hotspots": hotspots,
        "updated_at": now,
    }


async def list_hotspots(
    session: AsyncSession, city_id: str, metric: str, top: int
) -> list[AnalyticsHotspotDaily]:
    q = (
        select(AnalyticsHotspotDaily)
        .where(AnalyticsHotspotDaily.city_id == city_id)
        .where(AnalyticsHotspotDaily.metric == metric)
        .order_by(desc(AnalyticsHotspotDaily.score))
        .limit(top)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def list_events(
    session: AsyncSession,
    city_id: str,
    event_type: str | None,
    start: dt.datetime,
    end: dt.datetime,
    limit: int,
    offset: int,
) -> list[AnalyticsEvent]:
    q = (
        select(AnalyticsEvent)
        .where(AnalyticsEvent.city_id == city_id)
        .where(AnalyticsEvent.start_ts < end)
        .where(AnalyticsEvent.end_ts >= start)
    )
    if event_type:
        q = q.where(AnalyticsEvent.event_type == event_type)
    q = q.order_by(desc(AnalyticsEvent.start_ts)).offset(offset).limit(limit)
    res = await session.execute(q)
    return list(res.scalars().all())


async def create_export_job(session: AsyncSession, job: ExportJob) -> None:
    session.add(job)
    await session.flush()


async def update_export_job(
    session: AsyncSession,
    job_id: str,
    status: str,
    progress: float,
    file_path: str | None = None,
    error_message: str | None = None,
    started_at: dt.datetime | None = None,
    completed_at: dt.datetime | None = None,
    row_count: int | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE export_job
            SET status = :status,
                progress = :progress,
                file_path = :file_path,
                error_message = :error_message,
                started_at = COALESCE(:started_at, started_at),
                completed_at = COALESCE(:completed_at, completed_at),
                row_count = COALESCE(:row_count, row_count),
                updated_at = now()
            WHERE job_id = :job_id
            """
        ),
        {
            "status": status,
            "progress": progress,
            "file_path": file_path,
            "error_message": error_message,
            "started_at": started_at,
            "completed_at": completed_at,
            "row_count": row_count,
            "job_id": job_id,
        },
    )


async def get_export_job(session: AsyncSession, job_id: str) -> ExportJob | None:
    res = await session.execute(select(ExportJob).where(ExportJob.job_id == job_id))
    return res.scalar_one_or_none()


async def list_analytics_runs(
    session: AsyncSession, city_id: str, limit: int = 50
) -> list[AnalyticsRun]:
    res = await session.execute(
        select(AnalyticsRun)
        .where(AnalyticsRun.city_id == city_id)
        .order_by(AnalyticsRun.created_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def run_export_csv(
    session: AsyncSession, job_id: str, query: ExportJobQuery
) -> tuple[str, int]:
    export_dir = pathlib.Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{job_id}.csv"

    q = text(
        """
        SELECT asset_id,
               metric,
               time_bucket(:granularity, ts) AS bucket,
               {agg}(value) AS value
        FROM telemetry_observation
        WHERE asset_id = ANY(:asset_ids)
          AND metric = :metric
          AND ts >= :start
          AND ts < :end
          AND scenario_id IS NULL
        GROUP BY asset_id, metric, bucket
        ORDER BY asset_id, bucket
        """.format(agg=query.agg)
    )
    res = await session.execute(
        q,
        {
            "asset_ids": query.asset_ids,
            "metric": query.metric,
            "start": query.from_ts,
            "end": query.to_ts,
            "granularity": query.granularity,
        },
    )
    rows = res.all()

    # write CSV
    with file_path.open("w", encoding="utf-8") as f:
        f.write("asset_id,metric,ts,value\n")
        for asset_id, metric, bucket, value in rows:
            val_str = "" if value is None else str(float(value))
            f.write(f"{asset_id},{metric},{bucket.isoformat()},{val_str}\n")

    return str(file_path), len(rows)


async def get_city_summary(session: AsyncSession, city_id: str, minutes: int) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(minutes=minutes)

    rain_avg = await session.scalar(
        select(func.avg(TelemetryObservation.value))
        .join(Asset, Asset.asset_id == TelemetryObservation.asset_id)
        .where(Asset.city_id == city_id)
        .where(Asset.asset_type == "rain_gauge")
        .where(TelemetryObservation.metric == "rain_mmph")
        .where(TelemetryObservation.ts >= start)
        .where(TelemetryObservation.ts <= now)
    )
    river_avg = await session.scalar(
        select(func.avg(TelemetryObservation.value))
        .join(Asset, Asset.asset_id == TelemetryObservation.asset_id)
        .where(Asset.city_id == city_id)
        .where(Asset.asset_type == "river_gauge")
        .where(TelemetryObservation.metric == "water_level_m")
        .where(TelemetryObservation.ts >= start)
        .where(TelemetryObservation.ts <= now)
    )

    status_rows = await session.execute(
        select(AssetStatusLatest.status, func.count(AssetStatusLatest.asset_id))
        .where(AssetStatusLatest.city_id == city_id)
        .group_by(AssetStatusLatest.status)
    )
    status_counts = {"normal": 0, "watch": 0, "warning": 0}
    for status, count in status_rows.all():
        if status in status_counts:
            status_counts[status] = int(count)

    return {
        "city_id": city_id,
        "now": now,
        "rain_mmph": float(rain_avg) if rain_avg is not None else 0.0,
        "river_level_m": float(river_avg) if river_avg is not None else 0.0,
        "status_counts": status_counts,
    }
