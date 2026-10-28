from __future__ import annotations

import datetime as dt

import pandas as pd

from floodmvp.jobs.run_analytics import _coverage_ratio


def test_multiple_samples_in_one_bucket_count_once() -> None:
    """Bursty high-frequency samples must not mask missing five-minute buckets."""
    start = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
    end = start + dt.timedelta(minutes=20)
    timestamps = [start + dt.timedelta(minutes=minute) for minute in range(10)]
    observations = pd.DataFrame({"ts": timestamps, "value": [1.0] * 10})

    assert _coverage_ratio(observations, start, end, interval_minutes=5) == 0.5


def test_partial_buckets_and_out_of_window_samples() -> None:
    """Include only the three time buckets overlapping the requested window."""
    base = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
    start = base + dt.timedelta(minutes=2)
    end = base + dt.timedelta(minutes=12)
    observations = pd.DataFrame(
        {
            "ts": [base, base + dt.timedelta(minutes=3), base + dt.timedelta(minutes=6)],
            "value": [1.0, 1.0, 1.0],
        }
    )

    assert _coverage_ratio(observations, start, end, interval_minutes=5) == 2 / 3


def test_empty_window_and_invalid_granularity() -> None:
    start = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
    end = start + dt.timedelta(minutes=20)
    observations = pd.DataFrame(columns=["ts", "value"])

    assert _coverage_ratio(observations, start, end, interval_minutes=5) == 0.0
    assert _coverage_ratio(observations, start, end, interval_minutes=0) == 0.0
