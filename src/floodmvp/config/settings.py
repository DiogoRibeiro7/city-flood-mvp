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


settings = Settings()
