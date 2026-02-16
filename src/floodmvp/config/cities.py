from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class CityNetworkConfig:
    center_lon: float
    center_lat: float
    half_size_deg: float
    grid_n: int = 20
    jitter_ratio: float = 0.18
    outfall_count: int = 3
    seed: int = 7


@dataclass(frozen=True)
class CityTelemetryConfig:
    scenario: str = "heavy_rain_high_river"
    realism: str = "synthetic"  # synthetic | tier2_porto
    realism_profile: str | None = None
    years: int = 0
    days: int = 7
    pipe_limit: int = 150


@dataclass(frozen=True)
class CityAnalyticsConfig:
    rain_event_threshold_mmph: float | None = None
    rain_event_min_duration_minutes: int | None = None
    overflow_fill_threshold: float | None = None
    overflow_min_duration_minutes: int | None = None
    risk_fill_watch: float | None = None
    risk_fill_warning: float | None = None


@dataclass(frozen=True)
class CityConfig:
    city_id: str
    name: str
    country: str
    network: CityNetworkConfig
    telemetry: CityTelemetryConfig = CityTelemetryConfig()
    analytics: CityAnalyticsConfig = CityAnalyticsConfig()


CITY_CONFIGS: list[CityConfig] = [
    CityConfig(
        city_id="city_porto_mvp",
        name="Porto",
        country="PT",
        network=CityNetworkConfig(
            center_lon=-8.61,
            center_lat=41.15,
            half_size_deg=0.08,
            grid_n=20,
            outfall_count=3,
            seed=7,
        ),
        telemetry=CityTelemetryConfig(
            scenario="heavy_rain_high_river",
            realism="tier2_porto",
            realism_profile="porto",
            years=0,
            days=7,
            pipe_limit=150,
        ),
        analytics=CityAnalyticsConfig(
            rain_event_threshold_mmph=5.0,
            rain_event_min_duration_minutes=15,
            overflow_fill_threshold=1.0,
            overflow_min_duration_minutes=10,
            risk_fill_watch=1.15,
            risk_fill_warning=1.4,
        ),
    ),
    CityConfig(
        city_id="city_oslo_mvp",
        name="Oslo",
        country="NO",
        network=CityNetworkConfig(
            center_lon=10.75,
            center_lat=59.91,
            half_size_deg=0.07,
            grid_n=18,
            outfall_count=2,
            seed=11,
        ),
        telemetry=CityTelemetryConfig(
            scenario="normal",
            realism="synthetic",
            years=0,
            days=7,
            pipe_limit=120,
        ),
        analytics=CityAnalyticsConfig(
            rain_event_threshold_mmph=4.0,
            overflow_fill_threshold=1.05,
            risk_fill_watch=1.1,
            risk_fill_warning=1.35,
        ),
    ),
    CityConfig(
        city_id="city_houston_mvp",
        name="Houston",
        country="US",
        network=CityNetworkConfig(
            center_lon=-95.36,
            center_lat=29.76,
            half_size_deg=0.09,
            grid_n=22,
            outfall_count=4,
            seed=23,
        ),
        telemetry=CityTelemetryConfig(
            scenario="heavy_rain_low_river",
            realism="synthetic",
            years=0,
            days=7,
            pipe_limit=180,
        ),
        analytics=CityAnalyticsConfig(
            rain_event_threshold_mmph=6.0,
            overflow_fill_threshold=0.95,
            risk_fill_watch=1.1,
            risk_fill_warning=1.3,
        ),
    ),
]


def get_city_configs(selected_ids: str | None = None) -> list[CityConfig]:
    if selected_ids is None:
        selected_ids = os.environ.get("CITY_IDS")
    if not selected_ids:
        return CITY_CONFIGS
    wanted = {cid.strip() for cid in selected_ids.split(",") if cid.strip()}
    return [c for c in CITY_CONFIGS if c.city_id in wanted]


def get_city_config(city_id: str, configs: Iterable[CityConfig] | None = None) -> CityConfig | None:
    if configs is None:
        configs = CITY_CONFIGS
    for cfg in configs:
        if cfg.city_id == city_id:
            return cfg
    return None
