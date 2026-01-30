from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.time import parse_iso8601
from floodmvp.models.domain import EventOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.analytics import list_events

router = APIRouter(tags=["events"])


@router.get("/events", response_model=list[EventOut])
async def events(
    city_id: str = Query(...),
    type: str | None = Query(default=None, description="event_type filter"),
    from_ts: str = Query(..., alias="from"),
    to_ts: str = Query(..., alias="to"),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[EventOut]:
    start = parse_iso8601(from_ts)
    end = parse_iso8601(to_ts)
    rows = await list_events(session, city_id, type, start, end, limit)
    return [
        EventOut(
            event_id=r.event_id,
            event_type=r.event_type,
            severity=r.severity,
            start_ts=r.start_ts,
            end_ts=r.end_ts,
            asset_ids=list(r.asset_ids),
            summary=r.summary,
        )
        for r in rows
    ]
