"""Exercise timestamp ties across filtered offset pages against PostgreSQL."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api import main as api_main
from floodmvp.config.settings import settings
from floodmvp.models.db import AnalyticsEvent, AnalyticsRun, Asset, City, Note
from floodmvp.storage.db import get_session

START = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


@pytest.fixture()
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()

    async def session() -> AsyncIterator[AsyncSession]:
        yield db_session

    api_main.app.dependency_overrides[get_session] = session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=api_main.app), base_url="http://test"
        ) as http:
            yield http
    finally:
        api_main.app.dependency_overrides.pop(get_session, None)
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["events", "notes"])
async def test_filtered_pages_have_unique_order_for_timestamp_ties(
    kind: str, client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add_all(
        [
            City(city_id="city_a", name="A", country="PT"),
            City(city_id="city_b", name="B", country="PT"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Asset(asset_id=asset, city_id="city_a", asset_type="pipe", name=asset, props={})
            for asset in ("asset_a", "asset_b")
        ]
    )
    db_session.add_all(
        [
            AnalyticsRun(
                run_id=run,
                city_id=city,
                start_ts=START,
                end_ts=START + dt.timedelta(hours=1),
                status="completed",
                version="v1",
                params={},
                metrics={},
            )
            for run, city in (("run_a", "city_a"), ("run_other", "city_a"), ("run_b", "city_b"))
        ]
    )
    await db_session.flush()

    # Insert ties out of ID order and mix timestamps to detect either missing sort key.
    values = [("d", 5), ("b", 5), ("0", 0), ("a", 5), ("z", 10), ("c", 5)]
    if kind == "events":
        for suffix, minute in values + [
            ("wrong_city", 5),
            ("wrong_run", 5),
            ("wrong_type", 5),
            ("outside", 120),
        ]:
            db_session.add(
                AnalyticsEvent(
                    event_id=f"event_{suffix}",
                    city_id="city_b" if suffix == "wrong_city" else "city_a",
                    run_id="run_b"
                    if suffix == "wrong_city"
                    else "run_other"
                    if suffix == "wrong_run"
                    else "run_a",
                    event_type="rain" if suffix == "wrong_type" else "overflow",
                    severity=1,
                    confidence=0.5,
                    start_ts=START + dt.timedelta(minutes=minute),
                    end_ts=START + dt.timedelta(minutes=minute + 1),
                    asset_ids=[],
                    summary="Controlled pagination fixture",
                )
            )
        query = {
            "city_id": "city_a",
            "run_id": "run_a",
            "type": "overflow",
            "from": START.isoformat(),
            "to": (START + dt.timedelta(hours=1)).isoformat(),
        }
        id_field, prefix = "event_id", "event"
    else:
        for suffix, minute in values + [("wrong_city", 5), ("wrong_asset", 5), ("wrong_event", 5)]:
            db_session.add(
                Note(
                    note_id=f"note_{suffix}",
                    city_id="city_b" if suffix == "wrong_city" else "city_a",
                    asset_id="asset_b" if suffix == "wrong_asset" else "asset_a",
                    event_id="event_other" if suffix == "wrong_event" else "event_a",
                    title="Controlled pagination fixture",
                    body="Synthetic",
                    author="Test",
                    created_at=START + dt.timedelta(minutes=minute),
                    updated_at=START,
                )
            )
        query = {"city_id": "city_a", "asset_id": "asset_a", "event_id": "event_a"}
        id_field, prefix = "note_id", "note"
    await db_session.commit()

    expected = [f"{prefix}_{suffix}" for suffix in ("z", "a", "b", "c", "d", "0")]
    for _ in range(2):
        paged = []
        for offset in (0, 2, 4, 6):
            response = await client.get(
                f"/v1/{kind}", params={**query, "limit": 2, "offset": offset}
            )
            assert response.status_code == 200
            ids = [row[id_field] for row in response.json()]
            assert ids == expected[offset : offset + 2]
            paged.extend(ids)
        assert paged == expected
        assert len(set(paged)) == len(paged)
    response = await client.get(f"/v1/{kind}", params={**query, "limit": 100})
    assert response.status_code == 200
    assert [row[id_field] for row in response.json()] == expected
