"""Regression tests for bounded request quotas and metric label cardinality."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import Mock

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.api.routers import notes as notes_router
from floodmvp.config.settings import Settings, settings
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Isolate API quota state and avoid database dependencies."""

    async def fake_session() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_session] = fake_session
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


@pytest.mark.asyncio
async def test_client_supplied_tenant_headers_cannot_reset_quota(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A public caller cannot rotate tenant IDs to bypass the shared quota."""
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    monkeypatch.setattr(settings, "rate_limit_rps", 100.0)
    monkeypatch.setattr(settings, "rate_limit_burst", 100)
    monkeypatch.setattr(settings, "tenant_quota_rps", 0.0001)
    monkeypatch.setattr(settings, "tenant_quota_burst", 1)

    first = await client.get("/v1/health", headers={"X-Tenant-Id": "tenant-a"})
    second = await client.get("/v1/health", headers={"X-Tenant-Id": "tenant-b"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "TENANT_RATE_LIMITED"
    assert list(api_main._TENANT_LIMITS) == ["public"]


@pytest.mark.asyncio
async def test_only_verified_credentials_define_tenant_identity(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JWT claims override forged headers; API keys use a stable quota bucket."""
    secret = "test-jwt-signing-secret-at-least-32-bytes"
    monkeypatch.setattr(settings, "jwt_secret", secret)
    monkeypatch.setattr(settings, "jwt_audience", None)
    monkeypatch.setattr(settings, "jwt_issuer", None)
    monkeypatch.setattr(settings, "jwt_tenant_claim", "tenant")
    monkeypatch.setattr(settings, "analytics_api_key", "sample-api-key")

    def bearer(tenant: str | None) -> dict[str, str]:
        claims = {"sub": "user-1"}
        if tenant is not None:
            claims["tenant"] = tenant
        token = jwt.encode(claims, secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}", "X-Tenant-Id": "forged"}

    for headers in (
        bearer("city-porto"),
        bearer(None),
        {"X-API-Key": "sample-api-key", "X-Tenant-Id": "forged"},
        {"X-Tenant-Id": "forged"},
        {"Authorization": "Bearer invalid", "X-Tenant-Id": "forged"},
    ):
        result = await client.get("/v1/health", headers=headers)
        assert result.status_code == 200

    assert list(api_main._TENANT_LIMITS) == ["city-porto", "authenticated", "public"]

    # The legacy API key is only an authentication method when JWT is disabled.
    monkeypatch.setattr(settings, "jwt_secret", None)
    result = await client.get(
        "/v1/health", headers={"X-API-Key": "sample-api-key", "X-Tenant-Id": "forged"}
    )
    assert result.status_code == 200
    assert list(api_main._TENANT_LIMITS)[-1] == "analytics-key"


@pytest.mark.asyncio
async def test_bucket_tables_evict_the_least_recently_used_entries(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bound both caches even when new IP addresses and tenants keep arriving."""
    monkeypatch.setattr(settings, "rate_limit_bucket_capacity", 2)
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)

    for address in ("10.0.0.1", "10.0.0.2", "10.0.0.1", "10.0.0.3"):
        transport = ASGITransport(app=app, client=(address, 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            assert (await http.get("/v1/health")).status_code == 200

    assert list(api_main._RATE_LIMITS) == ["10.0.0.1", "10.0.0.3"]
    api_main._TENANT_LIMITS.clear()

    secret = "test-jwt-signing-secret-at-least-32-bytes"
    monkeypatch.setattr(settings, "jwt_secret", secret)
    monkeypatch.setattr(settings, "jwt_audience", None)
    monkeypatch.setattr(settings, "jwt_issuer", None)
    monkeypatch.setattr(settings, "jwt_tenant_claim", "tenant")

    for tenant in ("tenant-1", "tenant-2", "tenant-1", "tenant-3"):
        token = jwt.encode({"sub": "tester", "tenant": tenant}, secret, algorithm="HS256")
        result = await client.get("/v1/health", headers={"Authorization": f"Bearer {token}"})
        assert result.status_code == 200

    assert list(api_main._TENANT_LIMITS) == ["tenant-1", "tenant-3"]
    assert len(api_main._RATE_LIMITS) <= 2


@pytest.mark.asyncio
async def test_http_metrics_group_ids_and_unmatched_paths(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dynamic IDs and arbitrary unknown paths must not create metric labels."""
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    monkeypatch.setattr(settings, "app_env", "dev")

    async def missing_note(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(notes_router, "get_note", missing_note)
    metric_names = (
        "REQUEST_COUNT",
        "REQUEST_LATENCY",
        "HTTP_ERRORS",
        "TENANT_REQUEST_COUNT",
        "TENANT_REQUEST_LATENCY",
        "TENANT_HTTP_ERRORS",
    )
    metrics = {name: Mock() for name in metric_names}
    for name, collector in metrics.items():
        monkeypatch.setattr(api_main, name, collector)

    for path in ("/v1/notes/note-a", "/v1/notes/note-b", "/unknown/a", "/unknown/b"):
        result = await client.get(path, headers={"X-Tenant-Id": path})
        assert result.status_code == 404

    paths = [call.kwargs["path"] for call in metrics["REQUEST_COUNT"].labels.call_args_list]
    assert paths == ["/v1/notes/{note_id}"] * 2 + ["<unmatched>"] * 2
    for collector in metrics.values():
        for metric_call in collector.labels.call_args_list:
            assert metric_call.kwargs["path"] in {"/v1/notes/{note_id}", "<unmatched>"}
            if "tenant" in metric_call.kwargs:
                assert metric_call.kwargs["tenant"] == "public"


def test_bucket_capacity_must_be_positive() -> None:
    """Reject a configuration that would make cache eviction impossible."""
    with pytest.raises(ValidationError):
        Settings(rate_limit_bucket_capacity=0)
