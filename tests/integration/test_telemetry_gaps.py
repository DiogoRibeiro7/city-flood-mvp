from __future__ import annotations

import datetime as dt

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.main import app
from floodmvp.models.db import Asset, City, TelemetryObservation
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
async def test_observations_include_gaps(app_client: AsyncClient, db_session: AsyncSession) -> None:
    has_gapfill = await db_session.scalar(
        text("SELECT 1 FROM pg_proc WHERE proname = 'time_bucket_gapfill' LIMIT 1")
    )
    if not has_gapfill:
        pytest.skip("time_bucket_gapfill not available")
    city_id = "city_gap"
    asset_id = "pipe_gap"
    db_session.add(City(city_id=city_id, name="Gap City", country="US"))
    db_session.add(
        Asset(
            asset_id=asset_id,
            city_id=city_id,
            asset_type="pipe",
            name="Pipe",
            geom=WKTElement("LINESTRING(-8.610 41.150, -8.612 41.152)", srid=4326),
            props={},
        )
    )
    start = dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    db_session.add_all(
        [
            TelemetryObservation(
                asset_id=asset_id,
                metric="fill_ratio",
                ts=start,
                value=0.4,
                quality_flag="ok",
                source="synthetic",
            ),
            TelemetryObservation(
                asset_id=asset_id,
                metric="fill_ratio",
                ts=start + dt.timedelta(minutes=10),
                value=0.6,
                quality_flag="ok",
                source="synthetic",
            ),
        ]
    )
    await db_session.commit()

    params = {
        "metric": "fill_ratio",
        "from": start.isoformat(),
        "to": (start + dt.timedelta(minutes=15)).isoformat(),
        "granularity": "5m",
        "agg": "avg",
        "include_gaps": "true",
    }
    res = await app_client.get(f"/v1/assets/{asset_id}/observations", params=params)
    assert res.status_code == 200
    body = res.json()
    values = [p["value"] for p in body["series"]]
    assert len(values) == 3
    assert values[1] is None
