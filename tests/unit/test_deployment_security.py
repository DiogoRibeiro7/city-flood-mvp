"""Exercise the dedicated-tenant boundary before any repository access."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from floodmvp.api import main as api_main
from floodmvp.api.routers import cities
from floodmvp.config.settings import settings
from floodmvp.storage.db import get_session

SECRET = "synthetic-deployment-test-signing-key-32-bytes"
PUBLIC_PATHS = {"/v1/health", "/v1/telemetry/events:batch"}
DATA_ROUTES = [
    (method, re.sub(r"\{[^}]+\}", "record-a", route.path))
    for route in api_main.app.routes
    if isinstance(route, APIRoute)
    and route.path.startswith("/v1/")
    and route.path not in PUBLIC_PATHS
    for method in sorted(route.methods)
]


def bearer(tenant: Any = "tenant-a", role: str = "viewer", **overrides: Any) -> dict[str, str]:
    claims = {
        "sub": "synthetic-user",
        "roles": [role],
        "tenant": tenant,
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        **overrides,
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, SECRET, algorithm="HS256")}


@pytest.fixture()
async def deployed(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    for name, value in {
        "app_env": "production",
        "deployment_tenant_id": "tenant-a",
        "jwt_secret": SECRET,
        "jwt_audience": None,
        "jwt_issuer": None,
        "jwt_tenant_claim": "tenant",
        "jwt_roles_claim": "roles",
        "analytics_api_key": "synthetic-legacy-key",
        "rate_limit_rps": 10000,
        "rate_limit_burst": 10000,
        "tenant_quota_rps": 10000,
        "tenant_quota_burst": 10000,
        "ingest_token": "synthetic-ingestion-token",
    }.items():
        monkeypatch.setattr(settings, name, value)

    async def forbidden_session() -> AsyncGenerator[None, None]:
        raise AssertionError("Unauthorized request reached a database dependency")
        yield None

    api_main.app.dependency_overrides[get_session] = forbidden_session
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=api_main.app), base_url="http://test"
        ) as client:
            yield client
    finally:
        api_main.app.dependency_overrides.clear()
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


@pytest.mark.parametrize(("method", "path"), DATA_ROUTES)
async def test_every_deployed_data_route_requires_auth_before_db(
    deployed: AsyncClient, method: str, path: str
) -> None:
    response = await deployed.request(method, path, headers={"X-Tenant-Id": "tenant-a"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(("method", "path"), DATA_ROUTES)
async def test_foreign_tenant_admin_cannot_read_or_mutate_deployment(
    deployed: AsyncClient, method: str, path: str
) -> None:
    headers = {
        **bearer("tenant-b", "admin"),
        "X-Tenant-Id": "tenant-a",
        "X-API-Key": "synthetic-legacy-key",
    }
    response = await deployed.request(method, path, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    "tenant", [None, "", "tenant-a ", 123, ["tenant-a"], {"tenant": "tenant-a"}]
)
async def test_malformed_or_nonmatching_tenant_cannot_select_a_database(
    deployed: AsyncClient, tenant: Any
) -> None:
    response = await deployed.get("/v1/cities", headers=bearer(tenant))
    assert response.status_code == 403


@pytest.mark.parametrize("missing", ["sub", "exp", "tenant"])
async def test_deployed_jwt_requires_identity_expiry_and_tenant(
    deployed: AsyncClient, missing: str
) -> None:
    claims = {
        "sub": "tester",
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        "tenant": "tenant-a",
        "roles": ["viewer"],
    }
    del claims[missing]
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    response = await deployed.get("/v1/cities", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == (403 if missing == "tenant" else 401)


@pytest.mark.parametrize(
    "kind", ["expired", "wrong_signature", "wrong_issuer", "wrong_audience", "no_role"]
)
async def test_invalid_identity_or_role_fails_closed(
    deployed: AsyncClient, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = bearer()
    if kind == "expired":
        headers = bearer(exp=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1))
    elif kind == "wrong_signature":
        monkeypatch.setattr(settings, "jwt_secret", "another-synthetic-signing-key-32-bytes")
    elif kind == "wrong_issuer":
        monkeypatch.setattr(settings, "jwt_issuer", "expected-issuer")
        headers = bearer(iss="other-issuer")
    elif kind == "wrong_audience":
        monkeypatch.setattr(settings, "jwt_audience", "expected-audience")
        headers = bearer(aud="other-audience")
    else:
        headers = bearer(role="unrecognized")
    response = await deployed.get("/v1/cities", headers=headers)
    assert response.status_code == (403 if kind == "no_role" else 401)


async def test_missing_deployment_binding_refuses_even_valid_admin(
    deployed: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "deployment_tenant_id", "")
    response = await deployed.get("/v1/cities", headers=bearer(role="admin"))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


async def test_valid_tenant_can_read_but_not_share_cached_data(
    deployed: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def session() -> AsyncGenerator[None, None]:
        yield None

    api_main.app.dependency_overrides[get_session] = session
    read = AsyncMock(return_value=[])
    monkeypatch.setattr(cities, "list_cities", read)
    response = await deployed.get("/v1/cities", headers={**bearer(), "X-Tenant-Id": "tenant-b"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    read.assert_awaited_once()
    # The same signing authority's token is denied at another dedicated deployment.
    monkeypatch.setattr(settings, "deployment_tenant_id", "tenant-b")
    assert (await deployed.get("/v1/cities", headers=bearer())).status_code == 403
    assert read.await_count == 1


async def test_legacy_key_is_deployment_scoped_and_jwt_takes_precedence(
    deployed: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        await deployed.get("/v1/cities", headers={"X-API-Key": "synthetic-legacy-key"})
    ).status_code == 401
    monkeypatch.setattr(settings, "jwt_secret", None)
    assert (await deployed.get("/v1/cities", headers={"X-API-Key": "wrong"})).status_code == 403
    # An arbitrary Latin-1 credential must not trigger compare_digest(str)'s TypeError.
    assert (await deployed.get("/v1/cities", headers=[(b"X-API-Key", b"\xff")])).status_code == 403


async def test_ingest_still_uses_its_separate_credential(deployed: AsyncClient) -> None:
    # Authorization in ingestion precedes its repository calls but follows its session dependency.
    async def session() -> AsyncGenerator[None, None]:
        yield None

    api_main.app.dependency_overrides[get_session] = session
    payload = {"device_id": "synthetic", "sent_at": "2026-01-01T00:00:00Z", "events": []}
    for headers in (bearer(role="admin"), [(b"Authorization", b"Bearer \xff")]):
        response = await deployed.post("/v1/telemetry/events:batch", headers=headers, json=payload)
        assert response.status_code == 401


@pytest.mark.parametrize("limiter", ["client", "tenant"])
def test_two_processes_each_receive_a_full_quota(limiter: str) -> None:
    """Measure the unsupported two-process case without a network or database."""
    script = """
import asyncio, json, os
from httpx import ASGITransport, AsyncClient
from floodmvp.api.main import app
async def probe():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = [await client.get("/v1/health") for _ in range(3)]
        print(json.dumps({"pid": os.getpid(), "statuses": [r.status_code for r in responses],
                          "error": responses[-1].json()["error"]["code"]}), flush=True)
asyncio.run(probe())
"""
    env = {
        **os.environ,
        "APP_ENV": "test",
        "JWT_SECRET": "",
        "ANALYTICS_API_KEY": "",
        "DATABASE_URL": "postgresql+asyncpg://postgres:unused@127.0.0.1:1/test_no_connection",
        "RATE_LIMIT_RPS": "0.00000001" if limiter == "client" else "10000",
        "RATE_LIMIT_BURST": "2" if limiter == "client" else "10000",
        "TENANT_QUOTA_RPS": "0.00000001" if limiter == "tenant" else "10000",
        "TENANT_QUOTA_BURST": "2" if limiter == "tenant" else "10000",
    }
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    observations = []
    try:
        for process in processes:
            out, err = process.communicate(timeout=30)
            assert process.returncode == 0, err
            observations.append(json.loads(out.strip().splitlines()[-1]))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    assert len({item["pid"] for item in observations}) == 2
    expected = "RATE_LIMITED" if limiter == "client" else "TENANT_RATE_LIMITED"
    assert all(
        item["statuses"] == [200, 200, 429] and item["error"] == expected for item in observations
    )
    print(json.dumps({"limiter": limiter, "processes": observations, "total_accepted": 4}))
