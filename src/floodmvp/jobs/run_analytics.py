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


async def main() -> None:
    city_id = "city_porto_mvp"
    now = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    start = now - dt.timedelta(days=settings.analytics_window_days)
    run_id = new_id("run")

    async with SessionLocal() as session:
        session.add(
            AnalyticsRun(
                run_id=run_id,
                city_id=city_id,
                start_ts=start,
                end_ts=now,
                status="running",
                version=settings.analytics_version,
                params={
                    "window_days": settings.analytics_window_days,
                    "rain_threshold_mmph": settings.rain_event_threshold_mmph,
                    "rain_min_duration_minutes": settings.rain_event_min_duration_minutes,
                    "overflow_fill_threshold": settings.overflow_fill_threshold,
                    "overflow_min_duration_minutes": settings.overflow_min_duration_minutes,
                    "risk_fill_watch": settings.risk_fill_watch,
                    "risk_fill_warning": settings.risk_fill_warning,
                },
                metrics={},
            )
        )
        await session.flush()

        # reset derived tables for idempotent runs
        await session.execute(delete(AnalyticsEvent).where(AnalyticsEvent.city_id == city_id))
        await session.execute(delete(AnalyticsHotspotDaily).where(AnalyticsHotspotDaily.city_id == city_id))
        await session.execute(delete(AssetStatusLatest).where(AssetStatusLatest.city_id == city_id))

        # Rain events from first rain gauge
        rain_gauge = (await session.execute(
            select(Asset).where(Asset.city_id == city_id).where(Asset.asset_type == "rain_gauge").limit(1)
        )).scalar_one()
        rain_df = await _load_metric_df(session, rain_gauge.asset_id, "rain_mmph", start, now)
        rain_events = detect_rain_events(
            rain_df,
            threshold_mmph=settings.rain_event_threshold_mmph,
            min_duration_minutes=settings.rain_event_min_duration_minutes,
        )
        for s, e, peak in rain_events:
            session.add(
                AnalyticsEvent(
                    event_id=new_id("evt"),
                    city_id=city_id,
                    event_type="rain",
                    severity=int(min(10, max(1, peak / 10))),
                    start_ts=s,
                    end_ts=e,
                    asset_ids=[rain_gauge.asset_id],
                    summary=f"Rain episode (peak={peak:.1f} mm/h)",
                )
            )

        # Overflows from subset of pipes
        pipes = (await session.execute(
            select(Asset).where(Asset.city_id == city_id).where(Asset.asset_type == "pipe").limit(250)
        )).scalars().all()

        day = now.date()
        overflow_event_count = 0
        hotspots_count = 0
        for p in pipes:
            fill_df = await _load_metric_df(session, p.asset_id, "fill_ratio", start, now)
            events = detect_overflow_events(
                fill_df,
                threshold=settings.overflow_fill_threshold,
                min_duration_minutes=settings.overflow_min_duration_minutes,
            )
            score = overflow_minutes_score(events)

            peak_fill = float(fill_df["value"].max()) if len(fill_df) else 0.0
            status, risk = risk_from_fill(
                peak_fill,
                watch_threshold=settings.risk_fill_watch,
                warning_threshold=settings.risk_fill_warning,
            )

            session.add(
                AssetStatusLatest(
                    asset_id=p.asset_id,
                    city_id=city_id,
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
                    session.add(
                        AnalyticsEvent(
                            event_id=new_id("evt"),
                            city_id=city_id,
                            event_type="overflow",
                            severity=int(min(10, max(1, (peak - 1.0) * 10))),
                            start_ts=s,
                            end_ts=e,
                            asset_ids=[p.asset_id],
                            summary=f"Overflow window (peak fill={peak:.2f})",
                        )
                    )

                session.add(
                    AnalyticsHotspotDaily(
                        city_id=city_id,
                        day=day,
                        metric="overflow_risk",
                        asset_id=p.asset_id,
                        score=float(score),
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

    print(
        f"Analytics run {run_id} for city_id={city_id} ({start.isoformat()} -> {now.isoformat()})"
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
