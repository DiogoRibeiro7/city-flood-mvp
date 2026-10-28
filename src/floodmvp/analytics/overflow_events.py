from __future__ import annotations

import datetime as dt

import pandas as pd

from floodmvp.analytics.threshold_events import detect_threshold_events


def detect_overflow_events(
    fill_df: pd.DataFrame,
    threshold: float = 1.0,
    min_duration_minutes: int = 10,
    max_gap_minutes: float = 5.0,
) -> list[tuple[dt.datetime, dt.datetime, float]]:
    """Detect overflow windows from pipe fill ratios without spanning data gaps.

    Returns (start, end, peak_fill) for each sustained exceedance.
    """
    return detect_threshold_events(
        fill_df,
        threshold=threshold,
        min_duration_minutes=min_duration_minutes,
        max_gap_minutes=max_gap_minutes,
    )
