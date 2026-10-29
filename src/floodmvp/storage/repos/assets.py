from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from geoalchemy2 import Geography
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import cast, func, select
from sqlalchemy import tuple_ as sql_tuple
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import Asset, AssetTag, City


def _geom_to_geojson(geom: Any) -> dict[str, Any] | None:
    if geom is None:
        return None
    shp = to_shape(geom)
    return mapping(shp)


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
        # Geography measures metres on the spheroid; Web Mercator metres are
        # distorted by latitude and exclude assets near the requested radius.
        q = q.where(
            func.ST_DWithin(
                cast(Asset.geom, Geography(srid=4326)),
                cast(point, Geography(srid=4326)),
                radius_m,
            )
        )
    if tags:
        # Repeating a filter does not require an asset to hold the same tag twice.
        # The (asset_id, key, value) primary key makes matching tag rows unique.
        unique_tags = list(dict.fromkeys(tags))
        tag_subq = (
            select(AssetTag.asset_id)
            .where(sql_tuple(AssetTag.key, AssetTag.value).in_(unique_tags))
            .group_by(AssetTag.asset_id)
            .having(func.count() == len(unique_tags))
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


async def _list_pipes_by_nodes(
    session: AsyncSession, node_ids: Iterable[str], direction: str, city_id: str
) -> list[Asset]:
    """Fetch pipes adjacent to an entire traversal frontier in one query."""
    ids = sorted(set(node_ids))
    if not ids:
        return []
    key = "downstream_node_id" if direction == "upstream" else "upstream_node_id"
    q = (
        select(Asset)
        .where(Asset.city_id == city_id)
        .where(Asset.asset_type == "pipe")
        # JSON ->> works for both JSON and JSONB, including fresh test schemas.
        .where(Asset.props[key].as_string().in_(ids))
        .order_by(Asset.asset_id)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def _list_assets_by_ids(
    session: AsyncSession, asset_ids: Iterable[str], city_id: str
) -> list[Asset]:
    ids = sorted(set(asset_ids))
    if not ids:
        return []
    res = await session.execute(
        select(Asset)
        .where(Asset.city_id == city_id, Asset.asset_id.in_(ids))
        .order_by(Asset.asset_id)
    )
    return list(res.scalars().all())


async def traverse_network(
    session: AsyncSession,
    asset_id: str,
    direction: str,
    depth: int,
) -> list[Asset] | None:
    """Traverse connected assets; return None if the starting asset is absent."""
    if depth <= 0:
        return []
    start = await get_asset(session, asset_id)
    if start is None:
        return None

    visited: set[str] = {start.asset_id}
    results: list[Asset] = []

    if start.asset_type == "pipe":
        node_id = _pipe_endpoint(start, direction)
        frontier_nodes = {node_id} if node_id else set()
        # The endpoint adjacent to the starting pipe is part of the traversal.
        adjacent_nodes = await _list_assets_by_ids(session, frontier_nodes, start.city_id)
        for node in adjacent_nodes:
            if node.asset_id not in visited:
                visited.add(node.asset_id)
                results.append(node)
    else:
        frontier_nodes = {start.asset_id}

    for _ in range(depth):
        if not frontier_nodes:
            break
        next_nodes: set[str] = set()
        pipes = await _list_pipes_by_nodes(session, frontier_nodes, direction, start.city_id)
        for pipe in pipes:
            if pipe.asset_id not in visited:
                visited.add(pipe.asset_id)
                results.append(pipe)
            node_next = _pipe_endpoint(pipe, direction)
            if node_next and node_next not in visited:
                next_nodes.add(node_next)

        node_assets = await _list_assets_by_ids(session, next_nodes, start.city_id)
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
