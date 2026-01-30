from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.errors import AppError
from floodmvp.common.time import parse_iso8601
from floodmvp.models.domain import ObservationsOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.telemetry import get_observations, list_metrics

router = APIRouter(tags=["telemetry"])


@router.get("/assets/{asset_id}/metrics", response_model=list[str])
async def metrics(asset_id: str, session: AsyncSession = Depends(get_session)) -> list[str]:
    return await list_metrics(session, asset_id)


@router.get("/assets/{asset_id}/observations", response_model=ObservationsOut)
async def observations(
    request: Request,
    asset_id: str,
    metric: str = Query(...),
    from_ts: str = Query(..., alias="from"),
    to_ts: str = Query(..., alias="to"),
    granularity: str = Query("5m", description="Timescale time_bucket interval, e.g. 1m,5m,1h"),
    agg: str = Query("avg", description="avg|min|max"),
    session: AsyncSession = Depends(get_session),
) -> ObservationsOut:
    start = parse_iso8601(from_ts)
    end = parse_iso8601(to_ts)
    if end <= start:
        raise AppError(code="INVALID_ARGUMENT", message="'to' must be after 'from'")

    try:
        rows = await get_observations(session, asset_id, metric, start, end, granularity, agg)
    except ValueError as e:
        raise AppError(code="INVALID_ARGUMENT", message=str(e))

    return ObservationsOut(
        metric=metric,
        series=[{"ts": t, "value": v} for t, v in rows],
        request_id=getattr(request.state, "request_id", "req_unknown"),
    )
