"""CORS configuration must preserve the local demo without exposing production."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from floodmvp.api.main import app
from floodmvp.config.settings import Settings, settings


def test_local_demo_allows_all_origins_by_default() -> None:
    """The existing Vite demo remains accessible without extra configuration."""
    assert Settings(app_env="dev", cors_allowed_origins="").cors_origins == ["*"]
    assert Settings(app_env="test", cors_allowed_origins="  ").cors_origins == ["*"]


@pytest.mark.parametrize("environment", ["prod", "production", "staging"])
def test_nonlocal_environments_deny_cross_origin_by_default(environment: str) -> None:
    """Missing configuration must not silently allow arbitrary websites."""
    assert Settings(app_env=environment, cors_allowed_origins="").cors_origins == []


def test_exact_origins_are_normalized_from_environment_string() -> None:
    """Accept a comma-separated origin list without trailing whitespace."""
    configured = Settings(
        app_env="prod",
        cors_allowed_origins=" https://dashboard.example.com, http://localhost:5173 , ",
    )
    assert configured.cors_origins == [
        "https://dashboard.example.com",
        "http://localhost:5173",
    ]


@pytest.mark.parametrize("environment", ["prod", "staging"])
def test_wildcard_origin_is_rejected_outside_development(environment: str) -> None:
    """Do not permit an explicit wildcard in a deployed environment."""
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(app_env=environment, cors_allowed_origins="https://trusted.example.com, *")


@pytest.mark.parametrize(
    "origin",
    [
        "trusted.example.com",
        "ftp://trusted.example.com",
        "https://trusted.example.com/path",
        "https://trusted.example.com/",
        "https://trusted.example.com?next=1",
        "https://*.example.com",
        "https://trusted.example.com:invalid",
    ],
)
def test_non_origin_urls_are_rejected(origin: str) -> None:
    """A browser origin contains only HTTP(S) scheme, host, and optional port."""
    with pytest.raises(ValidationError, match="Invalid CORS"):
        Settings(app_env="prod", cors_allowed_origins=origin)


def test_api_uses_validated_configured_origins() -> None:
    """The application's middleware receives the validated setting."""
    cors = [middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware]
    assert len(cors) == 1
    assert cors[0].kwargs["allow_origins"] == settings.cors_origins
    assert cors[0].kwargs["allow_credentials"] is False


@pytest.fixture()
async def production_client() -> AsyncGenerator[AsyncClient, None]:
    """Exercise Starlette preflight behavior using the production allowlist."""
    configured = Settings(app_env="prod", cors_allowed_origins="https://trusted.example.com")
    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/data")
    async def data() -> dict[str, str]:
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as http:
        yield http


@pytest.mark.asyncio
async def test_production_preflight_denies_unlisted_browser_origin(
    production_client: AsyncClient,
) -> None:
    """Only explicitly allowed origins may make cross-origin browser requests."""
    headers = {"Access-Control-Request-Method": "GET"}
    allowed = await production_client.options(
        "/data", headers={**headers, "Origin": "https://trusted.example.com"}
    )
    denied = await production_client.options(
        "/data", headers={**headers, "Origin": "https://untrusted.example.com"}
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://trusted.example.com"
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.asyncio
async def test_non_browser_requests_still_work(production_client: AsyncClient) -> None:
    """A CORS policy is not a general HTTP client authorization check."""
    result = await production_client.get("/data")

    assert result.status_code == 200
    assert result.json() == {"status": "ok"}
