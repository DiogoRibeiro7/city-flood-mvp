from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from floodmvp.api.main import app
from floodmvp.config.settings import settings
from floodmvp.jobs import queue_worker
from floodmvp.models.db import Asset, City, TelemetryObservation
from floodmvp.storage.db import get_session


@pytest.fixture()
async def app_client(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncClient:
    monkeypatch.setattr(settings, "export_dir", str(tmp_path / "exports"))

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_job_csv(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    city_id = "city_export"
    asset_id = "pipe_export"
    db_session.add(City(city_id=city_id, name="Export City", country="US"))
    await db_session.flush()
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
    await db_session.flush()
    start = dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.UTC)
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
    assert body["status"] == "queued"
    assert body["file_path"] is None

    pending_download = await app_client.get(f"/v1/analytics/jobs/{body['job_id']}/download")
    assert pending_download.status_code == 400
    assert pending_download.json()["error"]["code"] == "JOB_NOT_READY"

    # The API enqueues work; the worker processes it in a separate session.
    assert db_session.bind is not None
    monkeypatch.setattr(
        queue_worker,
        "SessionLocal",
        async_sessionmaker(db_session.bind, expire_on_commit=False),
    )
    await queue_worker.run_worker(poll_seconds=0, once=True)
    # The API test fixture reuses one session; real HTTP requests use fresh ones.
    db_session.expire_all()

    status = await app_client.get(f"/v1/analytics/jobs/{body['job_id']}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["file_path"]

    res_dl = await app_client.get(f"/v1/analytics/jobs/{body['job_id']}/download")
    assert res_dl.status_code == 200
    content = res_dl.text
    assert "asset_id,metric,ts,value" in content
    assert asset_id in content

    # Export files may be pruned independently of their completed job records.
    Path(status.json()["file_path"]).unlink()
    missing_download = await app_client.get(f"/v1/analytics/jobs/{body['job_id']}/download")
    assert missing_download.status_code == 404
    error = missing_download.json()["error"]
    assert error["code"] == "JOB_FILE_NOT_FOUND"
    assert error["details"] == {"job_id": body["job_id"]}
