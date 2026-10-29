"""City validation for persisted calibration overrides."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.config.settings import settings
from floodmvp.models.db import AnalyticsThresholdOverride, City
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    """Exercise real API validation against an isolated PostgreSQL database."""
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_session, None)
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


@pytest.mark.asyncio
async def test_override_city_and_thresholds_are_validated_before_insert(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reject unknown cities and invalid values but persist a valid override."""
    db_session.add(City(city_id="city_calibration", name="Calibration City", country="PT"))
    await db_session.commit()

    missing = await client.post(
        "/v1/analytics/calibration/overrides",
        json={"city_id": "no_such_city", "thresholds": {"risk_fill_watch": 1.2}},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CITY_NOT_FOUND"

    invalid = await client.post(
        "/v1/analytics/calibration/overrides",
        json={"city_id": "city_calibration", "thresholds": {"overflow_min_duration_minutes": -2}},
    )
    assert invalid.status_code == 422

    valid = await client.post(
        "/v1/analytics/calibration/overrides",
        json={
            "city_id": "city_calibration",
            "season": "month-10",
            "thresholds": {"risk_fill_watch": 1.1, "risk_fill_warning": 1.3},
        },
    )
    assert valid.status_code == 200
    assert valid.json()["thresholds"]["risk_fill_warning"] == 1.3

    overrides = (await db_session.execute(select(AnalyticsThresholdOverride))).scalars().all()
    assert len(overrides) == 1
    assert overrides[0].city_id == "city_calibration"
    assert overrides[0].season == "month-10"
