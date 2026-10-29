from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import error_response
from floodmvp.common.errors import AppError
from floodmvp.models.domain import AssetOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.assets import asset_to_out, get_asset, list_assets, traverse_network

router = APIRouter(tags=["assets"])


def _validate_lon_lat(lon: float, lat: float, parameter: str) -> None:
    """Reject coordinates that cannot represent a WGS84 longitude/latitude pair."""
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise ValueError(f"{parameter} coordinates must be finite")
    if not -180 <= lon <= 180:
        raise ValueError(f"{parameter} longitude must be between -180 and 180")
    if not -90 <= lat <= 90:
        raise ValueError(f"{parameter} latitude must be between -90 and 90")


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be 'minLon,minLat,maxLon,maxLat'")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("bbox must be 'minLon,minLat,maxLon,maxLat'") from exc
    _validate_lon_lat(min_lon, min_lat, "bbox")
    _validate_lon_lat(max_lon, max_lat, "bbox")
    # ST_MakeEnvelope does not model an antimeridian-wrapping rectangle.
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("bbox must have minLon < maxLon and minLat < maxLat")
    return min_lon, min_lat, max_lon, max_lat


def _parse_near(near: str | None) -> tuple[float, float] | None:
    if near is None:
        return None
    parts = near.split(",")
    if len(parts) != 2:
        raise ValueError("near must be 'lon,lat'")
    try:
        lon, lat = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("near must be 'lon,lat'") from exc
    _validate_lon_lat(lon, lat, "near")
    return lon, lat


def _parse_tags(tags: list[str] | None) -> list[tuple[str, str]] | None:
    if not tags:
        return None
    parsed: list[tuple[str, str]] = []
    for raw in tags:
        parts = raw.split(":", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("tag must be 'key:value'")
        parsed.append((parts[0], parts[1]))
    return parsed


@router.get(
    "/cities/{city_id}/assets",
    response_model=list[AssetOut],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "asset_id": "pipe_123",
                            "city_id": "city_porto_mvp",
                            "asset_type": "pipe",
                            "name": "Pipe 0001",
                            "geom_geojson": {
                                "type": "LineString",
                                "coordinates": [[-8.69, 41.07], [-8.68, 41.08]],
                            },
                            "props": {"diameter_m": 0.5, "material": "PVC"},
                        }
                    ]
                }
            }
        }
        ,
        400: error_response(
            code="INVALID_ARGUMENT",
            message="bbox must be 'minLon,minLat,maxLon,maxLat'",
        ),
    },
)
async def city_assets(
    city_id: str,
    response: Response,
    type: str | None = Query(default=None, description="asset_type filter"),
    bbox: str | None = Query(
        default=None, description="minLon,minLat,maxLon,maxLat (WGS84, non-wrapping extent)"
    ),
    near: str | None = Query(default=None, description="WGS84 lon,lat for radial search"),
    radius_m: float = Query(default=500.0, ge=1, le=50_000, allow_inf_nan=False),
    tag: list[str] | None = Query(default=None, description="tag filter key:value (repeatable)"),
    limit: int = Query(default=2000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[AssetOut]:
    try:
        bb = _parse_bbox(bbox)
        near_pt = _parse_near(near)
        tags = _parse_tags(tag)
    except ValueError as e:
        raise AppError(code="INVALID_ARGUMENT", message=str(e)) from e

    rows = await list_assets(
        session,
        city_id=city_id,
        asset_type=type,
        bbox=bb,
        near=near_pt,
        radius_m=radius_m if near_pt else None,
        tags=tags,
        limit=limit,
        offset=offset,
    )
    response.headers["Cache-Control"] = "public, max-age=60"
    return [AssetOut(**asset_to_out(a)) for a in rows]


@router.get(
    "/assets/{asset_id}",
    response_model=AssetOut,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "asset_id": "pipe_123",
                        "city_id": "city_porto_mvp",
                        "asset_type": "pipe",
                        "name": "Pipe 0001",
                        "geom_geojson": {
                            "type": "LineString",
                            "coordinates": [[-8.69, 41.07], [-8.68, 41.08]],
                        },
                        "props": {"diameter_m": 0.5, "material": "PVC"},
                    }
                }
            }
        }
        ,
        404: error_response(
            code="ASSET_NOT_FOUND",
            message="Asset not found",
            details={"asset_id": "asset_missing"},
        ),
    },
)
async def asset(
    asset_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AssetOut:
    a = await get_asset(session, asset_id)
    if a is None:
        raise AppError(
            code="ASSET_NOT_FOUND",
            message="Asset not found",
            details={"asset_id": asset_id},
            status_code=404,
        )
    response.headers["Cache-Control"] = "public, max-age=60"
    return AssetOut(**asset_to_out(a))


async def _network_assets_or_404(
    session: AsyncSession,
    asset_id: str,
    direction: Literal["upstream", "downstream"],
    depth: int,
) -> list[AssetOut]:
    """Distinguish an unknown asset from an existing isolated asset."""
    rows = await traverse_network(session, asset_id, direction, depth)
    if rows is None:
        raise AppError(
            code="ASSET_NOT_FOUND",
            message="Asset not found",
            details={"asset_id": asset_id},
            status_code=404,
        )
    return [AssetOut(**asset_to_out(a)) for a in rows]


@router.get(
    "/assets/{asset_id}/upstream",
    response_model=list[AssetOut],
    responses={
        404: error_response(
            code="ASSET_NOT_FOUND",
            message="Asset not found",
            details={"asset_id": "asset_missing"},
        ),
    },
)
async def asset_upstream(
    asset_id: str,
    depth: int = Query(3, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> list[AssetOut]:
    return await _network_assets_or_404(session, asset_id, "upstream", depth)


@router.get(
    "/assets/{asset_id}/downstream",
    response_model=list[AssetOut],
    responses={
        404: error_response(
            code="ASSET_NOT_FOUND",
            message="Asset not found",
            details={"asset_id": "asset_missing"},
        ),
    },
)
async def asset_downstream(
    asset_id: str,
    depth: int = Query(3, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> list[AssetOut]:
    return await _network_assets_or_404(session, asset_id, "downstream", depth)
