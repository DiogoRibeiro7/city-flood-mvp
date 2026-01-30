from __future__ import annotations

import datetime as dt

import pandas as pd


def detect_overflow_events(
    fill_df: pd.DataFrame,
    threshold: float = 1.0,
    min_duration_minutes: int = 10,
) -> list[tuple[dt.datetime, dt.datetime, float]]:
    """Detect overflow windows from pipe fill ratio (>1.0).

    Returns list of (start, end, peak_fill).
    """
    if not {"ts", "value"}.issubset(fill_df.columns):
        raise ValueError("fill_df must have columns ts,value")

    df = fill_df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts")

    over = df["value"] >= threshold
    events: list[tuple[dt.datetime, dt.datetime, float]] = []
    if over.sum() == 0:
        return events

    grp = (over != over.shift(1)).cumsum()
    for _, g in df[over].groupby(grp):
        start = g["ts"].iloc[0]
        step = g["ts"].iloc[1] - g["ts"].iloc[0] if len(g) > 1 else pd.Timedelta(minutes=1)
        end = g["ts"].iloc[-1] + step
        duration = (end - start).total_seconds() / 60.0
        if duration >= min_duration_minutes:
            events.append((start.to_pydatetime(), end.to_pydatetime(), float(g["value"].max())))
    return events
