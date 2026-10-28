from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from floodmvp.api.main import app
from floodmvp.api.routers.ingest import (
    _authorize,
    _replay_idempotent_response,
    _request_digest,
    _validate_idempotency_key,
)
from floodmvp.common.errors import AppError
from floodmvp.config.settings import settings
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
        results=[
            IngestEventResult(ts=payload.events[0].ts, type="fill_ratio", status="accepted")
        ],
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

    assert _replay_idempotent_response(
        payload.device_id, prior_response, payload, _request_digest(payload)
    ).accepted == 1


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
