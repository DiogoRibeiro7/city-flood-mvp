from __future__ import annotations

from collections import OrderedDict
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

import floodmvp.api.main as api_main
import floodmvp.api.routers.assets as assets_router
from floodmvp.api.main import app
from floodmvp.api.routers.assets import _parse_bbox, _parse_near
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    async def _override_session() -> AsyncIterator[None]:
        yield None

    # A large parameter matrix should not exhaust middleware rate-limit buckets.
    monkeypatch.setattr(api_main, "_RATE_LIMITS", OrderedDict())
    monkeypatch.setattr(api_main, "_TENANT_LIMITS", OrderedDict())
    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_spatial_parsers_accept_wgs84_boundaries_and_optional_filters() -> None:
    assert _parse_bbox(None) is None
    assert _parse_near(None) is None
    assert _parse_bbox("-180,-90,180,90") == (-180.0, -90.0, 180.0, 90.0)
    assert _parse_near("180,90") == (180.0, 90.0)


@pytest.mark.parametrize(
    ("parameter", "value", "message"),
    [
        ("bbox", "1,2,3", "bbox must be"),
        ("bbox", "1,invalid,3,4", "bbox must be"),
        ("bbox", "NaN,41,-8,42", "bbox coordinates must be finite"),
        ("bbox", "-9,41,Infinity,42", "bbox coordinates must be finite"),
        ("bbox", "-181,41,-8,42", "bbox longitude must be between"),
        ("bbox", "-8,-91,-7,42", "bbox latitude must be between"),
        ("bbox", "-8,41,181,42", "bbox longitude must be between"),
        ("bbox", "-8,41,-7,91", "bbox latitude must be between"),
        ("bbox", "-7,41,-8,42", "bbox must have minLon"),
        ("bbox", "-8,42,-7,41", "bbox must have minLon"),
        ("bbox", "-8,41,-8,42", "bbox must have minLon"),
        ("bbox", "-8,41,-7,41", "bbox must have minLon"),
        ("near", "1", "near must be"),
        ("near", "1,invalid", "near must be"),
        ("near", "NaN,41", "near coordinates must be finite"),
        ("near", "-8,-Infinity", "near coordinates must be finite"),
        ("near", "181,41", "near longitude must be between"),
        ("near", "-8,91", "near latitude must be between"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_spatial_coordinates_return_structured_400(
    client: AsyncClient,
    parameter: str,
    value: str,
    message: str,
) -> None:
    response = await client.get("/v1/cities/city_test/assets", params={parameter: value})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert message in error["message"]
    assert error["request_id"]


@pytest.mark.parametrize("radius", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.asyncio
async def test_nonfinite_radius_returns_structured_400(client: AsyncClient, radius: str) -> None:
    response = await client.get(
        "/v1/cities/city_test/assets",
        params={"near": "-8.61,41.15", "radius_m": radius},
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["request_id"]


@pytest.mark.asyncio
async def test_valid_bbox_and_near_filters_reach_storage(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments: dict[str, Any] = {}

    async def _list_assets(_session: object, **kwargs: Any) -> list[object]:
        arguments.update(kwargs)
        return []

    monkeypatch.setattr(assets_router, "list_assets", _list_assets)
    response = await client.get(
        "/v1/cities/city_test/assets",
        params={
            "bbox": "-8.7,41.0,-8.5,41.3",
            "near": "-8.61,41.15",
            "radius_m": "500",
        },
    )

    assert response.status_code == 200
    assert response.json() == []
    assert arguments["bbox"] == (-8.7, 41.0, -8.5, 41.3)
    assert arguments["near"] == (-8.61, 41.15)
    assert arguments["radius_m"] == 500.0
