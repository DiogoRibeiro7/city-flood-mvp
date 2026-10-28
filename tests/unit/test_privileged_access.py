"""Security regressions for privileged endpoints and local demo exceptions."""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.api.routers import analytics, jobs
from floodmvp.api.routers import notes as notes_router
from floodmvp.config.settings import settings
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Exercise real FastAPI request parsing while avoiding database writes."""

    async def fake_session() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_session] = fake_session
    api_main._RATE_LIMITS.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        api_main._RATE_LIMITS.clear()


@pytest.fixture()
def production_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the configuration that previously exposed administrative APIs."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/v1/jobs/queue", None),
        ("POST", "/v1/jobs/queue/job_123/cancel", None),
        (
            "POST",
            "/v1/analytics/jobs",
            {
                "type": "export_csv",
                "query": {
                    "asset_ids": ["pipe_1"],
                    "metric": "fill_ratio",
                    "from": "2026-01-01T00:00:00Z",
                    "to": "2026-01-02T00:00:00Z",
                },
            },
        ),
        (
            "POST",
            "/v1/analytics/calibration/overrides",
            {"city_id": "city_porto_mvp", "thresholds": {}},
        ),
        (
            "POST",
            "/v1/notes",
            {"city_id": "city_porto_mvp", "title": "Incident", "body": "Check drain"},
        ),
        ("DELETE", "/v1/notes/note_123", None),
    ],
)
async def test_production_privileged_endpoints_fail_closed_without_credentials(
    client: AsyncClient,
    production_without_credentials: None,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    response = await client.request(method, path, json=body)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_local_demo_remains_available_without_credentials(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)

    async def fake_list_jobs(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(jobs, "list_jobs", fake_list_jobs)
    response = await client.get("/v1/jobs/queue")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_key_fallback_enforces_authentication(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "analytics_api_key", "sample-strong-key")

    async def fake_list_jobs(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(jobs, "list_jobs", fake_list_jobs)

    missing = await client.get("/v1/jobs/queue")
    invalid = await client.get("/v1/jobs/queue", headers={"X-API-Key": "wrong"})
    accepted = await client.get(
        "/v1/jobs/queue", headers={"X-API-Key": "sample-strong-key"}
    )

    assert missing.status_code == 401
    assert invalid.status_code == 403
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_calibration_override_accepts_configured_api_key(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The calibration POST must read X-API-Key, not only Authorization."""
    monkeypatch.setattr(settings, "analytics_api_key", "sample-strong-key")

    class SessionStub:
        async def commit(self) -> None:
            return None

    async def fake_session() -> AsyncGenerator[SessionStub, None]:
        yield SessionStub()

    async def fake_create_override(session: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            override_id="override_1",
            city_id=kwargs["city_id"],
            season=kwargs["season"],
            thresholds=kwargs["thresholds"],
            notes=kwargs["notes"],
            created_at=dt.datetime(2026, 10, 28, tzinfo=dt.UTC),
        )

    app.dependency_overrides[get_session] = fake_session
    monkeypatch.setattr(analytics, "create_threshold_override", fake_create_override)

    response = await client.post(
        "/v1/analytics/calibration/overrides",
        headers={"X-API-Key": "sample-strong-key"},
        json={"city_id": "city_porto_mvp", "thresholds": {"risk_fill_watch": 1.2}},
    )

    assert response.status_code == 200
    assert response.json()["thresholds"]["risk_fill_watch"] == 1.2


@pytest.mark.asyncio
async def test_jwt_takes_precedence_and_restricts_roles(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "test-jwt-signing-secret-at-least-32-bytes"
    monkeypatch.setattr(settings, "jwt_secret", secret)
    monkeypatch.setattr(settings, "analytics_api_key", "fallback-key")
    monkeypatch.setattr(settings, "jwt_audience", None)
    monkeypatch.setattr(settings, "jwt_issuer", None)

    async def fake_list_jobs(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(jobs, "list_jobs", fake_list_jobs)

    def bearer(role: str) -> dict[str, str]:
        token = jwt.encode({"sub": "tester", "roles": [role]}, secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    viewer = await client.get("/v1/jobs/queue", headers=bearer("viewer"))
    analyst = await client.delete("/v1/notes/note_123", headers=bearer("analyst"))
    api_key_only = await client.get("/v1/jobs/queue", headers={"X-API-Key": "fallback-key"})
    admin = await client.get("/v1/jobs/queue", headers=bearer("admin"))

    assert viewer.status_code == 403
    assert analyst.status_code == 403
    assert api_key_only.status_code == 401
    assert admin.status_code == 200


@pytest.mark.asyncio
async def test_authorized_note_writes_enforce_analyst_and_admin_roles(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "test-jwt-signing-secret-at-least-32-bytes"
    monkeypatch.setattr(settings, "jwt_secret", secret)
    monkeypatch.setattr(settings, "jwt_audience", None)
    monkeypatch.setattr(settings, "jwt_issuer", None)

    class SessionStub:
        async def commit(self) -> None:
            return None

    async def fake_session() -> AsyncGenerator[SessionStub, None]:
        yield SessionStub()

    async def fake_create_note(session: Any, **kwargs: Any) -> SimpleNamespace:
        now = dt.datetime(2026, 10, 28, tzinfo=dt.UTC)
        return SimpleNamespace(note_id="note_123", created_at=now, updated_at=now, **kwargs)

    async def fake_delete_note(session: Any, note_id: str) -> bool:
        return note_id == "note_123"

    app.dependency_overrides[get_session] = fake_session
    monkeypatch.setattr(notes_router, "create_note", fake_create_note)
    monkeypatch.setattr(notes_router, "delete_note", fake_delete_note)

    def bearer(role: str) -> dict[str, str]:
        token = jwt.encode({"sub": "tester", "roles": [role]}, secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/v1/notes",
        headers=bearer("analyst"),
        json={"city_id": "city_porto_mvp", "title": "Inspection", "body": "Check inlet"},
    )
    deleted = await client.delete("/v1/notes/note_123", headers=bearer("admin"))

    assert created.status_code == 200
    assert created.json()["note_id"] == "note_123"
    assert deleted.status_code == 200
