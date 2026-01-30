from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.errors import AppError
from floodmvp.models.domain import AssetOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.assets import asset_to_out, get_asset, list_assets

router = APIRouter(tags=["assets"])


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be 'minLon,minLat,maxLon,maxLat'")
    vals = tuple(float(x) for x in parts)
    return vals  # type: ignore[return-value]


@router.get("/cities/{city_id}/assets", response_model=list[AssetOut])
async def city_assets(
    city_id: str,
    type: str | None = Query(default=None, description="asset_type filter"),
    bbox: str | None = Query(default=None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(default=2000, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
) -> list[AssetOut]:
    try:
        bb = _parse_bbox(bbox)
    except ValueError as e:
        raise AppError(code="INVALID_ARGUMENT", message=str(e))

    rows = await list_assets(session, city_id=city_id, asset_type=type, bbox=bb, limit=limit)
    return [AssetOut(**asset_to_out(a)) for a in rows]


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def asset(asset_id: str, session: AsyncSession = Depends(get_session)) -> AssetOut:
    a = await get_asset(session, asset_id)
    if a is None:
        raise AppError(code="ASSET_NOT_FOUND", message="Asset not found", details={"asset_id": asset_id})
    return AssetOut(**asset_to_out(a))
