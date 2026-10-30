"""Validate export references before jobs are written to PostgreSQL."""

from __future__ import annotations

import datetime as dt

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.models.db import Asset, City, ExportJob
from floodmvp.storage.db import get_session

START = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
END = START + dt.timedelta(hours=1)


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncClient:
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()

    async def _session_override():
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.clear()
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


async def _seed_assets(session: AsyncSession) -> None:
    session.add_all(
        [
            City(city_id="city_export_a", name="Export A", country="PT"),
            City(city_id="city_export_b", name="Export B", country="PT"),
        ]
    )
    await session.flush()
    session.add_all(
        [
            Asset(
                asset_id="pipe_export_a",
                city_id="city_export_a",
                asset_type="pipe",
                name="Pipe A",
                geom=WKTElement("LINESTRING(-8.610 41.150, -8.611 41.151)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="pump_export_b",
                city_id="city_export_b",
                asset_type="pump",
                name="Pump B",
                geom=WKTElement("POINT(-8.612 41.152)", srid=4326),
                props={},
            ),
        ]
    )
    await session.commit()


def _export_query(**overrides: object) -> dict[str, object]:
    query: dict[str, object] = {
        "asset_ids": ["pipe_export_a"],
        "metric": "fill_ratio",
        "from": START.isoformat(),
        "to": END.isoformat(),
    }
    query.update(overrides)
    return {"type": "export_csv", "query": query}


@pytest.mark.asyncio
async def test_export_jobs_reject_unknown_or_mismatched_references(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_assets(db_session)
    invalid_cases = [
        (_export_query(city_id="city_missing"), "CITY_NOT_FOUND"),
        (
            {
                "type": "report_csv",
                "query": {
                    "city_id": "city_missing",
                    "from": START.isoformat(),
                    "to": END.isoformat(),
                },
            },
            "CITY_NOT_FOUND",
        ),
        (_export_query(asset_ids=["asset_missing"]), "ASSET_NOT_FOUND"),
        (_export_query(city_id="city_export_b"), "ASSET_NOT_FOUND"),
        (_export_query(asset_type="pump"), "ASSET_NOT_FOUND"),
    ]

    for payload, expected_code in invalid_cases:
        response = await client.post("/v1/analytics/jobs", json=payload)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == expected_code

    assert await db_session.scalar(select(func.count()).select_from(ExportJob)) == 0


@pytest.mark.asyncio
async def test_export_jobs_queue_valid_city_and_asset_filters(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_assets(db_session)
    valid_cases = [
        _export_query(city_id="city_export_a", asset_type="pipe"),
        _export_query(city_id="city_export_a", asset_ids=[]),
        {
            "type": "report_csv",
            "query": {
                "city_id": "city_export_a",
                "from": START.isoformat(),
                "to": END.isoformat(),
            },
        },
    ]

    for payload in valid_cases:
        response = await client.post("/v1/analytics/jobs", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

    assert await db_session.scalar(select(func.count()).select_from(ExportJob)) == 3
