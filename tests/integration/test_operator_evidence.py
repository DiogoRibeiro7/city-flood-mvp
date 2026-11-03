from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.main import app
from floodmvp.models.db import (
    AnalyticsEvent,
    AnalyticsRun,
    Asset,
    City,
    ScenarioRun,
    TelemetryObservation,
)
from floodmvp.storage.db import get_session

START = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_raw_evidence_preserves_quality_bounds_and_scenario_isolation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(City(city_id="city", name="Fixture", country="PT"))
    await db_session.flush()
    db_session.add(
        Asset(
            asset_id="gauge",
            city_id="city",
            asset_type="rain_gauge",
            name="Fixture gauge",
            geom=WKTElement("POINT(-8.6 41.1)", srid=4326),
            props={},
        )
    )
    db_session.add(
        ScenarioRun(
            scenario_id="scenario",
            name="Synthetic",
            start_ts=START,
            end_ts=START + dt.timedelta(hours=1),
        )
    )
    await db_session.flush()
    for minute, scenario in ((0, None), (1, "scenario"), (5, None), (10, None)):
        db_session.add(
            TelemetryObservation(
                asset_id="gauge",
                metric="rain_mmph",
                ts=START + dt.timedelta(minutes=minute),
                value=float("nan") if minute == 5 else 8.0,
                quality_flag="unverified",
                source="noaa_ghcnh",
                source_type="fixture",
                source_id="station",
                scenario_id=scenario,
                lineage={
                    "observation": {"interval_minutes": 360, "private_payload": "hidden"},
                    "conversion": "six-hour mean",
                    "chunk": {"url": "private"},
                },
            )
        )
    await db_session.commit()
    url = "/v1/assets/gauge/observations/evidence"
    params = {
        "metric": "rain_mmph",
        "from": START.isoformat(),
        "to": (START + dt.timedelta(minutes=10)).isoformat(),
    }
    first = await client.get(url, params={**params, "limit": 1})
    assert first.status_code == 200
    payload = first.json()
    assert payload["has_more"] is True and payload["next_offset"] == 1
    assert payload["scenario_id"] is None
    row = payload["rows"][0]
    assert row["quality_flag"] == "unverified" and row["source_id"] == "station"
    assert row["measurement_context"] == {"interval_minutes": 360, "conversion": "six-hour mean"}
    second = (await client.get(url, params={**params, "limit": 1, "offset": 1})).json()
    assert second["rows"][0]["value"] is None
    assert second["has_more"] is False and second["next_offset"] is None
    scenario = (await client.get(url, params={**params, "scenario_id": "latest"})).json()
    assert scenario["scenario_id"] == "scenario" and len(scenario["rows"]) == 1
    assert (await client.get(url, params={**params, "scenario_id": "absent"})).status_code == 404
    assert (await client.get(url.replace("gauge", "absent"), params=params)).status_code == 404
    assert (await client.get(url, params={**params, "to": params["from"]})).status_code == 400
    assert (await client.get(url, params={**params, "limit": 501})).status_code == 400
    assert (await client.get(url, params={**params, "offset": -1})).status_code == 400


@pytest.mark.asyncio
async def test_event_explanation_uses_producing_run_not_latest(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(City(city_id="city", name="Fixture", country="PT"))
    await db_session.flush()
    for run_id, threshold in (("original", 5), ("newest", 50)):
        db_session.add(
            AnalyticsRun(
                run_id=run_id,
                city_id="city",
                start_ts=START,
                end_ts=START + dt.timedelta(hours=1),
                status="completed",
                version="fixture-v1",
                params={"rain_threshold_mmph": threshold},
                metrics={},
            )
        )
    await db_session.flush()
    db_session.add(
        AnalyticsEvent(
            event_id="event",
            run_id="original",
            city_id="city",
            event_type="rain",
            severity=1,
            confidence=0.8,
            start_ts=START,
            end_ts=START + dt.timedelta(minutes=20),
            asset_ids=[],
            summary="Fixture",
        )
    )
    await db_session.commit()
    response = await client.get("/v1/events/event/run")
    assert response.status_code == 200
    assert response.json()["run_id"] == "original"
    assert response.json()["params"] == {"rain_threshold_mmph": 5}
    assert "max_gap_minutes" not in response.json()["params"]
    assert (await client.get("/v1/events/missing/run")).status_code == 404
