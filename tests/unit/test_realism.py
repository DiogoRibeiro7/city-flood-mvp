from __future__ import annotations

import datetime as dt

import pandas as pd

from floodmvp.generators.realism import _disaggregate_hourly_to_5min


def test_disaggregate_hourly_to_5min_preserves_totals() -> None:
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    hourly = pd.DataFrame(
        {
            "ts": [base, base + dt.timedelta(hours=1)],
            "value_mm": [12.0, 0.0],
        }
    )
    five = _disaggregate_hourly_to_5min(hourly, seed=123)
    assert len(five) == 24
    assert (five["value"] >= 0.0).all()
    five["hour"] = five["ts"].dt.floor("h")
    sums = five.groupby("hour")["value"].sum().tolist()
    assert abs(sums[0] - 12.0) < 1e-6
    assert abs(sums[1] - 0.0) < 1e-6
