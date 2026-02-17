from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy import tuple_ as sql_tuple
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import Asset, AssetTag, City


def _geom_to_geojson(geom: Any) -> dict[str, Any] | None:
    if geom is None:
        return None
    shp = to_shape(geom)
    # shapely mapping compatible
    return cast(dict[str, Any], shp.__geo_interface__)


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
    near: tuple[float, float] | None,
    radius_m: float | None,
    tags: list[tuple[str, str]] | None,
    limit: int,
    offset: int,
) -> list[Asset]:
    q = select(Asset).where(Asset.city_id == city_id)
    if asset_type:
        q = q.where(Asset.asset_type == asset_type)
    if bbox:
        minx, miny, maxx, maxy = bbox
        envelope = func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)
        q = q.where(func.ST_Intersects(Asset.geom, envelope))
    if near and radius_m:
        lon, lat = near
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        q = q.where(
            func.ST_DWithin(
                func.ST_Transform(Asset.geom, 3857),
                func.ST_Transform(point, 3857),
                radius_m,
            )
        )
    if tags:
        tag_subq = (
            select(AssetTag.asset_id)
            .where(sql_tuple(AssetTag.key, AssetTag.value).in_(tags))
            .group_by(AssetTag.asset_id)
            .having(func.count(func.distinct(func.concat(AssetTag.key, ":", AssetTag.value))) == len(tags))
        )
        q = q.where(Asset.asset_id.in_(tag_subq))
    q = q.order_by(Asset.asset_id).offset(offset).limit(limit)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_asset(session: AsyncSession, asset_id: str) -> Asset | None:
    res = await session.execute(select(Asset).where(Asset.asset_id == asset_id))
    return res.scalar_one_or_none()


def _pipe_endpoint(pipe: Asset, direction: str) -> str | None:
    key = "upstream_node_id" if direction == "upstream" else "downstream_node_id"
    props = pipe.props or {}
    val = props.get(key)
    return str(val) if val else None


async def _list_pipes_by_node(
    session: AsyncSession, node_id: str, direction: str
) -> list[Asset]:
    key = "downstream_node_id" if direction == "upstream" else "upstream_node_id"
    q = (
        select(Asset)
        .where(Asset.asset_type == "pipe")
        .where(func.jsonb_extract_path_text(Asset.props, key) == node_id)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def _list_assets_by_ids(session: AsyncSession, asset_ids: Iterable[str]) -> list[Asset]:
    ids = list(asset_ids)
    if not ids:
        return []
    res = await session.execute(select(Asset).where(Asset.asset_id.in_(ids)))
    return list(res.scalars().all())


async def traverse_network(
    session: AsyncSession,
    asset_id: str,
    direction: str,
    depth: int,
) -> list[Asset]:
    if depth <= 0:
        return []
    start = await get_asset(session, asset_id)
    if start is None:
        return []

    visited: set[str] = {start.asset_id}
    results: list[Asset] = []

    if start.asset_type == "pipe":
        node_id = _pipe_endpoint(start, direction)
        frontier_nodes = {node_id} if node_id else set()
    else:
        frontier_nodes = {start.asset_id}

    for _ in range(depth):
        if not frontier_nodes:
            break
        next_nodes: set[str] = set()
        for node_id in list(frontier_nodes):
            if not node_id:
                continue
            pipes = await _list_pipes_by_node(session, node_id, direction)
            for pipe in pipes:
                if pipe.asset_id not in visited:
                    visited.add(pipe.asset_id)
                    results.append(pipe)
                node_next = _pipe_endpoint(pipe, direction)
                if node_next and node_next not in visited:
                    next_nodes.add(node_next)

        node_assets = await _list_assets_by_ids(session, next_nodes)
        for node in node_assets:
            if node.asset_id not in visited:
                visited.add(node.asset_id)
                results.append(node)
        frontier_nodes = next_nodes

    return results


def asset_to_out(a: Asset) -> dict[str, Any]:
    return {
        "asset_id": a.asset_id,
        "city_id": a.city_id,
        "asset_type": a.asset_type,
        "name": a.name,
        "geom_geojson": _geom_to_geojson(a.geom),
        "props": a.props or {},
    }
