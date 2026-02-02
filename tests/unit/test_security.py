from __future__ import annotations

import pytest
from httpx import AsyncClient

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.config.settings import settings
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
async def test_rate_limit_enforced(client: AsyncClient) -> None:
    api_main._RATE_LIMITS.clear()
    prev_rate = settings.rate_limit_rps
    prev_burst = settings.rate_limit_burst
    settings.rate_limit_rps = 0.0
    settings.rate_limit_burst = 1
    try:
        res1 = await client.get("/v1/health")
        assert res1.status_code == 200
        res2 = await client.get("/v1/health")
        assert res2.status_code == 429
        body = res2.json()
        assert body["error"]["code"] == "RATE_LIMITED"
    finally:
        settings.rate_limit_rps = prev_rate
        settings.rate_limit_burst = prev_burst
        api_main._RATE_LIMITS.clear()


@pytest.mark.asyncio
async def test_assets_cache_control(client: AsyncClient, monkeypatch) -> None:
    async def _fake_list_assets(*args, **kwargs):
        return []

    monkeypatch.setattr("floodmvp.api.routers.assets.list_assets", _fake_list_assets)
    res = await client.get("/v1/cities/c1/assets")
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "public, max-age=60"


@pytest.mark.asyncio
async def test_analytics_api_key_required(client: AsyncClient) -> None:
    prev_key = settings.analytics_api_key
    settings.analytics_api_key = "secret"
    try:
        res = await client.post("/v1/analytics/jobs", json={"type": "export_csv", "query": {"asset_ids": ["a"], "metric": "m", "from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"}})
        assert res.status_code == 401
        body = res.json()
        assert body["error"]["code"] == "UNAUTHORIZED"
    finally:
        settings.analytics_api_key = prev_key
