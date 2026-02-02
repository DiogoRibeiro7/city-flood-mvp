from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"

    database_url: str
    ingest_token: str = "dev-ingest-token"
    export_dir: str = "data/exports"
    analytics_api_key: str | None = None
    rate_limit_rps: float = 5.0
    rate_limit_burst: int = 20
    request_max_bytes: int = 1_000_000
    request_timeout_s: float = 10.0


settings = Settings()
