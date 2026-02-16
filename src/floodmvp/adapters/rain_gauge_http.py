from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RainGaugeFetchConfig:
    url: str
    format: str  # json | csv
    device_field: str
    ts_field: str
    value_field: str
    metric: str = "rain_mmph"
    headers: dict[str, str] | None = None
    timeout_s: float = 30.0


def _parse_ts(value: str) -> dt.datetime:
    ts = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts


def _as_rows_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        if "records" in payload and isinstance(payload["records"], list):
            return [r for r in payload["records"] if isinstance(r, dict)]
    raise ValueError("Unsupported JSON payload. Use a list or {records:[...]}")


def fetch_rain_gauge_rows(config: RainGaugeFetchConfig) -> list[dict[str, Any]]:
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


def normalize_rain_gauge_rows(
    rows: list[dict[str, Any]],
    config: RainGaugeFetchConfig,
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


def convert_units(value: float, units: str, interval_minutes: int | None = None) -> float:
    if units == "mmph":
        return value
    if units == "mm":
        if not interval_minutes:
            raise ValueError("interval_minutes is required when units=mm")
        return value * (60.0 / float(interval_minutes))
    if units == "in":
        return value * 25.4
    if units == "inph":
        return value * 25.4
    raise ValueError("units must be one of mmph, mm, in, inph")


def apply_unit_conversion(rows: list[dict[str, Any]], units: str, interval_minutes: int | None) -> None:
    if units == "mmph":
        return
    for row in rows:
        raw = row.get("value")
        if raw is None:
            continue
        row["value"] = convert_units(float(raw), units, interval_minutes=interval_minutes)
