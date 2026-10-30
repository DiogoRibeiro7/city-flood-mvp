from __future__ import annotations

import datetime as dt
import math

import pandas as pd

EventWindow = tuple[dt.datetime, dt.datetime, float]


def detect_threshold_events(
    observations: pd.DataFrame,
    *,
    threshold: float,
    min_duration_minutes: int,
    max_gap_minutes: float,
) -> list[EventWindow]:
    """Find sustained threshold exceedances without bridging missing telemetry.

    Timestamps mark samples, so the final sample is extended by the median
    observed cadence (up to ``max_gap_minutes``). If no cadence can be inferred,
    a conservative one-minute interval is used. Larger gaps always split events.
    """
    if not isinstance(observations, pd.DataFrame):
        raise TypeError("observations must be a pandas DataFrame")
    if not {"ts", "value"}.issubset(observations.columns):
        raise ValueError("observations must have columns ts,value")
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    if min_duration_minutes < 0:
        raise ValueError("min_duration_minutes must be non-negative")
    if not math.isfinite(max_gap_minutes) or max_gap_minutes <= 0:
        raise ValueError("max_gap_minutes must be finite and positive")
    if observations.empty:
        return []

    df = observations[["ts", "value"]].copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if df["ts"].isna().any():
        raise ValueError("timestamps must not be missing")
    df["value"] = pd.to_numeric(df["value"], errors="raise")
    # A timestamp represents one observation; the latest value wins on duplicates.
    df = df.sort_values("ts", kind="stable").drop_duplicates("ts", keep="last")
    df = df.reset_index(drop=True)

    max_gap = pd.Timedelta(minutes=max_gap_minutes)
    gaps = df["ts"].diff()
    observed_cadence = gaps[(gaps > pd.Timedelta(0)) & (gaps <= max_gap)]
    sample_period = (
        observed_cadence.median() if not observed_cadence.empty else pd.Timedelta(minutes=1)
    )

    above = df["value"] >= threshold
    if not above.any():
        return []

    # A threshold change or a telemetry outage starts a new episode.
    new_episode = above.ne(above.shift(fill_value=False)) | gaps.gt(max_gap)
    episode_ids = new_episode.cumsum()

    events: list[EventWindow] = []
    for _, episode in df.loc[above].groupby(episode_ids[above], sort=False):
        start = episode["ts"].iloc[0]
        end = episode["ts"].iloc[-1] + sample_period
        if (end - start).total_seconds() / 60 >= min_duration_minutes:
            events.append(
                (start.to_pydatetime(), end.to_pydatetime(), float(episode["value"].max()))
            )
    return events
