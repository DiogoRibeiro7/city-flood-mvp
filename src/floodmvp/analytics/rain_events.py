from __future__ import annotations

import datetime as dt

import pandas as pd

from floodmvp.analytics.threshold_events import detect_threshold_events


def detect_rain_events(
    rain_df: pd.DataFrame,
    threshold_mmph: float = 5.0,
    min_duration_minutes: int = 15,
    max_gap_minutes: float = 5.0,
) -> list[tuple[dt.datetime, dt.datetime, float]]:
    """Detect sustained rain episodes without spanning missing telemetry.

    Returns (start, end, peak_mmph) for each sustained exceedance.
    """
    return detect_threshold_events(
        rain_df,
        threshold=threshold_mmph,
        min_duration_minutes=min_duration_minutes,
        max_gap_minutes=max_gap_minutes,
    )
