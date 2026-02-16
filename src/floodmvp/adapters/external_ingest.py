from __future__ import annotations

import csv
import datetime as dt
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IngestRecord:
    asset_id: str
    metric: str
    ts: dt.datetime
    value: float
    quality_flag: str = "ok"
    source: str = "external"


@dataclass
class IngestStats:
    received: int = 0
    accepted: int = 0
    rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def add_rejection(self, reason: str) -> None:
        self.rejected += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _parse_ts(value: str) -> dt.datetime:
    ts = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    return ts


def _normalize_record(raw: dict[str, Any], default_device_id: str | None = None) -> dict[str, Any]:
    device_id = raw.get("asset_id") or raw.get("device_id") or default_device_id
    metric = raw.get("metric") or raw.get("type")
    ts = raw.get("ts") or raw.get("timestamp")
    value = raw.get("value")
    quality_flag = raw.get("quality_flag") or raw.get("quality") or "ok"
    return {
        "device_id": device_id,
        "metric": metric,
        "ts": ts,
        "value": value,
        "quality_flag": quality_flag,
    }


def parse_csv(path: Path, default_device_id: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(_normalize_record(row, default_device_id=default_device_id))
    return rows


def parse_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [_normalize_record(r) for r in raw]
    if isinstance(raw, dict):
        if "records" in raw and isinstance(raw["records"], list):
            return [_normalize_record(r) for r in raw["records"]]
        if "device_id" in raw and "events" in raw and isinstance(raw["events"], list):
            default_device_id = raw.get("device_id")
            return [_normalize_record(r, default_device_id=default_device_id) for r in raw["events"]]
    raise ValueError("Unsupported JSON format. Use a list, {records:[...]}, or {device_id, events:[...]}.")


def parse_ndjson(lines: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if isinstance(raw, dict):
            rows.append(_normalize_record(raw))
        else:
            raise ValueError("NDJSON lines must be JSON objects")
    return rows


def validate_records(
    rows: Iterable[dict[str, Any]],
    asset_map: dict[str, str] | None = None,
    allowed_asset_ids: set[str] | None = None,
    city_by_asset: dict[str, str] | None = None,
    city_id: str | None = None,
    source: str = "external",
) -> tuple[list[IngestRecord], IngestStats]:
    stats = IngestStats()
    records: list[IngestRecord] = []

    for row in rows:
        stats.received += 1
        device_id = row.get("device_id")
        if not device_id:
            stats.add_rejection("device_id is required")
            continue
        asset_id = asset_map[device_id] if asset_map and device_id in asset_map else device_id

        if allowed_asset_ids is not None and asset_id not in allowed_asset_ids:
            stats.add_rejection("asset_id not found")
            continue

        if city_id and city_by_asset is not None:
            asset_city = city_by_asset.get(asset_id)
            if asset_city != city_id:
                stats.add_rejection("asset_id not in city")
                continue

        metric = row.get("metric")
        if not metric or not str(metric).strip():
            stats.add_rejection("metric is required")
            continue

        ts_raw = row.get("ts")
        if not ts_raw:
            stats.add_rejection("ts is required")
            continue
        try:
            ts = _parse_ts(str(ts_raw))
        except Exception:
            stats.add_rejection("ts must be ISO 8601")
            continue

        value_raw = row.get("value")
        if not _is_finite_number(value_raw):
            stats.add_rejection("value must be a finite number")
            continue

        quality_flag = str(row.get("quality_flag") or "ok")
        records.append(
            IngestRecord(
                asset_id=asset_id,
                metric=str(metric),
                ts=ts,
                value=float(value_raw),
                quality_flag=quality_flag,
                source=source,
            )
        )
        stats.accepted += 1

    return records, stats


def load_asset_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("asset map json must be an object of external_id -> asset_id")
        return {str(k): str(v) for k, v in raw.items()}
    if path.suffix.lower() in {".csv", ".tsv"}:
        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        out: dict[str, str] = {}
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                ext = row.get("external_id") or row.get("device_id")
                asset_id = row.get("asset_id")
                if not ext or not asset_id:
                    continue
                out[str(ext)] = str(asset_id)
        return out
    raise ValueError("asset map must be .json, .csv, or .tsv")
