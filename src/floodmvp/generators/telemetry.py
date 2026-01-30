from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TelemetrySeries:
    asset_id: str
    metric: str
    df: pd.DataFrame  # columns: ts, value


def _date_range_utc(start: dt.datetime, end: dt.datetime, freq: str) -> pd.DatetimeIndex:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be tz-aware")
    return pd.date_range(start=start, end=end, freq=freq, tz="UTC", inclusive="left")


def generate_rain_series(
    asset_id: str,
    start: dt.datetime,
    end: dt.datetime,
    freq: str = "1min",
    scenario: str = "heavy_rain_high_river",
    seed: int = 7,
) -> TelemetrySeries:
    """Synthetic rain intensity in mm/h."""
    rng = np.random.default_rng(seed)
    ts = _date_range_utc(start, end, freq)
    n = len(ts)
    base = rng.gamma(shape=0.3, scale=2.0, size=n)  # mostly near 0
    storms = np.zeros(n)

    # Add 1-3 storm pulses
    k = 2 if "heavy" in scenario else 1
    for _ in range(k):
        center = rng.integers(low=int(0.2 * n), high=int(0.9 * n))
        width = rng.integers(low=int(0.02 * n), high=int(0.08 * n))
        amp = float(rng.uniform(20, 80) if "heavy" in scenario else rng.uniform(5, 25))
        x = np.arange(n)
        storms += amp * np.exp(-0.5 * ((x - center) / max(width, 1)) ** 2)

    noise = rng.normal(0, 0.8, size=n)
    rain_mmph = np.clip(base + storms + noise, 0, None)

    df = pd.DataFrame({"ts": ts.to_pydatetime(), "value": rain_mmph.astype(float)})
    return TelemetrySeries(asset_id=asset_id, metric="rain_mmph", df=df)


def generate_river_level_series(
    asset_id: str,
    rain: TelemetrySeries,
    scenario: str = "heavy_rain_high_river",
    seed: int = 11,
) -> TelemetrySeries:
    """River level in meters. Correlated with rain (delayed) + smooth trend."""
    rng = np.random.default_rng(seed)
    ts = pd.to_datetime(rain.df["ts"], utc=True)
    n = len(ts)

    # Base level + smooth oscillation
    t = np.linspace(0, 2 * np.pi, n)
    base = 1.5 + 0.15 * np.sin(t)

    # Rain response (delay + convolution)
    rain_vals = rain.df["value"].to_numpy()
    delay = 60 if "heavy" in scenario else 30  # minutes
    kernel = np.exp(-np.linspace(0, 6, 180))
    resp = np.convolve(rain_vals, kernel, mode="same") / (kernel.sum() + 1e-9)
    resp = np.roll(resp, delay)

    scale = 0.015 if "high_river" in scenario else 0.008
    level = base + scale * resp + rng.normal(0, 0.02, size=n)

    if "high_river" in scenario:
        level += 0.4  # elevated boundary

    df = pd.DataFrame({"ts": ts.to_pydatetime(), "value": level.astype(float)})
    return TelemetrySeries(asset_id=asset_id, metric="water_level_m", df=df)


def generate_pipe_fill_ratio_series(
    asset_id: str,
    rain: TelemetrySeries,
    river_level: TelemetrySeries,
    sensitivity: float,
    seed: int = 23,
) -> TelemetrySeries:
    """Pipe fill ratio ~ 0..1+ . Exceeds 1.0 => overflow risk."""
    rng = np.random.default_rng(seed)
    ts = pd.to_datetime(rain.df["ts"], utc=True)
    n = len(ts)

    r = rain.df["value"].to_numpy()
    h = river_level.df["value"].to_numpy()

    # A simple dynamic: fill responds to rain + backwater from river
    backwater = np.clip((h - np.percentile(h, 70)), 0, None)
    fill = 0.2 + sensitivity * (r / 80.0) + 0.6 * (backwater / (backwater.max() + 1e-9))
    fill += rng.normal(0, 0.03, size=n)
    fill = np.clip(fill, 0, None)

    df = pd.DataFrame({"ts": ts.to_pydatetime(), "value": fill.astype(float)})
    return TelemetrySeries(asset_id=asset_id, metric="fill_ratio", df=df)
