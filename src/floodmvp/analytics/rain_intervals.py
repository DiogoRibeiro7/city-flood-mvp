"""Descriptive analytics on explicit GHCNh accumulation intervals, without resampling."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from typing import Any

from floodmvp.adapters.external_ingest import IngestRecord
from floodmvp.adapters.noaa_ghcnh import FIELD, INTERVAL_MINUTES, METRIC, SOURCE, utc

ANALYSIS_VERSION = "1"


def describe_rain_intervals(
    records: Sequence[IngestRecord], start: dt.datetime, end: dt.datetime
) -> dict[str, Any]:
    """Classify each quantitative six-hour report; do not infer rain timing or flood events."""
    start, end = utc(start), utc(end)
    if end <= start:
        raise ValueError("analysis window must have positive duration")
    intervals: list[dict[str, Any]] = []
    seen: set[tuple[str, dt.datetime]] = set()
    for record in sorted(records, key=lambda r: (r.ts, r.asset_id)):
        timestamp = utc(record.ts)
        key = (record.asset_id, timestamp)
        if key in seen:
            raise ValueError("interval analytics requires deduplicated observations")
        seen.add(key)
        observation = record.lineage.get("observation", {})
        left = utc(dt.datetime.fromisoformat(observation["interval_start"]))
        right = utc(dt.datetime.fromisoformat(observation["interval_end"]))
        depth = float(observation["depth_mm"])
        attributes = observation.get("attributes", {})
        if (
            record.source != SOURCE
            or record.metric != METRIC
            or observation.get("field") != FIELD
            or observation.get("interval_minutes") != INTERVAL_MINUTES
            or attributes.get("Measurement_Code") != ""
            or attributes.get("Quality_Code") != ""
            or right != timestamp
            or right - left != dt.timedelta(minutes=INTERVAL_MINUTES)
            or not start <= timestamp < end
            or not math.isfinite(depth)
            or depth < 0
            or not math.isclose(record.value, depth / 6, rel_tol=1e-12, abs_tol=0)
        ):
            raise ValueError("observation does not satisfy the six-hour rainfall contract")
        intervals.append(
            {
                "station_id": record.source_id,
                "asset_id": record.asset_id,
                "report_timestamp": timestamp.isoformat(),
                "interval_start": left.isoformat(),
                "interval_end": right.isoformat(),
                "depth_mm": depth,
                "six_hour_mean_mmph": record.value,
                "classification": "reported_wet_interval"
                if depth > 0
                else "observed_zero_interval",
                "minutes_inside_window": max(
                    0.0, (min(right, end) - max(left, start)).total_seconds() / 60
                ),
                "quality_flag": record.quality_flag,
                "source_sha256": record.lineage["chunk"]["sha256"],
                "source_line": record.lineage["source_line"],
            }
        )
    return {
        "analysis_version": ANALYSIS_VERSION,
        "method": "classify reported six-hour depths as positive or zero; no interpolation",
        "interpretation": "Descriptive rainfall intervals, not confirmed incidents or validated predictions.",
        "wet_depth_threshold_mm": 0.0,
        "comparison": "strictly_greater",
        "quantitative_reports": len(intervals),
        "reported_wet_intervals": sum(i["depth_mm"] > 0 for i in intervals),
        "observed_zero_intervals": sum(i["depth_mm"] == 0 for i in intervals),
        "maximum_reported_depth_mm": max((i["depth_mm"] for i in intervals), default=None),
        "maximum_six_hour_mean_mmph": max(
            (i["six_hour_mean_mmph"] for i in intervals), default=None
        ),
        "intervals": intervals,
        "operational_detector": {
            "status": "not_run",
            "reason": "Six-hour totals do not support the existing 15-minute rain_mmph intensity detector.",
        },
        "event_evaluation": {
            "status": "not_evaluated",
            "reason": "No independent event labels or fully reviewed event-free periods are established.",
            "confirmed_flood_incidents": None,
            "precision": None,
            "recall": None,
            "false_alarms_per_station_day": None,
            "lead_time_seconds": None,
        },
    }
