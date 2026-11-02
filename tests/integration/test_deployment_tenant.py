"""Dedicated-deployment admission protects actual records in the disposable DB."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator

import jwt
import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api import main as api_main
from floodmvp.config.settings import settings
from floodmvp.models.db import Asset, City, Note
from floodmvp.storage.db import get_session


async def test_foreign_tenant_cannot_read_dedicated_database(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "synthetic-tenant-integration-secret-32-bytes"
    for key, value in {
        "app_env": "production",
        "deployment_tenant_id": "tenant-a",
        "jwt_secret": secret,
        "jwt_issuer": None,
        "jwt_audience": None,
        "jwt_tenant_claim": "tenant",
        "jwt_roles_claim": "roles",
        "analytics_api_key": "synthetic-integration-legacy-key",
        "rate_limit_burst": 1000,
        "tenant_quota_burst": 1000,
    }.items():
        monkeypatch.setattr(settings, key, value)
    db_session.add(City(city_id="city-a", name="Private city A", country="PT"))
    await db_session.flush()
    db_session.add(
        Asset(
            asset_id="asset-a",
            city_id="city-a",
            asset_type="pump",
            name="Private pump A",
            geom=WKTElement("POINT(-8.61 41.15)", srid=4326),
            props={},
        )
    )
    db_session.add(
        Note(
            note_id="note-a",
            city_id="city-a",
            title="Private inspection",
            body="Tenant A incident detail",
            author="Synthetic operator",
        )
    )
    await db_session.commit()
    sessions_used = 0

    async def session() -> AsyncGenerator[AsyncSession, None]:
        nonlocal sessions_used
        sessions_used += 1
        yield db_session

    def headers(tenant: str) -> dict[str, str]:
        token = jwt.encode(
            {
                "sub": "operator",
                "tenant": tenant,
                "roles": ["admin"],
                "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
            },
            secret,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant-a"}

    api_main.app.dependency_overrides[get_session] = session
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=api_main.app), base_url="http://test"
        ) as client:
            for path in (
                "/v1/cities",
                "/v1/cities/city-a",
                "/v1/assets/asset-a",
                "/v1/notes/note-a",
            ):
                denied = await client.get(path, headers=headers("tenant-b"))
                assert denied.status_code == 403
                assert "Private" not in denied.text
            assert sessions_used == 0
            owned = await client.get("/v1/assets/asset-a", headers=headers("tenant-a"))
            assert owned.status_code == 200
            assert owned.json()["name"] == "Private pump A"
            assert owned.headers["cache-control"] == "private, no-store"
            note = await client.get("/v1/notes/note-a", headers=headers("tenant-a"))
            assert note.json()["body"] == "Tenant A incident detail"
            monkeypatch.setattr(settings, "jwt_secret", None)
            legacy = await client.get(
                "/v1/cities", headers={"X-API-Key": "synthetic-integration-legacy-key"}
            )
            assert legacy.status_code == 200
            assert legacy.json()[0]["city_id"] == "city-a"
    finally:
        api_main.app.dependency_overrides.clear()
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()
