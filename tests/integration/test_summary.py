from __future__ import annotations

import datetime as dt

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.main import app
from floodmvp.models.db import Asset, AssetStatusLatest, City, TelemetryObservation
from floodmvp.storage.db import get_session


@pytest.fixture()
async def app_client(db_session: AsyncSession) -> AsyncClient:
    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_city_summary_latest_aggregates(app_client: AsyncClient, db_session: AsyncSession) -> None:
    city_id = "city_summary"
    db_session.add(City(city_id=city_id, name="Summary City", country="US"))
    db_session.add_all(
        [
            Asset(
                asset_id="rain_1",
                city_id=city_id,
                asset_type="rain_gauge",
                name="Rain 1",
                geom=WKTElement("POINT(-8.610 41.150)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="rain_2",
                city_id=city_id,
                asset_type="rain_gauge",
                name="Rain 2",
                geom=WKTElement("POINT(-8.611 41.151)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="river_1",
                city_id=city_id,
                asset_type="river_gauge",
                name="River 1",
                geom=WKTElement("POINT(-8.612 41.152)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="river_2",
                city_id=city_id,
                asset_type="river_gauge",
                name="River 2",
                geom=WKTElement("POINT(-8.613 41.153)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="pipe_1",
                city_id=city_id,
                asset_type="pipe",
                name="Pipe 1",
                geom=WKTElement("LINESTRING(-8.610 41.150, -8.612 41.152)", srid=4326),
                props={},
            ),
        ]
    )
    db_session.add_all(
        [
            AssetStatusLatest(asset_id="pipe_1", city_id=city_id, status="warning", risk_score=0.8),
        ]
    )
    now = dt.datetime.now(dt.UTC)
    recent = now - dt.timedelta(minutes=5)
    older = now - dt.timedelta(minutes=30)
    db_session.add_all(
        [
            TelemetryObservation(
                asset_id="rain_1",
                metric="rain_mmph",
                ts=recent,
                value=10.0,
                quality_flag="ok",
                source="synthetic",
            ),
            TelemetryObservation(
                asset_id="rain_2",
                metric="rain_mmph",
                ts=recent,
                value=14.0,
                quality_flag="ok",
                source="synthetic",
            ),
            TelemetryObservation(
                asset_id="rain_1",
                metric="rain_mmph",
                ts=older,
                value=100.0,
                quality_flag="ok",
                source="synthetic",
            ),
            TelemetryObservation(
                asset_id="river_1",
                metric="water_level_m",
                ts=recent,
                value=2.0,
                quality_flag="ok",
                source="synthetic",
            ),
            TelemetryObservation(
                asset_id="river_2",
                metric="water_level_m",
                ts=recent,
                value=2.2,
                quality_flag="ok",
                source="synthetic",
            ),
        ]
    )
    await db_session.commit()

    res = await app_client.get(f"/v1/cities/{city_id}/summary?minutes=15")
    assert res.status_code == 200
    body = res.json()
    assert body["city_id"] == city_id
    assert body["status_counts"]["warning"] == 1
    assert body["status_counts"]["normal"] == 0
    assert body["status_counts"]["watch"] == 0
    assert abs(body["rain_mmph"] - 12.0) < 0.01
    assert abs(body["river_level_m"] - 2.1) < 0.01
