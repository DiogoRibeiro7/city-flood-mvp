from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import error_response
from floodmvp.common.errors import AppError
from floodmvp.models.domain import AssetOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.assets import asset_to_out, get_asset, list_assets, traverse_network

router = APIRouter(tags=["assets"])


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be 'minLon,minLat,maxLon,maxLat'")
    vals = tuple(float(x) for x in parts)
    return vals  # type: ignore[return-value]


def _parse_near(near: str | None) -> tuple[float, float] | None:
    if near is None:
        return None
    parts = near.split(",")
    if len(parts) != 2:
        raise ValueError("near must be 'lon,lat'")
    vals = tuple(float(x) for x in parts)
    return vals  # type: ignore[return-value]


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
    bbox: str | None = Query(default=None, description="minLon,minLat,maxLon,maxLat"),
    near: str | None = Query(default=None, description="lon,lat for radial search"),
    radius_m: float = Query(default=500.0, ge=1, le=50_000),
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


@router.get("/assets/{asset_id}/upstream", response_model=list[AssetOut])
async def asset_upstream(
    asset_id: str,
    depth: int = Query(3, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> list[AssetOut]:
    rows = await traverse_network(session, asset_id, "upstream", depth)
    return [AssetOut(**asset_to_out(a)) for a in rows]


@router.get("/assets/{asset_id}/downstream", response_model=list[AssetOut])
async def asset_downstream(
    asset_id: str,
    depth: int = Query(3, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> list[AssetOut]:
    rows = await traverse_network(session, asset_id, "downstream", depth)
    return [AssetOut(**asset_to_out(a)) for a in rows]
