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
    api_main._TENANT_LIMITS.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


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
        ("GET", "/v1/analytics/calibration/overrides?city_id=city_porto_mvp", None),
        (
            "POST",
            "/v1/notes",
            {"city_id": "city_porto_mvp", "title": "Incident", "body": "Check drain"},
        ),
        ("GET", "/v1/notes?city_id=city_porto_mvp", None),
        ("GET", "/v1/notes/note_123", None),
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
    accepted = await client.get("/v1/jobs/queue", headers={"X-API-Key": "sample-strong-key"})

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


def sample_calibration_override() -> SimpleNamespace:
    """Build an operational override row with sensitive operator notes."""
    return SimpleNamespace(
        override_id="override_1",
        city_id="city_porto_mvp",
        season="month-01",
        thresholds={"risk_fill_watch": 1.2},
        notes="Internal storm review",
        created_at=dt.datetime(2026, 10, 28, tzinfo=dt.UTC),
    )


@pytest.mark.asyncio
async def test_production_calibration_reads_require_admin_role(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only administrators may inspect calibration overrides when JWT is enabled."""
    secret = "test-jwt-signing-secret-at-least-32-bytes"
    monkeypatch.setattr(settings, "jwt_secret", secret)
    monkeypatch.setattr(settings, "analytics_api_key", "fallback-key")
    monkeypatch.setattr(settings, "jwt_audience", None)
    monkeypatch.setattr(settings, "jwt_issuer", None)
    reads = 0

    async def fake_list_overrides(*args: Any, **kwargs: Any) -> list[SimpleNamespace]:
        nonlocal reads
        reads += 1
        return [sample_calibration_override()]

    monkeypatch.setattr(analytics, "list_threshold_overrides", fake_list_overrides)

    def bearer(role: str) -> dict[str, str]:
        token = jwt.encode({"sub": "tester", "roles": [role]}, secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    path = "/v1/analytics/calibration/overrides?city_id=city_porto_mvp"
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={"X-API-Key": "fallback-key"})).status_code == 401
    for role in ("viewer", "analyst"):
        assert (await client.get(path, headers=bearer(role))).status_code == 403
    assert reads == 0  # Do not query sensitive records before authorization.

    allowed = await client.get(path, headers=bearer("admin"))
    assert allowed.status_code == 200
    assert allowed.json()[0]["notes"] == "Internal storm review"
    assert allowed.headers["cache-control"] == "private, no-store"
    assert reads == 1


@pytest.mark.asyncio
async def test_calibration_reads_accept_legacy_api_key_when_jwt_is_disabled(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Support existing trusted server-to-server callers during JWT migration."""
    monkeypatch.setattr(settings, "analytics_api_key", "sample-strong-key")

    async def fake_list_overrides(*args: Any, **kwargs: Any) -> list[SimpleNamespace]:
        return [sample_calibration_override()]

    monkeypatch.setattr(analytics, "list_threshold_overrides", fake_list_overrides)
    path = "/v1/analytics/calibration/overrides?city_id=city_porto_mvp"
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={"X-API-Key": "incorrect"})).status_code == 403

    allowed = await client.get(path, headers={"X-API-Key": "sample-strong-key"})
    assert allowed.status_code == 200
    assert allowed.json()[0]["override_id"] == "override_1"
    assert allowed.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_local_demo_keeps_calibration_reads_available(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local demonstration remains usable without a JWT or API key."""
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)

    async def fake_list_overrides(*args: Any, **kwargs: Any) -> list[SimpleNamespace]:
        return [sample_calibration_override()]

    monkeypatch.setattr(analytics, "list_threshold_overrides", fake_list_overrides)

    response = await client.get("/v1/analytics/calibration/overrides?city_id=city_porto_mvp")
    assert response.status_code == 200
    assert response.json()[0]["season"] == "month-01"
    assert response.headers["cache-control"] == "private, no-store"


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


def sample_note() -> SimpleNamespace:
    """Provide a repository row with the fields exposed by NoteOut."""
    now = dt.datetime(2026, 10, 28, tzinfo=dt.UTC)
    return SimpleNamespace(
        note_id="note_123",
        city_id="city_porto_mvp",
        asset_id=None,
        event_id=None,
        title="Inspection",
        body="Check inlet",
        author="Ops",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_local_demo_allows_anonymous_note_reads(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)

    async def fake_list_notes(*args: Any, **kwargs: Any) -> list[SimpleNamespace]:
        return [sample_note()]

    async def fake_get_note(*args: Any, **kwargs: Any) -> SimpleNamespace:
        return sample_note()

    monkeypatch.setattr(notes_router, "list_notes", fake_list_notes)
    monkeypatch.setattr(notes_router, "get_note", fake_get_note)

    listed = await client.get("/v1/notes?city_id=city_porto_mvp")
    detail = await client.get("/v1/notes/note_123")

    assert listed.status_code == detail.status_code == 200
    assert listed.json()[0]["note_id"] == detail.json()["note_id"] == "note_123"
    assert listed.headers["cache-control"] == "private, no-store"
    assert detail.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_production_note_reads_require_jwt_and_viewer_role(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "test-jwt-signing-secret-at-least-32-bytes"
    monkeypatch.setattr(settings, "jwt_secret", secret)
    monkeypatch.setattr(settings, "analytics_api_key", "fallback-key")
    monkeypatch.setattr(settings, "jwt_audience", None)
    monkeypatch.setattr(settings, "jwt_issuer", None)
    calls = 0

    async def fake_list_notes(*args: Any, **kwargs: Any) -> list[SimpleNamespace]:
        nonlocal calls
        calls += 1
        return [sample_note()]

    async def fake_get_note(*args: Any, **kwargs: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return sample_note()

    monkeypatch.setattr(notes_router, "list_notes", fake_list_notes)
    monkeypatch.setattr(notes_router, "get_note", fake_get_note)

    def bearer(role: str) -> dict[str, str]:
        token = jwt.encode({"sub": "tester", "roles": [role]}, secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    list_path = "/v1/notes?city_id=city_porto_mvp"
    assert (await client.get(list_path)).status_code == 401
    assert (await client.get(list_path, headers={"X-API-Key": "fallback-key"})).status_code == 401
    assert (await client.get(list_path, headers=bearer("auditor"))).status_code == 403
    assert (await client.get("/v1/notes/note_123")).status_code == 401
    assert calls == 0  # Authorization must precede repository access.

    for role in ("viewer", "analyst", "admin"):
        listed = await client.get(list_path, headers=bearer(role))
        assert listed.status_code == 200
        assert listed.json()[0]["author"] == "Ops"
        assert listed.headers["cache-control"] == "private, no-store"

    detail = await client.get("/v1/notes/note_123", headers=bearer("viewer"))
    assert detail.status_code == 200
    assert detail.json()["body"] == "Check inlet"
    assert detail.headers["cache-control"] == "private, no-store"
    assert calls == 4


@pytest.mark.asyncio
async def test_production_note_reads_allow_legacy_api_key(
    client: AsyncClient, production_without_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "analytics_api_key", "sample-strong-key")

    async def fake_list_notes(*args: Any, **kwargs: Any) -> list[SimpleNamespace]:
        return [sample_note()]

    async def fake_get_note(*args: Any, **kwargs: Any) -> SimpleNamespace | None:
        return sample_note() if args[1] == "note_123" else None

    monkeypatch.setattr(notes_router, "list_notes", fake_list_notes)
    monkeypatch.setattr(notes_router, "get_note", fake_get_note)

    path = "/v1/notes?city_id=city_porto_mvp"
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={"X-API-Key": "invalid"})).status_code == 403

    headers = {"X-API-Key": "sample-strong-key"}
    listed = await client.get(path, headers=headers)
    detail = await client.get("/v1/notes/note_123", headers=headers)
    missing = await client.get("/v1/notes/missing", headers=headers)

    assert listed.status_code == detail.status_code == 200
    assert listed.json()[0]["title"] == detail.json()["title"] == "Inspection"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOTE_NOT_FOUND"
