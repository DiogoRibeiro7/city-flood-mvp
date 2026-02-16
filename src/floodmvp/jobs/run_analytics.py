from __future__ import annotations

import asyncio
import datetime as dt

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.analytics.hotspots import overflow_minutes_score
from floodmvp.analytics.overflow_events import detect_overflow_events
from floodmvp.analytics.rain_events import detect_rain_events
from floodmvp.analytics.status import risk_from_fill
from floodmvp.common.ids import new_id
from floodmvp.config.cities import get_city_configs
from floodmvp.config.settings import settings
from floodmvp.models.db import (
    AnalyticsEvent,
    AnalyticsHotspotDaily,
    AnalyticsRun,
    Asset,
    AssetStatusLatest,
    TelemetryObservation,
)
from floodmvp.storage.db import SessionLocal
from floodmvp.storage.repos.analytics import apply_threshold_overrides


def _clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


def _coverage_ratio(
    df: pd.DataFrame, start: dt.datetime, end: dt.datetime, interval_minutes: int
) -> float:
    if interval_minutes <= 0:
        return 0.0
    expected = max(1, int((end - start).total_seconds() / 60 / interval_minutes))
    actual = len(df)
    return _clamp(actual / expected)


def _signal_confidence(signal_strength: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return _clamp(signal_strength / scale)


def _confidence(coverage: float, signal: float) -> float:
    # weight coverage higher than signal strength for reliability
    return _clamp(0.2 + 0.6 * coverage + 0.2 * signal)


async def run_city_analytics(
    session: AsyncSession,
    city,
    now: dt.datetime,
    start: dt.datetime,
    thresholds: dict[str, float],
) -> str:
    run_id = new_id("run")
    session.add(
        AnalyticsRun(
            run_id=run_id,
            city_id=city.city_id,
            start_ts=start,
            end_ts=now,
            status="running",
            version=settings.analytics_version,
            params={
                "window_days": settings.analytics_window_days,
                "rain_threshold_mmph": thresholds["rain_event_threshold_mmph"],
                "rain_min_duration_minutes": thresholds["rain_event_min_duration_minutes"],
                "overflow_fill_threshold": thresholds["overflow_fill_threshold"],
                "overflow_min_duration_minutes": thresholds["overflow_min_duration_minutes"],
                "risk_fill_watch": thresholds["risk_fill_watch"],
                "risk_fill_warning": thresholds["risk_fill_warning"],
            },
            metrics={},
        )
    )
    await session.flush()

    # reset latest asset status for idempotent runs
    await session.execute(delete(AssetStatusLatest).where(AssetStatusLatest.city_id == city.city_id))

    # Rain events from first rain gauge
    rain_gauge = (await session.execute(
        select(Asset).where(Asset.city_id == city.city_id).where(Asset.asset_type == "rain_gauge").limit(1)
    )).scalar_one()
    rain_df = await _load_metric_df(session, rain_gauge.asset_id, "rain_mmph", start, now)
    rain_events = detect_rain_events(
        rain_df,
        threshold_mmph=thresholds["rain_event_threshold_mmph"],
        min_duration_minutes=thresholds["rain_event_min_duration_minutes"],
    )
    for s, e, peak in rain_events:
        event_df = rain_df[(rain_df["ts"] >= s) & (rain_df["ts"] <= e)]
        coverage = _coverage_ratio(
            event_df, s, e, settings.telemetry_gap_granularity_minutes
        )
        signal = _signal_confidence(
            float(peak), thresholds["rain_event_threshold_mmph"] * 2
        )
        conf = _confidence(coverage, signal)
        session.add(
            AnalyticsEvent(
                event_id=new_id("evt"),
                run_id=run_id,
                city_id=city.city_id,
                event_type="rain",
                severity=int(min(10, max(1, peak / 10))),
                confidence=conf,
                start_ts=s,
                end_ts=e,
                asset_ids=[rain_gauge.asset_id],
                summary=f"Rain episode (peak={peak:.1f} mm/h)",
            )
        )

    # Overflows from subset of pipes
    pipes = (await session.execute(
        select(Asset).where(Asset.city_id == city.city_id).where(Asset.asset_type == "pipe").limit(250)
    )).scalars().all()

    day = now.date()
    overflow_event_count = 0
    hotspots_count = 0
    for p in pipes:
        fill_df = await _load_metric_df(session, p.asset_id, "fill_ratio", start, now)
        events = detect_overflow_events(
            fill_df,
            threshold=thresholds["overflow_fill_threshold"],
            min_duration_minutes=thresholds["overflow_min_duration_minutes"],
        )
        score = overflow_minutes_score(events)

        peak_fill = float(fill_df["value"].max()) if len(fill_df) else 0.0
        coverage_all = _coverage_ratio(
            fill_df, start, now, settings.telemetry_gap_granularity_minutes
        )
        hotspot_signal = _signal_confidence(
            float(score), thresholds["overflow_min_duration_minutes"] * 3
        )
        hotspot_conf = _confidence(coverage_all, hotspot_signal)
        status, risk = risk_from_fill(
            peak_fill,
            watch_threshold=thresholds["risk_fill_watch"],
            warning_threshold=thresholds["risk_fill_warning"],
        )

        session.add(
            AssetStatusLatest(
                asset_id=p.asset_id,
                city_id=city.city_id,
                status=status,
                risk_score=risk,
                details={"peak_fill_ratio_24h": peak_fill},
            )
        )

        if score > 0:
            hotspots_count += 1
            # event entry (collapsed)
            for s, e, peak in events[:3]:  # cap spam
                overflow_event_count += 1
                event_df = fill_df[(fill_df["ts"] >= s) & (fill_df["ts"] <= e)]
                coverage = _coverage_ratio(
                    event_df, s, e, settings.telemetry_gap_granularity_minutes
                )
                signal = _signal_confidence(
                    float(peak), thresholds["overflow_fill_threshold"] * 1.5
                )
                conf = _confidence(coverage, signal)
                session.add(
                    AnalyticsEvent(
                        event_id=new_id("evt"),
                        run_id=run_id,
                        city_id=city.city_id,
                        event_type="overflow",
                        severity=int(min(10, max(1, (peak - 1.0) * 10))),
                        confidence=conf,
                        start_ts=s,
                        end_ts=e,
                        asset_ids=[p.asset_id],
                        summary=f"Overflow window (peak fill={peak:.2f})",
                    )
                )

            session.add(
                AnalyticsHotspotDaily(
                    run_id=run_id,
                    city_id=city.city_id,
                    day=day,
                    metric="overflow_risk",
                    asset_id=p.asset_id,
                    score=float(score),
                    confidence=hotspot_conf,
                    details={"overflow_minutes_24h": float(score)},
                )
            )

    # update run metrics
    run_metrics = {
        "rain_events": len(rain_events),
        "overflow_events": overflow_event_count,
        "hotspots": hotspots_count,
        "assets_scored": len(pipes),
    }
    run = await session.get(AnalyticsRun, run_id)
    if run is not None:
        run.status = "completed"
        run.metrics = run_metrics
        run.updated_at = now

    await session.commit()
    return run_id


async def main() -> None:
    cities = get_city_configs()
    now = dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
    start = now - dt.timedelta(days=settings.analytics_window_days)

    async with SessionLocal() as session:
        for city in cities:
            thresholds = {
                "rain_event_threshold_mmph": city.analytics.rain_event_threshold_mmph
                or settings.rain_event_threshold_mmph,
                "rain_event_min_duration_minutes": city.analytics.rain_event_min_duration_minutes
                or settings.rain_event_min_duration_minutes,
                "overflow_fill_threshold": city.analytics.overflow_fill_threshold
                or settings.overflow_fill_threshold,
                "overflow_min_duration_minutes": city.analytics.overflow_min_duration_minutes
                or settings.overflow_min_duration_minutes,
                "risk_fill_watch": city.analytics.risk_fill_watch or settings.risk_fill_watch,
                "risk_fill_warning": city.analytics.risk_fill_warning or settings.risk_fill_warning,
            }
            thresholds = await apply_threshold_overrides(session, city.city_id, thresholds, now)
            run_id = await run_city_analytics(session, city, now, start, thresholds)
            print(
                f"Analytics run {run_id} for city_id={city.city_id} ({start.isoformat()} -> {now.isoformat()})"
            )


async def _load_metric_df(
    session: AsyncSession,
    asset_id: str,
    metric: str,
    start: dt.datetime,
    end: dt.datetime,
) -> pd.DataFrame:
    res = await session.execute(
        select(TelemetryObservation.ts, TelemetryObservation.value)
        .where(TelemetryObservation.asset_id == asset_id)
        .where(TelemetryObservation.metric == metric)
        .where(TelemetryObservation.ts >= start)
        .where(TelemetryObservation.ts < end)
        .order_by(TelemetryObservation.ts)
    )
    rows = res.all()
    return pd.DataFrame(rows, columns=["ts", "value"])


if __name__ == "__main__":
    asyncio.run(main())
