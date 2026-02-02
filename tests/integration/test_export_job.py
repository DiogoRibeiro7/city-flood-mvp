from __future__ import annotations

import datetime as dt

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.main import app
from floodmvp.config.settings import settings
from floodmvp.models.db import Asset, City, TelemetryObservation
from floodmvp.storage.db import get_session


@pytest.fixture()
async def app_client(db_session: AsyncSession, tmp_path) -> AsyncClient:
    settings.export_dir = str(tmp_path / "exports")

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_job_csv(app_client: AsyncClient, db_session: AsyncSession) -> None:
    city_id = "city_export"
    asset_id = "pipe_export"
    db_session.add(City(city_id=city_id, name="Export City", country="US"))
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
                ts=start + dt.timedelta(minutes=5),
                value=0.6,
                quality_flag="ok",
                source="synthetic",
            ),
        ]
    )
    await db_session.commit()

    payload = {
        "type": "export_csv",
        "query": {
            "asset_ids": [asset_id],
            "metric": "fill_ratio",
            "from": start.isoformat(),
            "to": (start + dt.timedelta(minutes=15)).isoformat(),
            "granularity": "5m",
            "agg": "avg",
        },
    }
    res = await app_client.post("/v1/analytics/jobs", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["file_path"]

    res_dl = await app_client.get(f"/v1/analytics/jobs/{body['job_id']}/download")
    assert res_dl.status_code == 200
    content = res_dl.text
    assert "asset_id,metric,ts,value" in content
    assert asset_id in content
