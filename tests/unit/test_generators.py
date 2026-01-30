from __future__ import annotations

import datetime as dt

from floodmvp.generators.city_network import generate_city_network
from floodmvp.generators.telemetry import generate_rain_series


def test_generate_city_network_counts() -> None:
    net = generate_city_network(city_id="c", grid_n=10)
    assert len(net.nodes) == 100
    # grid edges: horizontal 9*10 + vertical 9*10 = 180
    assert len(net.pipes) == 180
    assert len(net.rain_gauges) == 2
    assert len(net.river_gauges) == 2


def test_generate_rain_series_has_monotonic_ts() -> None:
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(hours=1)
    s = generate_rain_series("a", start, end, freq="1min")
    ts = s.df["ts"].tolist()
    assert ts == sorted(ts)
    assert len(ts) == 60
