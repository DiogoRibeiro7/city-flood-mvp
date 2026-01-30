from __future__ import annotations

import datetime as dt

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import AnalyticsEvent, AnalyticsHotspotDaily, AssetStatusLatest


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
) -> list[AnalyticsEvent]:
    q = (
        select(AnalyticsEvent)
        .where(AnalyticsEvent.city_id == city_id)
        .where(AnalyticsEvent.start_ts < end)
        .where(AnalyticsEvent.end_ts >= start)
    )
    if event_type:
        q = q.where(AnalyticsEvent.event_type == event_type)
    q = q.order_by(desc(AnalyticsEvent.start_ts)).limit(limit)
    res = await session.execute(q)
    return list(res.scalars().all())
