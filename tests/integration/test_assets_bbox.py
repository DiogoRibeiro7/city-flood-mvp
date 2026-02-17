from __future__ import annotations

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import Asset, AssetTag, City
from floodmvp.storage.repos.assets import asset_to_out, list_assets


@pytest.mark.asyncio
async def test_bbox_filtering_and_geojson(db_session: AsyncSession) -> None:
    city_id = "city_test_bbox"
    db_session.add(City(city_id=city_id, name="Test City", country="US"))

    assets = [
        Asset(
            asset_id="node_1",
            city_id=city_id,
            asset_type="node",
            name="Node 1",
            geom=WKTElement("POINT(-8.610 41.150)", srid=4326),
            props={},
        ),
        Asset(
            asset_id="pipe_1",
            city_id=city_id,
            asset_type="pipe",
            name="Pipe 1",
            geom=WKTElement("LINESTRING(-8.611 41.151, -8.612 41.152)", srid=4326),
            props={},
        ),
        Asset(
            asset_id="node_2",
            city_id=city_id,
            asset_type="node",
            name="Node 2",
            geom=WKTElement("POINT(-8.800 41.300)", srid=4326),
            props={},
        ),
    ]
    db_session.add_all(assets)
    db_session.add_all(
        [
            AssetTag(asset_id="node_1", key="basin", value="basin_ne"),
            AssetTag(asset_id="pipe_1", key="basin", value="basin_ne"),
            AssetTag(asset_id="node_2", key="basin", value="basin_sw"),
        ]
    )
    await db_session.commit()

    all_assets = await list_assets(
        db_session,
        city_id=city_id,
        asset_type=None,
        bbox=None,
        near=None,
        radius_m=None,
        tags=None,
        limit=100,
    )
    bbox_assets = await list_assets(
        db_session,
        city_id=city_id,
        asset_type=None,
        bbox=(-8.62, 41.14, -8.60, 41.16),
        near=None,
        radius_m=None,
        tags=None,
        limit=100,
    )
    near_assets = await list_assets(
        db_session,
        city_id=city_id,
        asset_type=None,
        bbox=None,
        near=(-8.6105, 41.151),
        radius_m=300,
        tags=None,
        limit=100,
    )

    assert len(all_assets) == 3
    assert len(bbox_assets) < len(all_assets)
    assert {a.asset_id for a in bbox_assets} == {"node_1", "pipe_1"}
    assert {a.asset_id for a in near_assets} == {"node_1", "pipe_1"}

    tag_assets = await list_assets(
        db_session,
        city_id=city_id,
        asset_type=None,
        bbox=None,
        near=None,
        radius_m=None,
        tags=[("basin", "basin_ne")],
        limit=100,
    )
    assert {a.asset_id for a in tag_assets} == {"node_1", "pipe_1"}

    geojson_point = asset_to_out(assets[0])["geom_geojson"]
    geojson_line = asset_to_out(assets[1])["geom_geojson"]
    assert geojson_point is not None
    assert geojson_point["type"] == "Point"
    assert isinstance(geojson_point["coordinates"], list | tuple)
    assert geojson_line is not None
    assert geojson_line["type"] == "LineString"
    assert isinstance(geojson_line["coordinates"], list | tuple)
