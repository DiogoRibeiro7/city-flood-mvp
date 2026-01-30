from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.domain import CityStatusOut, HotspotOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.analytics import get_city_status, list_hotspots

router = APIRouter(tags=["analytics"])


@router.get("/cities/{city_id}/status", response_model=CityStatusOut)
async def city_status(
    request: Request,
    city_id: str,
    session: AsyncSession = Depends(get_session),
) -> CityStatusOut:
    out = await get_city_status(session, city_id)
    out["request_id"] = getattr(request.state, "request_id", "req_unknown")
    return CityStatusOut(**out)


@router.get("/hotspots", response_model=list[HotspotOut])
async def hotspots(
    city_id: str = Query(...),
    metric: str = Query("overflow_risk"),
    top: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[HotspotOut]:
    rows = await list_hotspots(session, city_id, metric, top)
    return [HotspotOut(asset_id=r.asset_id, score=float(r.score), details=r.details or {}) for r in rows]
