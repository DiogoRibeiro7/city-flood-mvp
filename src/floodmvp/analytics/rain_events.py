from __future__ import annotations

import datetime as dt

import pandas as pd


def detect_rain_events(
    rain_df: pd.DataFrame,
    threshold_mmph: float = 5.0,
    min_duration_minutes: int = 15,
) -> list[tuple[dt.datetime, dt.datetime, float]]:
    """Detect rain episodes from intensity time series.

    Returns list of (start, end, peak_mmph).
    """
    if not {"ts", "value"}.issubset(rain_df.columns):
        raise ValueError("rain_df must have columns ts,value")

    df = rain_df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts")

    wet = df["value"] >= threshold_mmph
    events: list[tuple[dt.datetime, dt.datetime, float]] = []

    if wet.sum() == 0:
        return events

    # group contiguous wet periods
    grp = (wet != wet.shift(1)).cumsum()
    for _, g in df[wet].groupby(grp):
        start = g["ts"].iloc[0]
        end = g["ts"].iloc[-1] + (g["ts"].iloc[1] - g["ts"].iloc[0] if len(g) > 1 else pd.Timedelta(minutes=1))
        duration = (end - start).total_seconds() / 60.0
        if duration >= min_duration_minutes:
            events.append((start.to_pydatetime(), end.to_pydatetime(), float(g["value"].max())))

    return events
