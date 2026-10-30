from __future__ import annotations

import datetime as dt

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.models.db import Asset, City, IngestIdempotency, TelemetryObservation
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.ingest import prune_expired_idempotency


@pytest.fixture()
async def app_client(db_session: AsyncSession) -> AsyncClient:
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()


async def _seed_asset(session: AsyncSession, asset_id: str = "asset_1") -> None:
    session.add(City(city_id="city_test", name="Test City", country="US"))
    await session.flush()
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
        "sent_at": dt.datetime.now(dt.UTC).isoformat(),
        "events": [{"ts": dt.datetime.now(dt.UTC).isoformat(), "type": "fill_ratio", "value": 0.7}],
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
        "sent_at": dt.datetime.now(dt.UTC).isoformat(),
        "events": [{"ts": dt.datetime.now(dt.UTC).isoformat(), "type": "fill_ratio", "value": 0.7}],
    }
    headers = {"Authorization": "Bearer dev-ingest-token", "Idempotency-Key": "key-1"}

    res1 = await app_client.post("/v1/telemetry/events:batch", json=payload, headers=headers)
    assert res1.status_code == 200
    body1 = res1.json()

    count1 = await db_session.scalar(select(func.count()).select_from(TelemetryObservation))
    assert count1 == 1

    res2 = await app_client.post("/v1/telemetry/events:batch", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json() == body1

    payload["events"].append(
        {"ts": dt.datetime.now(dt.UTC).isoformat(), "type": "fill_ratio", "value": 0.8}
    )
    res3 = await app_client.post("/v1/telemetry/events:batch", json=payload, headers=headers)
    assert res3.status_code == 409
    assert res3.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    count2 = await db_session.scalar(select(func.count()).select_from(TelemetryObservation))
    assert count2 == 1


@pytest.mark.asyncio
async def test_ingest_partial_failure(app_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_asset(db_session)
    payload = {
        "device_id": "asset_1",
        "sent_at": dt.datetime.now(dt.UTC).isoformat(),
        "events": [
            {"ts": dt.datetime.now(dt.UTC).isoformat(), "type": "fill_ratio", "value": 0.7},
            {"ts": dt.datetime.now(dt.UTC).isoformat(), "type": "", "value": 0.2},
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


@pytest.mark.asyncio
async def test_expired_key_can_be_reused_without_pruning_unrelated_keys(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_asset(db_session)
    old_timestamp = dt.datetime.now(dt.UTC) - dt.timedelta(days=8)
    db_session.add_all(
        [
            IngestIdempotency(
                idempotency_key=key,
                device_id="asset_1",
                response={"device_id": "asset_1", "received": 0, "accepted": 0, "rejected": 0, "results": []},
                created_at=old_timestamp,
            )
            for key in ("key-expired", "key-unrelated-expired")
        ]
    )
    await db_session.commit()

    payload = {
        "device_id": "asset_1",
        "sent_at": dt.datetime.now(dt.UTC).isoformat(),
        "events": [
            {
                "ts": dt.datetime.now(dt.UTC).isoformat(),
                "type": "fill_ratio",
                "value": 0.7,
            }
        ],
    }
    headers = {"Authorization": "Bearer dev-ingest-token", "Idempotency-Key": "key-expired"}
    response = await app_client.post("/v1/telemetry/events:batch", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    # The HTTP fixture shares a session; real requests use fresh sessions.
    db_session.expire_all()
    renewed = await db_session.get(IngestIdempotency, "key-expired")
    assert renewed is not None
    assert renewed.created_at > old_timestamp
    # An ordinary telemetry request must never sweep other callers' keys.
    assert await db_session.get(IngestIdempotency, "key-unrelated-expired") is not None


@pytest.mark.asyncio
async def test_idempotency_maintenance_deletes_only_bounded_expired_rows(
    db_session: AsyncSession,
) -> None:
    await _seed_asset(db_session)
    now = dt.datetime.now(dt.UTC)
    db_session.add_all(
        [
            IngestIdempotency(
                idempotency_key=f"expired-{i}",
                device_id="asset_1",
                response={},
                created_at=now - dt.timedelta(days=8),
            )
            for i in range(3)
        ]
    )
    db_session.add(
        IngestIdempotency(
            idempotency_key="new-key",
            device_id="asset_1",
            response={},
            created_at=now - dt.timedelta(days=1),
        )
    )
    await db_session.commit()

    assert await prune_expired_idempotency(db_session, batch_size=2) == 2
    await db_session.commit()
    assert await db_session.scalar(select(func.count()).select_from(IngestIdempotency)) == 2

    assert await prune_expired_idempotency(db_session, batch_size=2) == 1
    await db_session.commit()
    assert await db_session.scalar(select(func.count()).select_from(IngestIdempotency)) == 1
    assert await db_session.get(IngestIdempotency, "new-key") is not None
