"""Exercise malformed requests through HTTP, including their published contract."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

import floodmvp.api.main as api_main
from floodmvp.common.errors import ErrorResponse
from floodmvp.config.settings import settings
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    async def no_database() -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr(api_main, "_RATE_LIMITS", OrderedDict())
    monkeypatch.setattr(api_main, "_TENANT_LIMITS", OrderedDict())
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    api_main.app.dependency_overrides[get_session] = no_database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=api_main.app, raise_app_exceptions=False),
            base_url="http://test",
            headers={"x-request-id": "req_contract"},
        ) as api:
            yield api
    finally:
        api_main.app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize(
    "thresholds",
    [
        '{"risk_fill_watch": 2, "risk_fill_warning": 1}',
        '{"overflow_fill_threshold": NaN}',
        '{"overflow_fill_threshold": Infinity}',
        '{"overflow_fill_threshold": -Infinity}',
    ],
)
async def test_calibration_validation_errors_are_json_safe(
    client: AsyncClient, thresholds: str
) -> None:
    response = await client.post(
        "/v1/analytics/calibration/overrides",
        content='{"city_id": "porto", "thresholds": ' + thresholds + "}",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["message"] == "Validation error"
    assert error["request_id"] == response.headers["x-request-id"] == "req_contract"
    assert error["details"]["errors"]
    ErrorResponse.model_validate(response.json())


@pytest.mark.parametrize("body", [b"{", b'"wrong body type"', b"\xff", b"{}"])
async def test_malformed_job_body_returns_400(client: AsyncClient, body: bytes) -> None:
    response = await client.post(
        "/v1/analytics/jobs", content=body, headers={"content-type": "application/json"}
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("job_type", ["export_csv", "report_csv"])
@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-01-02T00:00:00", "2026-01-01T00:00:00Z"),
        ("2026-01-01T00:00:00Z", "2026-01-01T01:00:00+01:00"),
        ("0001-01-01T00:00:00+01:00", "2026-01-01T00:00:00Z"),
    ],
)
async def test_invalid_job_windows_return_400(
    client: AsyncClient, job_type: str, start: str, end: str
) -> None:
    response = await client.post(
        "/v1/analytics/jobs",
        json={
            "type": job_type,
            "query": {
                "city_id": "porto",
                "asset_ids": [],
                "metric": "rain_mmph",
                "from": start,
                "to": end,
            },
        },
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=5001",
        "offset=-1",
        "limit=abc",
        "bbox=invalid",
        "radius_m=nan",
        "tag=invalid",
    ],
)
async def test_asset_filter_and_pagination_errors_return_400(
    client: AsyncClient, query: str
) -> None:
    response = await client.get(f"/v1/cities/porto/assets?{query}")

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/notes?city_id=porto",
        "/v1/events?city_id=porto&from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z",
    ],
)
@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "offset=-1"])
async def test_event_and_note_pagination_errors_return_400(
    client: AsyncClient, path: str, query: str
) -> None:
    response = await client.get(f"{path}&{query}")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
