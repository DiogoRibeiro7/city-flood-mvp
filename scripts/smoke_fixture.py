"""Fixed synthetic input shared by the disposable smoke seeder and assertions."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

CITY_ID = "city_porto_mvp"
RAIN_ID = "smoke_rain"
RIVER_ID = "smoke_river"
PIPE_ID = "smoke_pipe"
START = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
END = START + dt.timedelta(hours=1)
RAIN_VALUES = (0.0, 0.0, 8.0, 8.0, 8.0, 8.0, 8.0, 0.0, 0.0, 0.0, 0.0, 0.0)
FIXTURE_VERSION = "smoke-v1"


def measurements() -> list[dict[str, str | float]]:
    """Return 36 observations with stable asset IDs, timestamps and values."""
    rows: list[dict[str, str | float]] = []
    for asset_id, metric, values in (
        (RAIN_ID, "rain_mmph", RAIN_VALUES),
        (RIVER_ID, "water_level_m", (1.0,) * 12),
        (PIPE_ID, "fill_ratio", (0.5, 0.5, 1.2, 1.2, 1.2, 1.2, 1.2, 0.5, 0.5, 0.5, 0.5, 0.5)),
    ):
        for index, value in enumerate(values):
            rows.append(
                {
                    "asset_id": asset_id,
                    "metric": metric,
                    "ts": (START + dt.timedelta(minutes=5 * index)).isoformat(),
                    "value": value,
                }
            )
    return rows


def fixture_digest() -> str:
    return hashlib.sha256(json.dumps(measurements(), sort_keys=True).encode()).hexdigest()
