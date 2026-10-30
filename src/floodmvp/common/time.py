from __future__ import annotations

import datetime as dt
import re

_BUCKET_INTERVAL_PATTERN = re.compile(
    r"^\s*(\d{1,6})\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|"
    r"h|hr|hrs|hour|hours|d|day|days)\s*$",
    re.IGNORECASE,
)
_UNIT_SECONDS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
}


def utc_now() -> dt.datetime:
    """Return timezone-aware UTC now."""
    return dt.datetime.now(dt.UTC)


def parse_iso8601(ts: str) -> dt.datetime:
    """Parse ISO8601 timestamp to tz-aware datetime (UTC if missing tz)."""
    return normalize_utc(dt.datetime.fromisoformat(ts.replace("Z", "+00:00")))


def normalize_utc(value: dt.datetime) -> dt.datetime:
    """Use UTC for missing offsets and normalize explicit offsets to UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    try:
        return value.astimezone(dt.UTC)
    except OverflowError as exc:
        raise ValueError("timestamp is outside the supported UTC range") from exc


def parse_bucket_interval(value: str) -> dt.timedelta:
    """Convert a time-bucket granularity into a typed PostgreSQL interval.

    Accept second, minute, hour and day units, including API shorthands such
    as ``5m`` and ``1h``. Keep intervals positive and no longer than 30 days.
    """
    match = _BUCKET_INTERVAL_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("granularity must be a positive interval such as 5m, 1h or 1d")
    quantity = int(match.group(1))
    seconds = quantity * _UNIT_SECONDS[match.group(2).lower()]
    duration = dt.timedelta(seconds=seconds)
    if duration <= dt.timedelta(0) or duration > dt.timedelta(days=30):
        raise ValueError("granularity must be between 1 second and 30 days")
    return duration
