from __future__ import annotations

import datetime as dt
import pathlib

from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.config.settings import settings
from floodmvp.models.db import (
    AnalyticsThresholdOverride,
    AnalyticsEvent,
    AnalyticsHotspotDaily,
    AnalyticsRun,
    Asset,
    AssetStatusLatest,
    ExportJob,
    ExportJobLog,
    TelemetryObservation,
)
from floodmvp.models.domain import ExportJobQuery
from floodmvp.common.ids import new_id


async def get_latest_run_id(session: AsyncSession, city_id: str) -> str | None:
    res = await session.execute(
        select(AnalyticsRun.run_id)
        .where(AnalyticsRun.city_id == city_id)
        .order_by(AnalyticsRun.created_at.desc())
        .limit(1)
    )
    row = res.scalar_one_or_none()
    return str(row) if row else None


async def get_run(session: AsyncSession, run_id: str) -> AnalyticsRun | None:
    res = await session.execute(select(AnalyticsRun).where(AnalyticsRun.run_id == run_id))
    return res.scalar_one_or_none()


async def get_city_status(session: AsyncSession, city_id: str) -> dict:
    # cheap summary for dashboards
    now = dt.datetime.now(dt.timezone.utc)
    run_id = await get_latest_run_id(session, city_id)
    if run_id is None:
        return {
            "city_id": city_id,
            "risk": "low",
            "active_events": 0,
            "hotspots": 0,
            "updated_at": now,
        }
    events_res = await session.execute(
        select(func.count(AnalyticsEvent.event_id))
        .where(AnalyticsEvent.city_id == city_id)
        .where(AnalyticsEvent.run_id == run_id)
    )
    active_events = int(events_res.scalar_one() or 0)

    hs_res = await session.execute(
        select(func.count(AnalyticsHotspotDaily.asset_id))
        .where(AnalyticsHotspotDaily.city_id == city_id)
        .where(AnalyticsHotspotDaily.run_id == run_id)
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
    session: AsyncSession,
    city_id: str,
    metric: str,
    top: int,
    run_id: str | None = None,
) -> list[AnalyticsHotspotDaily]:
    if run_id is None:
        run_id = await get_latest_run_id(session, city_id)
    if run_id is None:
        return []
    q = (
        select(AnalyticsHotspotDaily)
        .where(AnalyticsHotspotDaily.city_id == city_id)
        .where(AnalyticsHotspotDaily.run_id == run_id)
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
    run_id: str | None = None,
) -> list[AnalyticsEvent]:
    if run_id is None:
        run_id = await get_latest_run_id(session, city_id)
    if run_id is None:
        return []
    q = (
        select(AnalyticsEvent)
        .where(AnalyticsEvent.city_id == city_id)
        .where(AnalyticsEvent.run_id == run_id)
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


async def add_export_job_log(
    session: AsyncSession,
    job_id: str,
    level: str,
    message: str,
    details: dict | None = None,
) -> None:
    session.add(
        ExportJobLog(
            log_id=new_id("log"),
            job_id=job_id,
            level=level,
            message=message,
            details=details or {},
        )
    )


async def list_export_job_logs(
    session: AsyncSession,
    job_id: str,
    limit: int = 200,
) -> list[ExportJobLog]:
    res = await session.execute(
        select(ExportJobLog)
        .where(ExportJobLog.job_id == job_id)
        .order_by(ExportJobLog.created_at.asc())
        .limit(limit)
    )
    return list(res.scalars().all())


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


def _season_key(ts: dt.datetime) -> str:
    return f"month-{ts.month:02d}"


async def get_threshold_override(
    session: AsyncSession, city_id: str, season: str
) -> AnalyticsThresholdOverride | None:
    res = await session.execute(
        select(AnalyticsThresholdOverride)
        .where(AnalyticsThresholdOverride.city_id == city_id)
        .where(AnalyticsThresholdOverride.season == season)
        .order_by(AnalyticsThresholdOverride.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def list_threshold_overrides(
    session: AsyncSession, city_id: str, limit: int = 50
) -> list[AnalyticsThresholdOverride]:
    res = await session.execute(
        select(AnalyticsThresholdOverride)
        .where(AnalyticsThresholdOverride.city_id == city_id)
        .order_by(AnalyticsThresholdOverride.created_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def create_threshold_override(
    session: AsyncSession, city_id: str, season: str, thresholds: dict, notes: str | None
) -> AnalyticsThresholdOverride:
    row = AnalyticsThresholdOverride(
        override_id=new_id("cal"),
        city_id=city_id,
        season=season,
        thresholds=thresholds,
        notes=notes,
    )
    session.add(row)
    await session.flush()
    return row


async def apply_threshold_overrides(
    session: AsyncSession, city_id: str, thresholds: dict, when: dt.datetime
) -> dict:
    season = _season_key(when)
    override = await get_threshold_override(session, city_id, season)
    if override is None:
        override = await get_threshold_override(session, city_id, "all")
    if override is None:
        return thresholds

    merged = dict(thresholds)
    for k, v in (override.thresholds or {}).items():
        if v is not None:
            merged[k] = v
    return merged


async def _percentiles(
    session: AsyncSession,
    city_id: str,
    asset_type: str,
    metric: str,
    start: dt.datetime,
    end: dt.datetime,
    month: int | None = None,
) -> dict[str, float] | None:
    q = (
        select(
            func.percentile_cont(0.85).within_group(TelemetryObservation.value),
            func.percentile_cont(0.9).within_group(TelemetryObservation.value),
            func.percentile_cont(0.95).within_group(TelemetryObservation.value),
        )
        .join(Asset, Asset.asset_id == TelemetryObservation.asset_id)
        .where(Asset.city_id == city_id)
        .where(Asset.asset_type == asset_type)
        .where(TelemetryObservation.metric == metric)
        .where(TelemetryObservation.ts >= start)
        .where(TelemetryObservation.ts < end)
    )
    if month is not None:
        q = q.where(func.extract("month", TelemetryObservation.ts) == month)
    res = await session.execute(q)
    row = res.first()
    if row is None or row[0] is None:
        return None
    return {"p85": float(row[0]), "p90": float(row[1]), "p95": float(row[2])}


async def calibration_recommendations(
    session: AsyncSession,
    city_id: str,
    start: dt.datetime,
    end: dt.datetime,
    seasonality: str,
    default_thresholds: dict,
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    months = range(1, 13) if seasonality == "monthly" else [None]
    for month in months:
        season = f"month-{month:02d}" if month else "all"
        rain = await _percentiles(
            session, city_id, "rain_gauge", "rain_mmph", start, end, month=month
        )
        fill = await _percentiles(
            session, city_id, "pipe", "fill_ratio", start, end, month=month
        )
        thresholds = dict(default_thresholds)
        if rain:
            thresholds["rain_event_threshold_mmph"] = rain["p90"]
        if fill:
            thresholds["overflow_fill_threshold"] = fill["p95"]
            thresholds["risk_fill_watch"] = fill["p85"]
            thresholds["risk_fill_warning"] = fill["p95"]
        out[season] = thresholds
    return out


async def diff_analytics_runs(
    session: AsyncSession,
    base_run_id: str,
    compare_run_id: str,
    limit: int = 100,
) -> dict:
    base_run = await get_run(session, base_run_id)
    compare_run = await get_run(session, compare_run_id)
    if base_run is None or compare_run is None:
        raise ValueError("run_id not found")
    if base_run.city_id != compare_run.city_id:
        raise ValueError("run_id city mismatch")

    def _metrics_delta(a: dict, b: dict) -> dict:
        out: dict[str, dict] = {}
        keys = set(a.keys()) | set(b.keys())
        for k in keys:
            av = a.get(k)
            bv = b.get(k)
            if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                out[k] = {"base": float(av), "compare": float(bv), "delta": float(bv - av)}
            else:
                out[k] = {"base": av, "compare": bv, "delta": None}
        return out

    base_metrics = base_run.metrics or {}
    compare_metrics = compare_run.metrics or {}

    base_events_res = await session.execute(
        select(AnalyticsEvent).where(AnalyticsEvent.run_id == base_run_id)
    )
    compare_events_res = await session.execute(
        select(AnalyticsEvent).where(AnalyticsEvent.run_id == compare_run_id)
    )
    base_events = list(base_events_res.scalars().all())
    compare_events = list(compare_events_res.scalars().all())

    def _event_key(e: AnalyticsEvent) -> tuple:
        return (
            e.event_type,
            tuple(sorted(e.asset_ids or [])),
            e.start_ts,
            e.end_ts,
        )

    base_event_map = {_event_key(e): e for e in base_events}
    compare_event_map = {_event_key(e): e for e in compare_events}
    base_keys = set(base_event_map.keys())
    compare_keys = set(compare_event_map.keys())

    added_keys = list(compare_keys - base_keys)
    removed_keys = list(base_keys - compare_keys)

    added_events = [compare_event_map[k] for k in added_keys[:limit]]
    removed_events = [base_event_map[k] for k in removed_keys[:limit]]

    base_hotspots_res = await session.execute(
        select(AnalyticsHotspotDaily).where(AnalyticsHotspotDaily.run_id == base_run_id)
    )
    compare_hotspots_res = await session.execute(
        select(AnalyticsHotspotDaily).where(AnalyticsHotspotDaily.run_id == compare_run_id)
    )
    base_hotspots = list(base_hotspots_res.scalars().all())
    compare_hotspots = list(compare_hotspots_res.scalars().all())

    def _hotspot_key(h: AnalyticsHotspotDaily) -> tuple:
        return (h.metric, h.asset_id, h.day)

    base_hotspot_map = {_hotspot_key(h): h for h in base_hotspots}
    compare_hotspot_map = {_hotspot_key(h): h for h in compare_hotspots}
    base_hs_keys = set(base_hotspot_map.keys())
    compare_hs_keys = set(compare_hotspot_map.keys())

    added_hs_keys = list(compare_hs_keys - base_hs_keys)
    removed_hs_keys = list(base_hs_keys - compare_hs_keys)
    changed_keys = list(base_hs_keys & compare_hs_keys)

    changed = []
    for k in changed_keys:
        before = base_hotspot_map[k].score
        after = compare_hotspot_map[k].score
        if before != after:
            changed.append((k, before, after))
    changed.sort(key=lambda x: abs(float(x[2]) - float(x[1])), reverse=True)

    def _hotspot_entry(h, before=None, after=None) -> dict:
        if before is None:
            before = h.score if h is not None else None
        if after is None:
            after = h.score if h is not None else None
        delta = None
        if before is not None and after is not None:
            delta = float(after - before)
        return {
            "asset_id": h.asset_id if h is not None else None,
            "metric": h.metric if h is not None else None,
            "day": h.day if h is not None else None,
            "score_before": float(before) if before is not None else None,
            "score_after": float(after) if after is not None else None,
            "delta": delta,
        }

    changed_out = []
    for k, before, after in changed[:limit]:
        h = compare_hotspot_map[k]
        changed_out.append(_hotspot_entry(h, before=before, after=after))

    added_out = [_hotspot_entry(compare_hotspot_map[k]) for k in added_hs_keys[:limit]]
    removed_out = [_hotspot_entry(base_hotspot_map[k]) for k in removed_hs_keys[:limit]]

    return {
        "city_id": base_run.city_id,
        "base_run_id": base_run.run_id,
        "compare_run_id": compare_run.run_id,
        "base_version": base_run.version,
        "compare_version": compare_run.version,
        "metrics_delta": _metrics_delta(base_metrics, compare_metrics),
        "events": {
            "base_count": len(base_events),
            "compare_count": len(compare_events),
            "added": added_events,
            "removed": removed_events,
        },
        "hotspots": {
            "base_count": len(base_hotspots),
            "compare_count": len(compare_hotspots),
            "changed": changed_out,
            "added": added_out,
            "removed": removed_out,
        },
    }


async def run_export_csv(
    session: AsyncSession, job_id: str, query: ExportJobQuery
) -> tuple[str, int]:
    export_dir = pathlib.Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{job_id}.csv"

    asset_ids = list(query.asset_ids)
    if not asset_ids and query.city_id:
        asset_q = select(Asset.asset_id).where(Asset.city_id == query.city_id)
        if query.asset_type:
            asset_q = asset_q.where(Asset.asset_type == query.asset_type)
        res_assets = await session.execute(asset_q)
        asset_ids = [r[0] for r in res_assets.all()]

    if not asset_ids:
        with file_path.open("w", encoding="utf-8") as f:
            f.write("asset_id,metric,ts,value\n")
        return str(file_path), 0

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
            "asset_ids": asset_ids,
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
