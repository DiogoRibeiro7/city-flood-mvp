"""Record every HTTP response, including middleware-level rejections."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from unittest.mock import Mock

import pytest
from fastapi import Request, Response
from httpx import ASGITransport, AsyncClient
from starlette.types import Message

from floodmvp.api import main as api_main
from floodmvp.api.main import app
from floodmvp.config.settings import settings

METRIC_NAMES = (
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "HTTP_ERRORS",
    "TENANT_REQUEST_COUNT",
    "TENANT_REQUEST_LATENCY",
    "TENANT_HTTP_ERRORS",
)


@pytest.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Use the real middleware while isolating token-bucket state."""
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


@pytest.fixture()
def observed(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Mock], Mock]:
    """Capture metric-label updates and structured request logs without global state."""
    collectors = {name: Mock() for name in METRIC_NAMES}
    for name, collector in collectors.items():
        monkeypatch.setattr(api_main, name, collector)
    logger = Mock()
    monkeypatch.setattr(api_main, "log_json", logger)
    return collectors, logger


def recorded_statuses(collector: Mock) -> list[str]:
    """List status label values from the request counter in call order."""
    return [call.kwargs["status"] for call in collector.labels.call_args_list]


def assert_rejection_recorded(
    collectors: dict[str, Mock], logger: Mock, *, status: int, request_id: str
) -> None:
    """Ensure an early response contributes to all relevant metrics and logs."""
    assert str(status) == recorded_statuses(collectors["REQUEST_COUNT"])[-1]
    assert str(status) == recorded_statuses(collectors["TENANT_REQUEST_COUNT"])[-1]
    for name in ("REQUEST_LATENCY", "TENANT_REQUEST_LATENCY"):
        assert collectors[name].labels.call_count > 0
    status_class = "4xx" if status < 500 else "5xx"
    assert collectors["HTTP_ERRORS"].labels.call_args.kwargs["status_class"] == status_class
    assert collectors["TENANT_HTTP_ERRORS"].labels.call_args.kwargs["status_class"] == status_class
    assert logger.call_args.kwargs["status"] == status
    assert logger.call_args.kwargs["request_id"] == request_id


@pytest.mark.asyncio
async def test_per_ip_rejection_is_counted_and_logged(
    client: AsyncClient,
    observed: tuple[dict[str, Mock], Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collectors, logger = observed
    monkeypatch.setattr(settings, "rate_limit_rps", 0.0)
    monkeypatch.setattr(settings, "rate_limit_burst", 1)
    monkeypatch.setattr(settings, "tenant_quota_rps", 100.0)
    monkeypatch.setattr(settings, "tenant_quota_burst", 100)

    allowed = await client.get("/v1/health")
    rejected = await client.get("/v1/health", headers={"X-Request-Id": "ip-limited"})

    assert allowed.status_code == 200
    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "RATE_LIMITED"
    assert rejected.headers["x-request-id"] == "ip-limited"
    assert recorded_statuses(collectors["REQUEST_COUNT"]) == ["200", "429"]
    assert collectors["REQUEST_COUNT"].labels.call_args.kwargs["path"] == "<unmatched>"
    assert_rejection_recorded(collectors, logger, status=429, request_id="ip-limited")


@pytest.mark.asyncio
async def test_tenant_rejection_is_counted_and_logged(
    client: AsyncClient,
    observed: tuple[dict[str, Mock], Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collectors, logger = observed
    monkeypatch.setattr(settings, "rate_limit_rps", 100.0)
    monkeypatch.setattr(settings, "rate_limit_burst", 100)
    monkeypatch.setattr(settings, "tenant_quota_rps", 0.0001)
    monkeypatch.setattr(settings, "tenant_quota_burst", 1)

    await client.get("/v1/health")
    rejected = await client.get("/v1/health", headers={"X-Request-Id": "tenant-limited"})

    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "TENANT_RATE_LIMITED"
    assert collectors["TENANT_REQUEST_COUNT"].labels.call_args.kwargs["tenant"] == "public"
    assert_rejection_recorded(collectors, logger, status=429, request_id="tenant-limited")


@pytest.mark.asyncio
@pytest.mark.parametrize("include_content_length", [True, False])
async def test_oversize_rejections_are_counted_and_logged(
    client: AsyncClient,
    observed: tuple[dict[str, Mock], Mock],
    monkeypatch: pytest.MonkeyPatch,
    include_content_length: bool,
) -> None:
    collectors, logger = observed
    monkeypatch.setattr(settings, "rate_limit_rps", 100.0)
    monkeypatch.setattr(settings, "rate_limit_burst", 100)
    monkeypatch.setattr(settings, "tenant_quota_rps", 100.0)
    monkeypatch.setattr(settings, "tenant_quota_burst", 100)
    monkeypatch.setattr(settings, "request_max_bytes", 3)

    async def streamed_body() -> AsyncIterator[bytes]:
        yield b"1234"

    content: bytes | AsyncIterator[bytes] = b"1234" if include_content_length else streamed_body()
    result = await client.post(
        "/v1/does-not-exist", content=content, headers={"X-Request-Id": "body-limited"}
    )

    assert result.status_code == 413
    assert result.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert result.headers["x-request-id"] == "body-limited"
    assert_rejection_recorded(collectors, logger, status=413, request_id="body-limited")


@pytest.mark.asyncio
async def test_timeout_is_counted_and_logged(
    observed: tuple[dict[str, Mock], Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive the middleware directly with a downstream timeout."""
    collectors, logger = observed
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()
    monkeypatch.setattr(settings, "rate_limit_rps", 100.0)
    monkeypatch.setattr(settings, "rate_limit_burst", 100)
    monkeypatch.setattr(settings, "tenant_quota_rps", 100.0)
    monkeypatch.setattr(settings, "tenant_quota_burst", 100)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/health",
        "raw_path": b"/v1/health",
        "query_string": b"",
        "scheme": "http",
        "headers": [(b"x-request-id", b"timed-out")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def timed_out(_request: Request) -> Response:
        raise TimeoutError("Simulated downstream timeout")

    response = await api_main.add_request_id(Request(scope, receive), timed_out)

    assert response.status_code == 504
    assert json.loads(response.body)["error"]["code"] == "REQUEST_TIMEOUT"
    assert response.headers["x-request-id"] == "timed-out"
    assert_rejection_recorded(collectors, logger, status=504, request_id="timed-out")
