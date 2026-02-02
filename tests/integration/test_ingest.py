from __future__ import annotations

import datetime as dt

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy import func, select
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


async def _seed_asset(session: AsyncSession, asset_id: str = "asset_1") -> None:
    session.add(City(city_id="city_test", name="Test City", country="US"))
    session.add(
        Asset(
            asset_id=asset_id,
            city_id="city_test",
            asset_type="node",
            name="Node 1",
            geom=WKTElement("POINT(-8.610 41.150)", srid=4326),
            props={},
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_ingest_auth_required(app_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_asset(db_session)
    payload = {
        "device_id": "asset_1",
        "sent_at": dt.datetime.utcnow().isoformat(),
        "events": [{"ts": dt.datetime.utcnow().isoformat(), "type": "fill_ratio", "value": 0.7}],
    }
    res = await app_client.post("/v1/telemetry/events:batch", json=payload)
    assert res.status_code == 401

    res = await app_client.post(
        "/v1/telemetry/events:batch",
        json=payload,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_ingest_idempotency(app_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_asset(db_session)
    payload = {
        "device_id": "asset_1",
        "sent_at": dt.datetime.utcnow().isoformat(),
        "events": [{"ts": dt.datetime.utcnow().isoformat(), "type": "fill_ratio", "value": 0.7}],
    }
    headers = {"Authorization": "Bearer dev-ingest-token", "Idempotency-Key": "key-1"}

    res1 = await app_client.post("/v1/telemetry/events:batch", json=payload, headers=headers)
    assert res1.status_code == 200
    body1 = res1.json()

    count1 = await db_session.scalar(select(func.count()).select_from(TelemetryObservation))
    assert count1 == 1

    payload["events"].append(
        {"ts": dt.datetime.utcnow().isoformat(), "type": "fill_ratio", "value": 0.8}
    )
    res2 = await app_client.post("/v1/telemetry/events:batch", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json() == body1

    count2 = await db_session.scalar(select(func.count()).select_from(TelemetryObservation))
    assert count2 == 1


@pytest.mark.asyncio
async def test_ingest_partial_failure(app_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_asset(db_session)
    payload = {
        "device_id": "asset_1",
        "sent_at": dt.datetime.utcnow().isoformat(),
        "events": [
            {"ts": dt.datetime.utcnow().isoformat(), "type": "fill_ratio", "value": 0.7},
            {"ts": dt.datetime.utcnow().isoformat(), "type": "", "value": 0.2},
        ],
    }
    headers = {"Authorization": "Bearer dev-ingest-token"}

    res = await app_client.post("/v1/telemetry/events:batch", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1
    assert body["results"][0]["status"] == "accepted"
    assert body["results"][1]["status"] == "rejected"

    count = await db_session.scalar(select(func.count()).select_from(TelemetryObservation))
    assert count == 1
