"""Prevent notes from linking assets and analytics events across cities."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.config.settings import settings
from floodmvp.models.db import AnalyticsEvent, AnalyticsRun, Asset, City, Note
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    """Exercise the notes endpoint with a dedicated PostgreSQL test session."""
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    # Keep this multi-request integration test from exhausting the shared
    # in-memory request quotas for tests that run later in the same process.
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
async def test_note_references_must_belong_to_the_requested_city(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Reject nonexistent and cross-city references while persisting valid notes."""
    start = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
    db_session.add_all(
        [
            City(city_id="city_notes_a", name="Notes City A", country="PT"),
            City(city_id="city_notes_b", name="Notes City B", country="PT"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Asset(
                asset_id="asset_notes_a",
                city_id="city_notes_a",
                asset_type="pipe",
                name="A",
                props={},
            ),
            Asset(
                asset_id="asset_notes_b",
                city_id="city_notes_b",
                asset_type="pipe",
                name="B",
                props={},
            ),
            AnalyticsRun(
                run_id="run_notes_b",
                city_id="city_notes_b",
                start_ts=start,
                end_ts=start + dt.timedelta(hours=1),
                status="completed",
                version="v1",
                params={},
                metrics={},
            ),
        ]
    )
    await db_session.flush()
    db_session.add(
        AnalyticsEvent(
            event_id="event_notes_b",
            run_id="run_notes_b",
            city_id="city_notes_b",
            event_type="overflow",
            severity=2,
            confidence=0.7,
            start_ts=start,
            end_ts=start + dt.timedelta(minutes=30),
            asset_ids=["asset_notes_b"],
            summary="Possible overflow",
        )
    )
    await db_session.commit()

    base = {"city_id": "city_notes_a", "title": "Inspection", "body": "Check drain"}
    for overrides, error_code in (
        ({"city_id": "missing"}, "CITY_NOT_FOUND"),
        ({"asset_id": "missing"}, "ASSET_NOT_FOUND"),
        ({"asset_id": "asset_notes_b"}, "ASSET_NOT_FOUND"),
        ({"event_id": "missing"}, "EVENT_NOT_FOUND"),
        ({"event_id": "event_notes_b"}, "EVENT_NOT_FOUND"),
    ):
        response = await client.post("/v1/notes", json={**base, **overrides})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == error_code

    city_note = await client.post("/v1/notes", json=base)
    assert city_note.status_code == 200
    assert city_note.json()["asset_id"] is None

    valid_link = await client.post(
        "/v1/notes",
        json={
            **base,
            "city_id": "city_notes_b",
            "asset_id": "asset_notes_b",
            "event_id": "event_notes_b",
        },
    )
    assert valid_link.status_code == 200
    assert valid_link.json()["event_id"] == "event_notes_b"

    notes = (await db_session.execute(select(Note).order_by(Note.city_id))).scalars().all()
    assert [(note.city_id, note.asset_id, note.event_id) for note in notes] == [
        ("city_notes_a", None, None),
        ("city_notes_b", "asset_notes_b", "event_notes_b"),
    ]
