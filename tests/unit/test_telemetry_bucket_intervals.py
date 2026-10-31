from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Interval
from sqlalchemy.dialects.postgresql import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession

import floodmvp.api.routers.telemetry as telemetry_router
from floodmvp.api.main import app
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.telemetry import get_observations

START = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
END = START + dt.timedelta(days=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("granularity", "include_gaps", "scenario_id", "bucket_function", "expected"),
    [
        ("1h", False, None, "time_bucket(", dt.timedelta(hours=1)),
        ("5m", True, None, "generate_series(", dt.timedelta(minutes=5)),
        ("5m", False, "scenario_1", "time_bucket(", dt.timedelta(minutes=5)),
        ("5 minutes", True, "scenario_1", "generate_series(", dt.timedelta(minutes=5)),
    ],
)
async def test_observation_queries_bind_typed_bucket_intervals(
    granularity: str,
    include_gaps: bool,
    scenario_id: str | None,
    bucket_function: str,
    expected: dt.timedelta,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.all.return_value = []
    session.execute.return_value = result

    rows = await get_observations(
        session,
        "pipe_1",
        "fill_ratio",
        START,
        END,
        granularity,
        "avg",
        include_gaps=include_gaps,
        scenario_id=scenario_id,
    )

    assert rows == []
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=asyncpg.dialect())
    assert bucket_function in str(compiled)
    assert "time_bucket_gapfill" not in str(compiled)
    assert "::INTERVAL" in str(compiled)
    assert compiled.params["bucket_interval"] == expected
    assert isinstance(compiled.binds["bucket_interval"].type, Interval)


@pytest.mark.asyncio
async def test_gapfilled_observations_limit_grid_size_before_database_access() -> None:
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(ValueError, match="at most 10000 buckets"):
        await get_observations(
            session, "pipe_1", "fill_ratio", START, END, "1s", "avg", include_gaps=True
        )

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_five_minute_continuous_aggregate_keeps_fast_path() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.all.return_value = [(START, 0.42)]
    session.execute.return_value = result

    rows = await get_observations(session, "pipe_1", "fill_ratio", START, END, "5 minutes", "avg")

    assert rows == [(START, 0.42)]
    statement = session.execute.await_args.args[0]
    assert "telemetry_observation_5m" in str(statement)


@pytest.mark.asyncio
@pytest.mark.parametrize("granularity", ["invalid", "0m", "31d", "1h; DROP TABLE x"])
@pytest.mark.parametrize("include_gaps", [False, True])
async def test_invalid_bucket_intervals_rejected_without_database_access(
    granularity: str, include_gaps: bool
) -> None:
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(ValueError, match="granularity"):
        await get_observations(
            session,
            "pipe_1",
            "fill_ratio",
            START,
            END,
            granularity,
            "avg",
            include_gaps=include_gaps,
        )

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "scenario_params"),
    [
        ("/v1/assets/pipe_1/observations", {}),
        (
            "/v1/assets/pipe_1/observations:compare",
            {"base_scenario_id": "baseline", "compare_scenario_id": "comparison"},
        ),
    ],
)
async def test_observation_endpoints_return_400_for_invalid_intervals(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    scenario_params: dict[str, str],
) -> None:
    async def _override_session():
        yield None

    async def _resolve_scenario(_session: AsyncSession, scenario_id: str) -> str:
        return scenario_id

    monkeypatch.setattr(telemetry_router, "resolve_scenario_id", _resolve_scenario)
    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                path,
                params={
                    "metric": "fill_ratio",
                    "from": START.isoformat(),
                    "to": END.isoformat(),
                    "granularity": "31d",
                    **scenario_params,
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
