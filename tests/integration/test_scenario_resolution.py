from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.main import app
from floodmvp.models.db import Asset, City, ScenarioRun, TelemetryObservation
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.telemetry import resolve_scenario_id


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_scenario_ids_are_validated_against_real_database(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Distinguish nonexistent scenarios from valid scenarios with sparse telemetry."""
    start = dt.datetime(2026, 2, 1, 0, 0, tzinfo=dt.UTC)
    db_session.add(City(city_id="city_scenarios", name="Scenario City", country="PT"))
    await db_session.flush()
    db_session.add_all(
        [
            Asset(
                asset_id="pipe_scenarios",
                city_id="city_scenarios",
                asset_type="pipe",
                name="Scenario Pipe",
                geom=WKTElement("LINESTRING(-8.6 41.1, -8.61 41.11)", srid=4326),
                props={},
            ),
            ScenarioRun(
                scenario_id="run_older",
                name="Older scenario",
                start_ts=start,
                end_ts=start + dt.timedelta(hours=1),
                created_at=start,
            ),
            ScenarioRun(
                scenario_id="run_recent",
                name="Recent scenario",
                start_ts=start,
                end_ts=start + dt.timedelta(hours=1),
                created_at=start + dt.timedelta(minutes=5),
            ),
        ]
    )
    await db_session.flush()
    db_session.add(
        TelemetryObservation(
            asset_id="pipe_scenarios",
            metric="fill_ratio",
            ts=start,
            value=0.42,
            quality_flag="ok",
            source="synthetic",
            scenario_id="run_recent",
        )
    )
    await db_session.commit()

    assert await resolve_scenario_id(db_session, "run_recent") == "run_recent"
    assert await resolve_scenario_id(db_session, "latest") == "run_recent"
    assert await resolve_scenario_id(db_session, "missing") is None

    base = "/v1/assets/pipe_scenarios"
    metrics = await client.get(f"{base}/metrics", params={"scenario_id": "latest"})
    assert metrics.status_code == 200
    assert metrics.json() == ["fill_ratio"]

    # A registered scenario with no observations is not a missing scenario.
    empty = await client.get(f"{base}/metrics", params={"scenario_id": "run_older"})
    assert empty.status_code == 200
    assert empty.json() == []

    missing = await client.get(f"{base}/metrics", params={"scenario_id": "missing"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SCENARIO_NOT_FOUND"

    observation_params = {
        "metric": "fill_ratio",
        "from": start.isoformat(),
        "to": (start + dt.timedelta(minutes=5)).isoformat(),
    }
    for params in (
        {"scenario_id": "missing"},
        {"base_scenario_id": "missing", "compare_scenario_id": "run_recent"},
        {"base_scenario_id": "run_recent", "compare_scenario_id": "missing"},
    ):
        endpoint = "observations" if "scenario_id" in params else "observations:compare"
        response = await client.get(f"{base}/{endpoint}", params={**observation_params, **params})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SCENARIO_NOT_FOUND"

    existing = await client.get(
        f"{base}/observations", params={**observation_params, "scenario_id": "run_recent"}
    )
    assert existing.status_code == 200
    assert [row["value"] for row in existing.json()["series"]] == [0.42]
