from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from floodmvp.api.main import app
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    async def _override_session():
        yield None

    async def _list_cities(_session):
        return [SimpleNamespace(city_id="city_test", name="Test City", country="US")]

    async def _get_city(_session, _city_id: str):
        return SimpleNamespace(city_id="city_test", name="Test City", country="US")

    async def _list_assets(*_args, **_kwargs):
        return [
            SimpleNamespace(
                asset_id="pipe_1",
                city_id="city_test",
                asset_type="pipe",
                name="Pipe 1",
                geom=None,
                props={},
            )
        ]

    async def _list_metrics(*_args, **_kwargs):
        return ["fill_ratio"]

    async def _resolve_scenario_id(_session, scenario_id: str | None):
        if scenario_id == "missing":
            return None
        return scenario_id or "scenario_1"

    async def _list_scenarios(_session):
        return [
            {
                "scenario_id": "scenario_1",
                "name": "heavy_rain",
                "start_ts": "2026-02-01T00:00:00Z",
                "end_ts": "2026-02-02T00:00:00Z",
            }
        ]

    async def _get_observations(*_args, **_kwargs):
        return [(dt.datetime(2026, 2, 1, 12, 0, tzinfo=dt.UTC), 0.42)]

    async def _list_events(*_args, **_kwargs):
        return [
            SimpleNamespace(
                event_id="evt_1",
                event_type="overflow",
                severity=2,
                start_ts=dt.datetime(2026, 2, 1, 10, 0, tzinfo=dt.UTC),
                end_ts=dt.datetime(2026, 2, 1, 12, 0, tzinfo=dt.UTC),
                asset_ids=["pipe_1"],
                summary="Overflow risk detected",
            )
        ]

    async def _get_city_status(*_args, **_kwargs):
        return {
            "city_id": "city_test",
            "risk": "low",
            "active_events": 1,
            "hotspots": 1,
            "updated_at": "2026-02-02T12:23:13Z",
        }

    async def _get_city_summary(*_args, **_kwargs):
        return {
            "city_id": "city_test",
            "now": "2026-02-02T12:00:00Z",
            "rain_mmph": 3.2,
            "river_level_m": 1.8,
            "status_counts": {"normal": 10, "watch": 2, "warning": 1},
        }

    async def _list_hotspots(*_args, **_kwargs):
        return [SimpleNamespace(asset_id="pipe_1", score=42.5, details={})]

    async def _list_analytics_runs(*_args, **_kwargs):
        return [
            SimpleNamespace(
                run_id="run_1",
                city_id="city_test",
                start_ts=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
                end_ts=dt.datetime(2026, 2, 2, tzinfo=dt.UTC),
                status="completed",
                version="v1",
                params={},
                metrics={},
                created_at=dt.datetime(2026, 2, 2, tzinfo=dt.UTC),
                updated_at=dt.datetime(2026, 2, 2, tzinfo=dt.UTC),
            )
        ]

    import floodmvp.storage.repos.analytics as analytics_repo
    import floodmvp.storage.repos.assets as assets_repo
    import floodmvp.storage.repos.telemetry as telemetry_repo

    monkeypatch.setattr(assets_repo, "list_cities", _list_cities)
    monkeypatch.setattr(assets_repo, "get_city", _get_city)
    monkeypatch.setattr(assets_repo, "list_assets", _list_assets)

    monkeypatch.setattr(telemetry_repo, "list_metrics", _list_metrics)
    monkeypatch.setattr(telemetry_repo, "resolve_scenario_id", _resolve_scenario_id)
    monkeypatch.setattr(telemetry_repo, "list_scenarios", _list_scenarios)
    monkeypatch.setattr(telemetry_repo, "get_observations", _get_observations)

    monkeypatch.setattr(analytics_repo, "list_events", _list_events)
    monkeypatch.setattr(analytics_repo, "get_city_status", _get_city_status)
    monkeypatch.setattr(analytics_repo, "get_city_summary", _get_city_summary)
    monkeypatch.setattr(analytics_repo, "list_hotspots", _list_hotspots)
    monkeypatch.setattr(analytics_repo, "list_analytics_runs", _list_analytics_runs)

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_and_metrics(client: AsyncClient) -> None:
    res = await client.get("/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res = await client.get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text


@pytest.mark.asyncio
async def test_cities_and_assets(client: AsyncClient) -> None:
    res = await client.get("/v1/cities")
    assert res.status_code == 200
    assert res.json()[0]["city_id"] == "city_test"

    res = await client.get("/v1/cities/city_test/assets?bbox=-1,1,1,2&type=pipe")
    assert res.status_code == 200
    assert res.json()[0]["asset_id"] == "pipe_1"


@pytest.mark.asyncio
async def test_telemetry_endpoints(client: AsyncClient) -> None:
    res = await client.get("/v1/telemetry/scenarios")
    assert res.status_code == 200
    assert res.json()[0]["scenario_id"] == "scenario_1"

    res = await client.get("/v1/assets/pipe_1/metrics")
    assert res.status_code == 200
    assert "fill_ratio" in res.json()

    res = await client.get(
        "/v1/assets/pipe_1/observations?metric=fill_ratio&from=2026-02-01T00:00:00Z&to=2026-02-02T00:00:00Z"
    )
    assert res.status_code == 200
    assert res.json()["metric"] == "fill_ratio"


@pytest.mark.asyncio
async def test_analytics_endpoints(client: AsyncClient) -> None:
    res = await client.get("/v1/cities/city_test/status")
    assert res.status_code == 200
    assert res.json()["city_id"] == "city_test"

    res = await client.get("/v1/cities/city_test/summary?minutes=15")
    assert res.status_code == 200
    assert res.json()["city_id"] == "city_test"

    res = await client.get("/v1/hotspots?city_id=city_test")
    assert res.status_code == 200
    assert res.json()[0]["asset_id"] == "pipe_1"

    res = await client.get(
        "/v1/events?city_id=city_test&type=overflow&from=2026-02-01T00:00:00Z&to=2026-02-02T00:00:00Z"
    )
    assert res.status_code == 200
    assert res.json()[0]["event_id"] == "evt_1"

    res = await client.get("/v1/analytics/runs?city_id=city_test")
    assert res.status_code == 200
    assert res.json()[0]["run_id"] == "run_1"
