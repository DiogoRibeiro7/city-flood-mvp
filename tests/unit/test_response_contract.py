"""Compare real HTTP error envelopes with both published schemas."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient, Response

from floodmvp.api import main as api_main
from floodmvp.api.routers import jobs, notes
from floodmvp.common.errors import ErrorResponse
from floodmvp.config.settings import settings
from floodmvp.storage.db import get_session
from scripts.export_openapi import build_public_spec


@pytest.fixture()
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    for option in ("rate_limit_rps", "rate_limit_burst", "tenant_quota_rps", "tenant_quota_burst"):
        monkeypatch.setattr(settings, option, 10000)
    api_main._RATE_LIMITS.clear()
    api_main._TENANT_LIMITS.clear()

    async def session() -> AsyncIterator[None]:
        yield None

    api_main.app.dependency_overrides[get_session] = session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=api_main.app), base_url="http://test"
        ) as http:
            yield http
    finally:
        api_main.app.dependency_overrides.pop(get_session, None)
        api_main._RATE_LIMITS.clear()
        api_main._TENANT_LIMITS.clear()


def assert_documented(response: Response, method: str, path: str, expected: str) -> None:
    assert response.headers["content-type"].startswith("application/json")
    envelope = ErrorResponse.model_validate(response.json())
    assert envelope.error.code == expected
    assert envelope.error.request_id == response.headers["x-request-id"]
    for spec in (api_main.app.openapi(), build_public_spec()):
        declared = spec["paths"][path][method]["responses"][str(response.status_code)]
        if "$ref" in declared:
            declared = spec["components"]["responses"][declared["$ref"].rsplit("/", 1)[-1]]
        media = declared["content"]["application/json"]
        assert media["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}
        examples = (
            [media["example"]]
            if "example" in media
            else [item["value"] for item in media["examples"].values()]
        )
        assert expected in {example["error"]["code"] for example in examples}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["body", "client_quota", "tenant_quota", "timeout"])
async def test_middleware_http_errors_match_contract(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    content = b""
    if failure == "body":
        monkeypatch.setattr(settings, "request_max_bytes", 5)
        content = b"123456"
        status, code = 413, "REQUEST_TOO_LARGE"
    elif failure == "timeout":
        monkeypatch.setattr(api_main, "_body_exceeds_limit", AsyncMock(side_effect=TimeoutError))
        status, code = 504, "REQUEST_TIMEOUT"
    else:
        prefix = "rate_limit" if failure == "client_quota" else "tenant_quota"
        monkeypatch.setattr(settings, f"{prefix}_rps", 0.00000001)
        monkeypatch.setattr(settings, f"{prefix}_burst", 1)
        assert (await client.get("/v1/health")).status_code == 200
        status = 429
        code = "RATE_LIMITED" if failure == "client_quota" else "TENANT_RATE_LIMITED"
    response = await client.request("GET", "/v1/health", content=content)
    assert response.status_code == status
    assert_documented(response, "get", "/v1/health", code)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "repository", "status", "code"),
    [
        ("get", "/v1/notes/{note_id}", "get_note", 404, "NOTE_NOT_FOUND"),
        ("delete", "/v1/notes/{note_id}", "delete_note", 404, "NOTE_NOT_FOUND"),
        ("get", "/v1/jobs/queue/{job_id}", "get_job", 404, "JOB_NOT_FOUND"),
        ("post", "/v1/jobs/queue/{job_id}/retry", "retry_job", 400, "JOB_NOT_RETRYABLE"),
        ("post", "/v1/jobs/queue/{job_id}/cancel", "cancel_job", 400, "JOB_NOT_CANCELLABLE"),
    ],
)
async def test_missing_note_and_queue_errors_match_contract(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    repository: str,
    status: int,
    code: str,
) -> None:
    module = notes if "/notes/" in path else jobs
    monkeypatch.setattr(module, repository, AsyncMock(return_value=None))
    response = await client.request(method, path.format(note_id="missing", job_id="missing"))
    assert response.status_code == status
    assert_documented(response, method, path, code)


@pytest.mark.asyncio
async def test_unconfigured_ingest_error_matches_contract(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ingest_token", "")
    response = await client.post(
        "/v1/telemetry/events:batch",
        json={"device_id": "synthetic", "sent_at": "2026-01-01T00:00:00Z", "events": []},
    )
    assert response.status_code == 503
    assert_documented(response, "post", "/v1/telemetry/events:batch", "AUTH_NOT_CONFIGURED")
