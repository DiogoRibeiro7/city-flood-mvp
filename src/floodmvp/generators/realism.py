from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from floodmvp.generators.telemetry import TelemetrySeries


@dataclass(frozen=True)
class Era5Config:
    lat: float
    lon: float
    area_buffer_deg: float = 0.1
    cache_dir: Path = Path("data/realism")


PORTO = Era5Config(lat=41.1496, lon=-8.6109)


def fetch_era5_land_hourly_precip(
    start: dt.datetime,
    end: dt.datetime,
    config: Era5Config = PORTO,
) -> Path:
    """Fetch ERA5-Land hourly total precipitation for a small area around a point.

    Returns path to NetCDF file. Requires cdsapi + configured ~/.cdsapirc.
    """
    try:
        import cdsapi  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("cdsapi is required for ERA5 download") from e

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be tz-aware")

    config.cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.cache_dir / "era5_land_hourly_precip.nc"
    if out_path.exists():
        return out_path

    date_index = pd.date_range(start=start, end=end, freq="1h", tz="UTC", inclusive="left")
    years = sorted({d.strftime("%Y") for d in date_index})
    months = sorted({d.strftime("%m") for d in date_index})
    days = sorted({d.strftime("%d") for d in date_index})
    times = [f"{h:02d}:00" for h in range(24)]

    north = config.lat + config.area_buffer_deg
    south = config.lat - config.area_buffer_deg
    west = config.lon - config.area_buffer_deg
    east = config.lon + config.area_buffer_deg

    req = {
        "product_type": "reanalysis",
        "variable": "total_precipitation",
        "year": years,
        "month": months,
        "day": days,
        "time": times,
        "area": [north, west, south, east],
        "format": "netcdf",
    }

    client = cdsapi.Client()
    client.retrieve("reanalysis-era5-land", req, str(out_path))
    return out_path


def _load_hourly_precip_mm(path: Path, lat: float, lon: float) -> pd.DataFrame:
    with xr.open_dataset(path) as ds:
        var = None
        for key in ("tp", "total_precipitation"):
            if key in ds.data_vars:
                var = key
                break
        if var is None:
            raise ValueError("No total precipitation variable found in ERA5 file")
        da = ds[var]
        if "latitude" in da.dims and "longitude" in da.dims:
            da = da.sel(latitude=lat, longitude=lon, method="nearest")
        df = da.to_dataframe().reset_index()
        df = df.rename(columns={var: "precip_m"})
        df["ts"] = pd.to_datetime(df["time"], utc=True)
        df = df[["ts", "precip_m"]].sort_values("ts")
        df["value_mm"] = df["precip_m"].astype(float) * 1000.0
        return df[["ts", "value_mm"]]


def _disaggregate_hourly_to_5min(
    hourly_mm: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for _, row in hourly_mm.iterrows():
        ts = row["ts"]
        total = float(row["value_mm"])
        if total <= 0.0:
            for i in range(12):
                rows.append({"ts": ts + dt.timedelta(minutes=5 * i), "value": 0.0})
            continue
        # Burstiness: heavier hours get more uneven splits.
        alpha = 0.4 if total >= 3.0 else 1.5
        weights = rng.gamma(shape=alpha, scale=1.0, size=12)
        weights = weights / (weights.sum() + 1e-9)
        for i, w in enumerate(weights):
            rows.append({"ts": ts + dt.timedelta(minutes=5 * i), "value": total * w})
    df = pd.DataFrame(rows)
    return df


def generate_rain_series_tier2(
    asset_id: str,
    start: dt.datetime,
    end: dt.datetime,
    config: Era5Config = PORTO,
    seed: int = 42,
) -> TelemetrySeries:
    """Data-driven rain series using ERA5-Land hourly data disaggregated to 5-min."""
    nc_path = fetch_era5_land_hourly_precip(start, end, config=config)
    hourly = _load_hourly_precip_mm(nc_path, config.lat, config.lon)
    # Keep only requested window
    hourly = hourly[(hourly["ts"] >= start) & (hourly["ts"] < end)]
    five = _disaggregate_hourly_to_5min(hourly, seed=seed)
    # Convert hourly totals (mm) to mm/h at 5-min resolution.
    five["value"] = five["value"].astype(float) * 12.0
    return TelemetrySeries(asset_id=asset_id, metric="rain_mmph", df=five)


def generate_river_level_tier2(
    asset_id: str,
    rain: TelemetrySeries,
    seed: int = 7,
) -> TelemetrySeries:
    """River level (m) driven by rain using a simple linear reservoir model."""
    rng = np.random.default_rng(seed)
    ts = pd.to_datetime(rain.df["ts"], utc=True)
    rain_mmph = rain.df["value"].to_numpy()
    # Convert mm/h at 5-min to mm per step
    rain_mm = rain_mmph / 12.0

    # Linear reservoir parameters (tuned for realism, not physics)
    k = 6.0  # hours
    alpha = 1.0 - np.exp(-1.0 / (k * 12.0))  # 5-min timestep
    storage = 0.0
    flow = np.zeros_like(rain_mm)
    for i, r in enumerate(rain_mm):
        storage = storage + r - alpha * storage
        flow[i] = storage

    flow_norm = flow / (np.percentile(flow, 95) + 1e-9)
    seasonal = 0.15 * np.sin(np.linspace(0, 2 * np.pi, len(flow_norm)))
    level = 1.1 + 0.9 * flow_norm + seasonal
    level += rng.normal(0, 0.03, size=len(level))
    level = np.clip(level, 0.6, 3.5)

    df = pd.DataFrame({"ts": ts.dt.to_pydatetime(), "value": level.astype(float)})
    return TelemetrySeries(asset_id=asset_id, metric="water_level_m", df=df)


def write_realism_stats(
    rain: TelemetrySeries,
    river: TelemetrySeries,
    config: Era5Config = PORTO,
) -> Path:
    stats = {
        "rain_p95_mmph": float(np.percentile(rain.df["value"], 95)),
        "rain_p99_mmph": float(np.percentile(rain.df["value"], 99)),
        "river_p95_m": float(np.percentile(river.df["value"], 95)),
        "river_p99_m": float(np.percentile(river.df["value"], 99)),
    }
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.cache_dir / "porto_realism_stats.json"
    out_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return out_path
