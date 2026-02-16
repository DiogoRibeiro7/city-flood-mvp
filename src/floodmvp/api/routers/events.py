from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import error_response
from floodmvp.common.time import parse_iso8601
from floodmvp.models.domain import EventOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.analytics import list_events

router = APIRouter(tags=["events"])


@router.get(
    "/events",
    response_model=list[EventOut],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "event_id": "evt_123",
                            "event_type": "overflow",
                            "severity": 2,
                            "start_ts": "2026-02-01T10:00:00Z",
                            "end_ts": "2026-02-01T12:00:00Z",
                            "asset_ids": ["pipe_123", "pipe_456"],
                            "summary": "Overflow risk detected across 2 pipes.",
                        }
                    ]
                }
            }
        }
        ,
        400: error_response(
            code="INVALID_ARGUMENT",
            message="'to' must be after 'from'",
        ),
    },
)
async def events(
    city_id: str = Query(...),
    type: str | None = Query(default=None, description="event_type filter"),
    from_ts: str = Query(..., alias="from"),
    to_ts: str = Query(..., alias="to"),
    run_id: str | None = Query(default=None, description="analytics run_id"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[EventOut]:
    start = parse_iso8601(from_ts)
    end = parse_iso8601(to_ts)
    if end <= start:
        from floodmvp.common.errors import AppError

        raise AppError(code="INVALID_ARGUMENT", message="'to' must be after 'from'")
    rows = await list_events(session, city_id, type, start, end, limit, offset, run_id=run_id)
    return [
        EventOut(
            event_id=r.event_id,
            event_type=r.event_type,
            severity=r.severity,
            confidence=float(r.confidence),
            start_ts=r.start_ts,
            end_ts=r.end_ts,
            asset_ids=list(r.asset_ids),
            summary=r.summary,
        )
        for r in rows
    ]
