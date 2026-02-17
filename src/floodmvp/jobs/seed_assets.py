from __future__ import annotations

import asyncio

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.ids import new_id
from floodmvp.config.cities import CityConfig, get_city_configs
from floodmvp.generators.city_network import generate_city_network, to_wkt
from floodmvp.models.db import Asset, AssetTag, City
from floodmvp.storage.db import SessionLocal


async def _reset(session: AsyncSession) -> None:
    # order matters due to fks
    await session.execute(delete(Asset))
    await session.execute(delete(City))


async def _seed_city(session: AsyncSession, city: CityConfig) -> None:
    net = generate_city_network(
        city_id=city.city_id,
        center_lon=city.network.center_lon,
        center_lat=city.network.center_lat,
        half_size_deg=city.network.half_size_deg,
        grid_n=city.network.grid_n,
        jitter_ratio=city.network.jitter_ratio,
        outfall_count=city.network.outfall_count,
        seed=city.network.seed,
    )
    minx, miny, maxx, maxy = net.city_polygon.bounds
    width = maxx - minx
    height = maxy - miny

    session.add(
        City(
            city_id=city.city_id,
            name=city.name,
            country=city.country,
            geom=to_wkt(net.city_polygon),
        )
    )
    await session.flush()

    # River segment asset
    session.add(
        Asset(
            asset_id=new_id("river"),
            city_id=city.city_id,
            asset_type="river_segment",
            name="River Segment 1",
            geom=to_wkt(net.river),
            props={"kind": "river", "note": "synthetic"},
        )
    )

    # Nodes
    node_ids: list[str] = []
    for i, p in enumerate(net.nodes):
        node_id = new_id("node")
        node_ids.append(node_id)
        basin_tag = "basin_nw"
        if p.x >= minx + width / 2 and p.y >= miny + height / 2:
            basin_tag = "basin_ne"
        elif p.x < minx + width / 2 and p.y < miny + height / 2:
            basin_tag = "basin_sw"
        elif p.x >= minx + width / 2 and p.y < miny + height / 2:
            basin_tag = "basin_se"
        nx = min(2, int(3 * (p.x - minx) / width))
        ny = min(2, int(3 * (p.y - miny) / height))
        neighborhood_tag = f"neighborhood_{nx}_{ny}"
        session.add(
            Asset(
                asset_id=node_id,
                city_id=city.city_id,
                asset_type="node",
                name=f"Node {i:04d}",
                geom=to_wkt(p),
                props={"kind": "junction"},
            )
        )
        session.add_all(
            [
                AssetTag(asset_id=node_id, key="basin", value=basin_tag),
                AssetTag(asset_id=node_id, key="neighborhood", value=neighborhood_tag),
            ]
        )

    # Outfalls
    outfall_ids: list[str] = []
    for i, p in enumerate(net.outfalls):
        outfall_id = new_id("outfall")
        outfall_ids.append(outfall_id)
        nx = min(2, int(3 * (p.x - minx) / width))
        ny = min(2, int(3 * (p.y - miny) / height))
        neighborhood_tag = f"neighborhood_{nx}_{ny}"
        session.add(
            Asset(
                asset_id=outfall_id,
                city_id=city.city_id,
                asset_type="outfall",
                name=f"Outfall {i:02d}",
                geom=to_wkt(p),
                props={"kind": "outfall"},
            )
        )
        session.add_all(
            [
                AssetTag(asset_id=outfall_id, key="basin", value="basin_river"),
                AssetTag(asset_id=outfall_id, key="neighborhood", value=neighborhood_tag),
            ]
        )

    # Pipes
    for i, pipe in enumerate(net.pipes):
        upstream_id = node_ids[pipe.upstream_idx]
        if pipe.downstream_kind == "node":
            downstream_id = node_ids[pipe.downstream_idx]
        else:
            downstream_id = outfall_ids[pipe.downstream_idx]
        pipe_id = new_id("pipe")
        mid = pipe.line.interpolate(0.5, normalized=True)
        basin_tag = "basin_nw"
        if mid.x >= minx + width / 2 and mid.y >= miny + height / 2:
            basin_tag = "basin_ne"
        elif mid.x < minx + width / 2 and mid.y < miny + height / 2:
            basin_tag = "basin_sw"
        elif mid.x >= minx + width / 2 and mid.y < miny + height / 2:
            basin_tag = "basin_se"
        nx = min(2, int(3 * (mid.x - minx) / width))
        ny = min(2, int(3 * (mid.y - miny) / height))
        neighborhood_tag = f"neighborhood_{nx}_{ny}"
        session.add(
            Asset(
                asset_id=pipe_id,
                city_id=city.city_id,
                asset_type="pipe",
                name=f"Pipe {i:04d}",
                geom=to_wkt(pipe.line),
                props={
                    "diameter_m": float(pipe.diameter_m),
                    "length_m": float(pipe.length_m),
                    "slope": float(pipe.slope),
                    "capacity_est_m3s": float(pipe.capacity_est_m3s),
                    "upstream_node_id": upstream_id,
                    "downstream_node_id": downstream_id,
                    "flow_direction": f"{upstream_id}->{downstream_id}",
                    "material": "PVC",
                },
            )
        )
        session.add_all(
            [
                AssetTag(asset_id=pipe_id, key="basin", value=basin_tag),
                AssetTag(asset_id=pipe_id, key="neighborhood", value=neighborhood_tag),
            ]
        )

    # Gauges
    for i, p in enumerate(net.rain_gauges):
        rain_id = new_id("rain")
        nx = min(2, int(3 * (p.x - minx) / width))
        ny = min(2, int(3 * (p.y - miny) / height))
        neighborhood_tag = f"neighborhood_{nx}_{ny}"
        session.add(
            Asset(
                asset_id=rain_id,
                city_id=city.city_id,
                asset_type="rain_gauge",
                name=f"Rain Gauge {i}",
                geom=to_wkt(p),
                props={"metric": "rain_mmph"},
            )
        )
        session.add_all(
            [
                AssetTag(asset_id=rain_id, key="basin", value="basin_surface"),
                AssetTag(asset_id=rain_id, key="neighborhood", value=neighborhood_tag),
            ]
        )
    for i, p in enumerate(net.river_gauges):
        river_id = new_id("river")
        nx = min(2, int(3 * (p.x - minx) / width))
        ny = min(2, int(3 * (p.y - miny) / height))
        neighborhood_tag = f"neighborhood_{nx}_{ny}"
        session.add(
            Asset(
                asset_id=river_id,
                city_id=city.city_id,
                asset_type="river_gauge",
                name=f"River Gauge {i}",
                geom=to_wkt(p),
                props={"metric": "water_level_m"},
            )
        )
        session.add_all(
            [
                AssetTag(asset_id=river_id, key="basin", value="basin_river"),
                AssetTag(asset_id=river_id, key="neighborhood", value=neighborhood_tag),
            ]
        )


async def main() -> None:
    cities = get_city_configs()
    async with SessionLocal() as session:
        await _reset(session)
        for city in cities:
            await _seed_city(session, city)
        await session.commit()
    print(f"Seeded assets for city_ids={[c.city_id for c in cities]}")


if __name__ == "__main__":
    asyncio.run(main())
