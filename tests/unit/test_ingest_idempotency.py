from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from floodmvp.api.main import app
from floodmvp.api.routers.ingest import (
    _authorize,
    _replay_idempotent_response,
    _request_digest,
    _validate_idempotency_key,
)
from floodmvp.common.errors import AppError
from floodmvp.config.settings import Settings, settings
from floodmvp.models.domain import IngestEventIn, IngestEventResult, IngestRequest, IngestResponse
from floodmvp.storage.db import get_session

NOW = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)


def _request(value: float = 0.7, device_id: str = "asset_1") -> IngestRequest:
    """Build a validated sample request whose event value is easy to vary."""
    return IngestRequest(
        device_id=device_id,
        sent_at=NOW,
        events=[IngestEventIn(ts=NOW, type="fill_ratio", value=value)],
    )


def _stored_response(payload: IngestRequest) -> dict[str, object]:
    response = IngestResponse(
        device_id=payload.device_id,
        received=1,
        accepted=1,
        rejected=0,
        results=[IngestEventResult(ts=payload.events[0].ts, type="fill_ratio", status="accepted")],
    )
    return {**response.model_dump(mode="json"), "_request_digest": _request_digest(payload)}


def test_idempotent_retry_replays_original_response() -> None:
    payload = _request()

    response = _replay_idempotent_response(
        payload.device_id, _stored_response(payload), _request(), _request_digest(payload)
    )

    assert response.accepted == 1
    assert response.device_id == "asset_1"
    assert "_request_digest" not in response.model_dump()


@pytest.mark.parametrize(
    "reused_payload",
    [
        _request(value=0.9),
        _request(device_id="different_asset"),
    ],
)
def test_idempotency_key_cannot_be_reused_for_another_request(
    reused_payload: IngestRequest,
) -> None:
    original = _request()

    with pytest.raises(AppError) as exc_info:
        _replay_idempotent_response(
            original.device_id,
            _stored_response(original),
            reused_payload,
            _request_digest(reused_payload),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


def test_legacy_response_still_supports_retry_for_same_device() -> None:
    payload = _request()
    prior_response = _stored_response(payload)
    del prior_response["_request_digest"]

    assert (
        _replay_idempotent_response(
            payload.device_id, prior_response, payload, _request_digest(payload)
        ).accepted
        == 1
    )


@pytest.mark.parametrize("key", ["  ", "x" * 129])
def test_invalid_idempotency_key_is_rejected(key: str) -> None:
    with pytest.raises(AppError) as exc_info:
        _validate_idempotency_key(key)

    assert exc_info.value.status_code == 400


def test_ingestion_fails_closed_without_configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ingest_token", "")

    with pytest.raises(AppError) as exc_info:
        _authorize("Bearer ")

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "AUTH_NOT_CONFIGURED"


@pytest.mark.parametrize("environment", ["prod", "production", "staging"])
@pytest.mark.parametrize("token", ["", "   ", "dev-ingest-token", " dev-ingest-token "])
def test_deployment_rejects_missing_or_demo_ingest_token(environment: str, token: str) -> None:
    """A known development token must never authorize public ingestion."""
    with pytest.raises(ValidationError, match="INGEST_TOKEN"):
        Settings(app_env=environment, ingest_token=token)


def test_local_demo_accepts_development_ingest_token() -> None:
    """Keep the documented local Docker Compose and smoke-test workflow."""
    configured = Settings(app_env="dev", ingest_token="dev-ingest-token")
    assert configured.ingest_auth_configured


def test_deployment_accepts_explicit_ingest_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured production token authorizes ingestion, and other values do not."""
    token = "test-deployment-secret-token"
    configured = Settings(app_env="prod", ingest_token=token)
    assert configured.ingest_auth_configured

    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "ingest_token", token)
    _authorize(f"Bearer {token}")

    with pytest.raises(HTTPException) as exc_info:
        _authorize("Bearer dev-ingest-token")
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("token", ["", "dev-ingest-token", " dev-ingest-token "])
def test_runtime_ingest_auth_rejects_unsafe_deployment_configuration(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    """Fail closed even if the settings object is updated after startup."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ingest_token", token)

    with pytest.raises(AppError) as exc_info:
        _authorize("Bearer dev-ingest-token")
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "AUTH_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_deployment_api_rejects_published_ingest_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a correctly formatted request must not reach the database."""
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "ingest_token", "dev-ingest-token")

    async def fake_session():
        yield None

    app.dependency_overrides[get_session] = fake_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/telemetry/events:batch",
                headers={"Authorization": "Bearer dev-ingest-token"},
                json=_request().model_dump(mode="json"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


def test_invalid_bearer_token_is_unauthorized() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _authorize("Bearer definitely-wrong")

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_api_preserves_bearer_challenge_on_invalid_token() -> None:
    """The JSON error handler must not discard authentication challenge headers."""

    async def fake_session():
        yield None

    app.dependency_overrides[get_session] = fake_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/telemetry/events:batch",
                headers={"Authorization": "Bearer wrong"},
                json=_request().model_dump(mode="json"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
