from __future__ import annotations

from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import Asset, City


def _geom_to_geojson(geom: Any) -> dict | None:
    if geom is None:
        return None
    shp = to_shape(geom)
    # shapely mapping compatible
    return shp.__geo_interface__  # type: ignore[return-value]


async def list_cities(session: AsyncSession) -> list[City]:
    res = await session.execute(select(City).order_by(City.name))
    return list(res.scalars().all())


async def get_city(session: AsyncSession, city_id: str) -> City | None:
    res = await session.execute(select(City).where(City.city_id == city_id))
    return res.scalar_one_or_none()


async def list_assets(
    session: AsyncSession,
    city_id: str,
    asset_type: str | None,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> list[Asset]:
    q = select(Asset).where(Asset.city_id == city_id)
    if asset_type:
        q = q.where(Asset.asset_type == asset_type)
    if bbox:
        minx, miny, maxx, maxy = bbox
        # ST_MakeEnvelope in SRID 4326
        q = q.where(Asset.geom.ST_Intersects(f"SRID=4326;POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"))
    q = q.limit(limit)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_asset(session: AsyncSession, asset_id: str) -> Asset | None:
    res = await session.execute(select(Asset).where(Asset.asset_id == asset_id))
    return res.scalar_one_or_none()


def asset_to_out(a: Asset) -> dict:
    return {
        "asset_id": a.asset_id,
        "city_id": a.city_id,
        "asset_type": a.asset_type,
        "name": a.name,
        "geom_geojson": _geom_to_geojson(a.geom),
        "props": a.props or {},
    }
