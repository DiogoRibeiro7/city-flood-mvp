from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    """Return timezone-aware UTC now."""
    return dt.datetime.now(dt.timezone.utc)


def parse_iso8601(ts: str) -> dt.datetime:
    """Parse ISO8601 timestamp to tz-aware datetime (UTC if missing tz)."""
    out = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if out.tzinfo is None:
        out = out.replace(tzinfo=dt.timezone.utc)
    return out.astimezone(dt.timezone.utc)
