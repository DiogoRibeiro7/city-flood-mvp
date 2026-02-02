from __future__ import annotations

import pytest
from httpx import AsyncClient

from floodmvp.api.main import app
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client() -> AsyncClient:
    async def _override_session():
        yield None

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_app_error_envelope(client: AsyncClient) -> None:
    res = await client.get("/v1/cities/test_city/assets?bbox=bad")
    assert res.status_code == 400
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert "request_id" in body["error"]


@pytest.mark.asyncio
async def test_validation_error_envelope(client: AsyncClient) -> None:
    res = await client.get("/v1/assets/asset_1/observations")
    assert res.status_code == 400
    body = res.json()
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert "errors" in body["error"]["details"]


@pytest.mark.asyncio
async def test_not_found_envelope(client: AsyncClient) -> None:
    res = await client.get("/v1/does-not-exist")
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]
