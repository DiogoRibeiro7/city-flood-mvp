from __future__ import annotations

from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_ENVIRONMENTS = frozenset({"dev", "development", "local", "test"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"
    # Exact browser origins, separated by commas (scheme, host and optional port).
    cors_allowed_origins: str = ""

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/floodmvp"
    ingest_token: str = "dev-ingest-token"
    export_dir: str = "data/exports"
    analytics_api_key: str | None = None
    jwt_secret: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_roles_claim: str = "roles"
    jwt_tenant_claim: str = "tenant"
    rate_limit_rps: float = 5.0
    rate_limit_burst: int = 20
    rate_limit_bucket_capacity: int = Field(default=4096, ge=1)
    tenant_quota_rps: float = 8.0
    tenant_quota_burst: int = 40
    request_max_bytes: int = Field(default=1_000_000, ge=1)
    request_timeout_s: float = Field(default=10.0, gt=0)

    analytics_version: str = "v1"
    analytics_window_days: int = 1
    rain_event_threshold_mmph: float = 5.0
    rain_event_min_duration_minutes: int = 15
    overflow_fill_threshold: float = 1.0
    overflow_min_duration_minutes: int = 10
    risk_fill_watch: float = 1.15
    risk_fill_warning: float = 1.4

    telemetry_gap_granularity_minutes: int = 5
    telemetry_gap_window_days: int = 1

    @property
    def cors_origins(self) -> list[str]:
        """Allow all origins in local demos; require an allowlist elsewhere."""
        origins = [origin.strip() for origin in self.cors_allowed_origins.split(",")]
        configured = [origin for origin in origins if origin]
        if configured:
            return configured
        return ["*"] if self.app_env.strip().lower() in _LOCAL_ENVIRONMENTS else []

    @model_validator(mode="after")
    def validate_cors_origins(self) -> Self:
        """Reject unsafe wildcards and invalid exact origins at startup."""
        local = self.app_env.strip().lower() in _LOCAL_ENVIRONMENTS
        for origin in self.cors_origins:
            if origin == "*":
                if not local:
                    raise ValueError("Wildcard CORS origins are only allowed in local development")
                continue

            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in parsed.netloc
            ):
                raise ValueError(f"Invalid CORS origin: {origin!r}")
            # urlsplit does not validate the numeric port until it is accessed.
            try:
                _ = parsed.port
            except ValueError as exc:
                raise ValueError(f"Invalid CORS origin port: {origin!r}") from exc
        return self


settings = Settings()
