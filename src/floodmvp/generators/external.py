from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Literal

import numpy as np


PatternType = Literal["steady", "storm_bursts", "seasonal", "random_walk"]


@dataclass(frozen=True)
class RainGaugeGenConfig:
    device_id: str
    start: dt.datetime
    end: dt.datetime
    cadence_seconds: int = 60
    pattern: PatternType = "storm_bursts"
    base_mmph: float = 0.5
    peak_mmph: float = 35.0
    noise_sigma: float = 0.6
    pattern_overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    outage_count: int = 0
    outage_min_minutes: int = 10
    outage_max_minutes: int = 120
    seed: int = 42


@dataclass(frozen=True)
class RiverLevelGenConfig:
    device_id: str
    start: dt.datetime
    end: dt.datetime
    cadence_seconds: int = 60
    pattern: PatternType = "seasonal"
    base_m: float = 1.2
    peak_m: float = 3.2
    noise_sigma: float = 0.03
    pattern_overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    outage_count: int = 0
    outage_min_minutes: int = 10
    outage_max_minutes: int = 120
    seed: int = 43


def _ts_range(start: dt.datetime, end: dt.datetime, cadence_seconds: int) -> list[dt.datetime]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=dt.timezone.utc)
    if end <= start:
        return []
    delta = dt.timedelta(seconds=cadence_seconds)
    out = []
    ts = start
    while ts <= end:
        out.append(ts)
        ts += delta
    return out


def _seasonal_curve(n: int, cycles: float = 1.0) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi * cycles, n)
    return 0.5 * (1 + np.sin(t - np.pi / 2))


def _storm_bursts(n: int, rng: np.random.Generator, burst_chance: float = 0.015) -> np.ndarray:
    out = np.zeros(n)
    for i in range(n):
        if rng.random() < burst_chance:
            length = int(rng.integers(10, 90))
            peak = rng.uniform(0.6, 1.0)
            for j in range(length):
                if i + j >= n:
                    break
                decay = 1.0 - (j / max(1, length))
                out[i + j] = max(out[i + j], peak * decay)
    return out


def _apply_outages(
    ts_list: list[dt.datetime],
    values: np.ndarray,
    rng: np.random.Generator,
    outage_count: int,
    outage_min_minutes: int,
    outage_max_minutes: int,
) -> tuple[list[dt.datetime], np.ndarray]:
    if outage_count <= 0 or not ts_list:
        return ts_list, values
    n = len(ts_list)
    if outage_max_minutes < outage_min_minutes:
        outage_max_minutes = outage_min_minutes
    cadence_minutes = max(1, int((ts_list[1] - ts_list[0]).total_seconds() / 60)) if n > 1 else 1
    mask = np.ones(n, dtype=bool)
    for _ in range(outage_count):
        length_min = int(rng.integers(outage_min_minutes, max(outage_min_minutes + 1, outage_max_minutes + 1)))
        length_steps = max(1, length_min // cadence_minutes)
        start_idx = int(rng.integers(0, max(1, n - length_steps)))
        end_idx = min(n, start_idx + length_steps)
        mask[start_idx:end_idx] = False
    ts_out = [ts for ts, keep in zip(ts_list, mask) if keep]
    values_out = values[mask]
    return ts_out, values_out


def _pattern_params(
    pattern: PatternType,
    base: float,
    peak: float,
    noise_sigma: float,
    overrides: dict[str, dict[str, float]],
) -> tuple[float, float, float, dict[str, float]]:
    params = {"burst_chance": 0.0, "cycles": 1.0, "step_sigma": 0.0}
    for k, v in overrides.get(pattern, {}).items():
        params[k] = float(v)
    base = float(overrides.get(pattern, {}).get("base", base))
    peak = float(overrides.get(pattern, {}).get("peak", peak))
    noise_sigma = float(overrides.get(pattern, {}).get("noise_sigma", noise_sigma))
    return base, peak, noise_sigma, params


def generate_rain_gauge(config: RainGaugeGenConfig) -> list[dict[str, object]]:
    rng = np.random.default_rng(config.seed)
    ts_list = _ts_range(config.start, config.end, config.cadence_seconds)
    n = len(ts_list)
    if n == 0:
        return []

    base, peak, noise_sigma, params = _pattern_params(
        config.pattern, config.base_mmph, config.peak_mmph, config.noise_sigma, config.pattern_overrides
    )

    if config.pattern == "steady":
        signal = np.ones(n)
    elif config.pattern == "storm_bursts":
        burst_chance = params.get("burst_chance", 0.015) or 0.015
        signal = _storm_bursts(n, rng, burst_chance=burst_chance)
    elif config.pattern == "seasonal":
        cycles = params.get("cycles", 1.0) or 1.0
        signal = _seasonal_curve(n, cycles=cycles)
    elif config.pattern == "random_walk":
        step_sigma = params.get("step_sigma", 0.08) or 0.08
        steps = rng.normal(0, step_sigma, size=n)
        signal = np.cumsum(steps)
        signal = (signal - signal.min()) / max(1e-6, (signal.max() - signal.min()))
    else:
        raise ValueError("unknown pattern")

    values = base + (peak - base) * signal
    values += rng.normal(0, noise_sigma, size=n)
    values = np.clip(values, 0.0, None)

    ts_list, values = _apply_outages(
        ts_list,
        values,
        rng,
        outage_count=config.outage_count,
        outage_min_minutes=config.outage_min_minutes,
        outage_max_minutes=config.outage_max_minutes,
    )

    return [
        {
            "device_id": config.device_id,
            "metric": "rain_mmph",
            "ts": ts.isoformat().replace("+00:00", "Z"),
            "value": float(val),
            "quality_flag": "ok",
        }
        for ts, val in zip(ts_list, values)
    ]


def generate_river_level(config: RiverLevelGenConfig) -> list[dict[str, object]]:
    rng = np.random.default_rng(config.seed)
    ts_list = _ts_range(config.start, config.end, config.cadence_seconds)
    n = len(ts_list)
    if n == 0:
        return []

    base, peak, noise_sigma, params = _pattern_params(
        config.pattern, config.base_m, config.peak_m, config.noise_sigma, config.pattern_overrides
    )

    if config.pattern == "steady":
        signal = np.ones(n)
    elif config.pattern == "storm_bursts":
        burst_chance = params.get("burst_chance", 0.008) or 0.008
        signal = _storm_bursts(n, rng, burst_chance=burst_chance)
    elif config.pattern == "seasonal":
        cycles = params.get("cycles", 0.5) or 0.5
        signal = _seasonal_curve(n, cycles=cycles)
    elif config.pattern == "random_walk":
        step_sigma = params.get("step_sigma", 0.02) or 0.02
        steps = rng.normal(0, step_sigma, size=n)
        signal = np.cumsum(steps)
        signal = (signal - signal.min()) / max(1e-6, (signal.max() - signal.min()))
    else:
        raise ValueError("unknown pattern")

    values = base + (peak - base) * signal
    values += rng.normal(0, noise_sigma, size=n)
    values = np.clip(values, 0.0, None)

    ts_list, values = _apply_outages(
        ts_list,
        values,
        rng,
        outage_count=config.outage_count,
        outage_min_minutes=config.outage_min_minutes,
        outage_max_minutes=config.outage_max_minutes,
    )

    return [
        {
            "device_id": config.device_id,
            "metric": "water_level_m",
            "ts": ts.isoformat().replace("+00:00", "Z"),
            "value": float(val),
            "quality_flag": "ok",
        }
        for ts, val in zip(ts_list, values)
    ]


def write_json(path: str, records: list[dict[str, object]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
