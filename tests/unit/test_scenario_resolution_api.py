from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import floodmvp.api.routers.telemetry as telemetry_router
from floodmvp.api.main import app
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.telemetry import resolve_scenario_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_id", "resolved_id", "query_clause"),
    [
        ("run_known", "run_known", "WHERE scenario_run.scenario_id ="),
        ("run_missing", None, "WHERE scenario_run.scenario_id ="),
        ("latest", "run_recent", "ORDER BY scenario_run.created_at DESC"),
        ("latest", None, "ORDER BY scenario_run.created_at DESC"),
    ],
)
async def test_scenario_resolution_checks_database_existence(
    scenario_id: str, resolved_id: str | None, query_clause: str
) -> None:
    """An explicit ID must not be accepted without a database lookup."""
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = resolved_id

    result = await resolve_scenario_id(session, scenario_id)

    assert result == resolved_id
    session.scalar.assert_awaited_once()
    statement = str(session.scalar.await_args.args[0])
    assert "FROM scenario_run" in statement
    assert query_clause in statement


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    async def _override_session() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/assets/pipe_1/metrics", {"scenario_id": "missing"}),
        (
            "/v1/assets/pipe_1/observations",
            {
                "scenario_id": "missing",
                "metric": "fill_ratio",
                "from": "2026-02-01T00:00:00Z",
                "to": "2026-02-01T01:00:00Z",
            },
        ),
        (
            "/v1/assets/pipe_1/observations:compare",
            {
                "base_scenario_id": "missing",
                "compare_scenario_id": "run_known",
                "metric": "fill_ratio",
                "from": "2026-02-01T00:00:00Z",
                "to": "2026-02-01T01:00:00Z",
            },
        ),
        (
            "/v1/assets/pipe_1/observations:compare",
            {
                "base_scenario_id": "run_known",
                "compare_scenario_id": "missing",
                "metric": "fill_ratio",
                "from": "2026-02-01T00:00:00Z",
                "to": "2026-02-01T01:00:00Z",
            },
        ),
    ],
)
async def test_unknown_scenario_returns_structured_404(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    params: dict[str, str],
) -> None:
    async def _resolve(_session: None, scenario_id: str) -> str | None:
        return None if scenario_id == "missing" else scenario_id

    query_observations = AsyncMock()
    query_metrics = AsyncMock()
    monkeypatch.setattr(telemetry_router, "resolve_scenario_id", _resolve)
    monkeypatch.setattr(telemetry_router, "get_observations", query_observations)
    monkeypatch.setattr(telemetry_router, "get_observations_map", query_observations)
    monkeypatch.setattr(telemetry_router, "list_metrics", query_metrics)

    response = await client.get(path, params=params)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SCENARIO_NOT_FOUND"
    assert response.json()["error"]["request_id"]
    query_observations.assert_not_awaited()
    query_metrics.assert_not_awaited()
