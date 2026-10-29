"""Enforce request sizes against streamed bytes, not untrusted headers."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.types import Message

from floodmvp.api import main as api_main
from floodmvp.config.settings import Settings, settings


@pytest.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Run the real middleware without leaking quota state between tests."""
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=api_main.app), base_url="http://test"
        ) as http:
            yield http
    finally:
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("declared_length", [None, "1", "invalid"])
async def test_oversize_stream_is_rejected_regardless_of_content_length(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    declared_length: str | None,
) -> None:
    """An absent, malformed or understated header must not bypass 413."""
    monkeypatch.setattr(settings, "request_max_bytes", 5)

    async def body() -> AsyncIterator[bytes]:
        yield b"123"
        yield b"456"

    headers = {"X-Request-Id": "stream-oversize"}
    if declared_length is not None:
        headers["Content-Length"] = declared_length

    result = await client.post("/v1/does-not-exist", content=body(), headers=headers)

    assert result.status_code == 413
    assert result.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert result.headers["x-request-id"] == "stream-oversize"


@pytest.mark.asyncio
async def test_accepted_body_reaches_fastapi_json_validation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading body chunks in middleware must preserve the actual JSON payload."""
    monkeypatch.setattr(settings, "request_max_bytes", 1024)
    monkeypatch.setattr(settings, "ingest_token", "test-ingest-token")

    payload = {"device_id": "sensor-1", "sent_at": "2026-10-29T00:00:00Z", "events": []}
    result = await client.post(
        "/v1/telemetry/events:batch",
        json=payload,
        headers={"Content-Length": "1"},
    )

    # Valid JSON reaches the handler, which rejects the missing ingest credential
    # before doing any database work. An empty/truncated body fails validation.
    assert result.status_code == 401
    assert result.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_streaming_guard_stops_before_reading_additional_chunks() -> None:
    """Stop as soon as the cumulative limit is crossed to bound buffering."""
    messages: list[Message] = [
        {"type": "http.request", "body": b"123", "more_body": True},
        {"type": "http.request", "body": b"456", "more_body": True},
        {"type": "http.request", "body": b"789", "more_body": False},
    ]

    async def receive() -> Message:
        return messages.pop(0)

    request = Request({"type": "http", "method": "POST", "headers": []}, receive)
    assert await api_main._body_exceeds_limit(request, max_bytes=5)
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_declared_oversize_is_rejected_without_consuming_body() -> None:
    """A known oversize declaration can be rejected without waiting for data."""

    async def receive() -> Message:
        raise AssertionError("Body must not be consumed")

    request = Request(
        {"type": "http", "method": "POST", "headers": [(b"content-length", b"6")]},
        receive,
    )
    assert await api_main._body_exceeds_limit(request, max_bytes=5)


def test_body_limit_must_be_positive() -> None:
    """Invalid size limits must fail during application configuration."""
    with pytest.raises(ValidationError):
        Settings(request_max_bytes=0)
