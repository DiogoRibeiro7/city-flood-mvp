from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RiverLevelFetchConfig:
    url: str
    format: str  # json | csv
    device_field: str
    ts_field: str
    value_field: str
    metric: str = "water_level_m"
    headers: dict[str, str] | None = None
    timeout_s: float = 30.0


def _parse_ts(value: str) -> dt.datetime:
    ts = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    return ts


def _as_rows_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict) and "records" in payload and isinstance(payload["records"], list):
        return [r for r in payload["records"] if isinstance(r, dict)]
    raise ValueError("Unsupported JSON payload. Use a list or {records:[...]}")


def fetch_river_level_rows(config: RiverLevelFetchConfig) -> list[dict[str, Any]]:
    with httpx.Client(timeout=config.timeout_s) as client:
        resp = client.get(config.url, headers=config.headers)
        resp.raise_for_status()
        if config.format == "json":
            payload = resp.json()
            return _as_rows_json(payload)
        if config.format == "csv":
            rows: list[dict[str, Any]] = []
            reader = csv.DictReader(resp.text.splitlines())
            for row in reader:
                rows.append(row)
            return rows
        raise ValueError("format must be json or csv")


def normalize_river_level_rows(
    rows: list[dict[str, Any]],
    config: RiverLevelFetchConfig,
    metric_override: str | None = None,
) -> list[dict[str, Any]]:
    metric = metric_override or config.metric
    out: list[dict[str, Any]] = []
    for row in rows:
        device_id = row.get(config.device_field)
        ts = row.get(config.ts_field)
        value = row.get(config.value_field)
        out.append(
            {
                "device_id": device_id,
                "metric": metric,
                "ts": ts,
                "value": value,
                "quality_flag": row.get("quality_flag") or row.get("quality") or "ok",
            }
        )
    return out


def convert_units(value: float, units: str) -> float:
    if units == "m":
        return value
    if units == "cm":
        return value / 100.0
    if units == "mm":
        return value / 1000.0
    if units == "ft":
        return value * 0.3048
    if units == "in":
        return value * 0.0254
    raise ValueError("units must be one of m, cm, mm, ft, in")


def apply_unit_conversion(rows: list[dict[str, Any]], units: str) -> None:
    if units == "m":
        return
    for row in rows:
        raw = row.get("value")
        if raw is None:
            continue
        row["value"] = convert_units(float(raw), units)
