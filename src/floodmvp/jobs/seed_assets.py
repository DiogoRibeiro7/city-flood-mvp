from __future__ import annotations

import asyncio

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.ids import new_id
from floodmvp.generators.city_network import generate_city_network, to_wkt
from floodmvp.models.db import Asset, City
from floodmvp.storage.db import SessionLocal


async def _reset(session: AsyncSession) -> None:
    # order matters due to fks
    await session.execute(delete(Asset))
    await session.execute(delete(City))


async def main() -> None:
    city_id = "city_porto_mvp"
    net = generate_city_network(city_id=city_id)

    async with SessionLocal() as session:
        await _reset(session)

        session.add(
            City(
                city_id=city_id,
                name="MVP City",
                country="PT",
                geom=to_wkt(net.city_polygon),
            )
        )

        # River segment asset
        session.add(
            Asset(
                asset_id=new_id("river"),
                city_id=city_id,
                asset_type="river_segment",
                name="River Segment 1",
                geom=to_wkt(net.river),
                props={"kind": "river", "note": "synthetic"},
            )
        )

        # Nodes
        for i, p in enumerate(net.nodes):
            session.add(
                Asset(
                    asset_id=new_id("node"),
                    city_id=city_id,
                    asset_type="node",
                    name=f"Node {i:04d}",
                    geom=to_wkt(p),
                    props={"kind": "junction"},
                )
            )

        # Pipes
        for i, ln in enumerate(net.pipes):
            session.add(
                Asset(
                    asset_id=new_id("pipe"),
                    city_id=city_id,
                    asset_type="pipe",
                    name=f"Pipe {i:04d}",
                    geom=to_wkt(ln),
                    props={
                        "diameter_m": float(0.3 + 0.5 * (i % 5) / 5.0),
                        "material": "PVC",
                    },
                )
            )

        # Gauges
        for i, p in enumerate(net.rain_gauges):
            session.add(
                Asset(
                    asset_id=f"rain_gauge_{i}",
                    city_id=city_id,
                    asset_type="rain_gauge",
                    name=f"Rain Gauge {i}",
                    geom=to_wkt(p),
                    props={"metric": "rain_mmph"},
                )
            )
        for i, p in enumerate(net.river_gauges):
            session.add(
                Asset(
                    asset_id=f"river_gauge_{i}",
                    city_id=city_id,
                    asset_type="river_gauge",
                    name=f"River Gauge {i}",
                    geom=to_wkt(p),
                    props={"metric": "water_level_m"},
                )
            )

        await session.commit()

    print(f"Seeded assets for city_id={city_id}")


if __name__ == "__main__":
    asyncio.run(main())
