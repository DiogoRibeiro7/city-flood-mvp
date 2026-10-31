from __future__ import annotations

import datetime as dt
from collections import OrderedDict

import pytest
from httpx import ASGITransport, AsyncClient

import floodmvp.api.main as api_main
from floodmvp.api.main import app
from floodmvp.api.validation import parse_query_timestamp
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    async def _override_session():
        # The request must fail validation before touching the database.
        yield None

    # Isolate this endpoint test from middleware rate limits shared across tests.
    monkeypatch.setattr(api_main, "_RATE_LIMITS", OrderedDict())
    monkeypatch.setattr(api_main, "_TENANT_LIMITS", OrderedDict())
    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-02-01T00:00:00Z", dt.datetime(2026, 2, 1, tzinfo=dt.UTC)),
        ("2026-02-01T01:00:00+01:00", dt.datetime(2026, 2, 1, tzinfo=dt.UTC)),
        ("2026-02-01T00:00:00", dt.datetime(2026, 2, 1, tzinfo=dt.UTC)),
    ],
)
def test_query_timestamp_preserves_utc_normalization(value: str, expected: dt.datetime) -> None:
    assert parse_query_timestamp(value, "from") == expected


@pytest.mark.parametrize(
    ("path", "required"),
    [
        ("/v1/events", {"city_id": "city_test"}),
        ("/v1/assets/pipe_1/observations", {"metric": "fill_ratio"}),
        (
            "/v1/assets/pipe_1/observations:compare",
            {
                "metric": "fill_ratio",
                "base_scenario_id": "base",
                "compare_scenario_id": "test",
            },
        ),
        ("/v1/analytics/calibration/recommendations", {"city_id": "city_test"}),
    ],
)
@pytest.mark.parametrize("invalid_parameter", ["from", "to"])
@pytest.mark.parametrize(
    "invalid_value",
    ["not-a-timestamp", "2026-02-31T00:00:00Z", "2026-02-01T00:00:00+25:00"],
)
@pytest.mark.asyncio
async def test_invalid_query_timestamps_return_structured_400(
    client: AsyncClient,
    path: str,
    required: dict[str, str],
    invalid_parameter: str,
    invalid_value: str,
) -> None:
    params = {
        "from": "2026-02-01T00:00:00Z",
        "to": "2026-02-02T00:00:00Z",
        **required,
    }
    params[invalid_parameter] = invalid_value

    response = await client.get(path, params=params)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["message"] == f"'{invalid_parameter}' must be a valid ISO 8601 timestamp"
    assert error["request_id"]


@pytest.mark.parametrize(
    ("path", "required"),
    [
        ("/v1/events", {"city_id": "city_test"}),
        ("/v1/assets/pipe_1/observations", {"metric": "fill_ratio"}),
        (
            "/v1/assets/pipe_1/observations:compare",
            {
                "metric": "fill_ratio",
                "base_scenario_id": "base",
                "compare_scenario_id": "test",
            },
        ),
        ("/v1/analytics/calibration/recommendations", {"city_id": "city_test"}),
    ],
)
@pytest.mark.asyncio
async def test_reversed_query_time_windows_still_return_400(
    client: AsyncClient,
    path: str,
    required: dict[str, str],
) -> None:
    response = await client.get(
        path,
        params={
            "from": "2026-02-02T00:00:00Z",
            "to": "2026-02-01T00:00:00Z",
            **required,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
