from __future__ import annotations

import datetime as dt

from floodmvp.generators.city_network import generate_city_network
from floodmvp.generators.telemetry import (
    generate_pipe_hydraulics_series,
    generate_rain_series,
    generate_river_level_series,
)


def test_generate_city_network_counts() -> None:
    net = generate_city_network(city_id="c", grid_n=10, seed=123)
    assert len(net.nodes) == 100
    # grid edges: horizontal 9*10 + vertical 9*10 = 180 + outfall connections (2 per outfall)
    assert len(net.pipes) == 186
    assert len(net.rain_gauges) == 2
    assert len(net.river_gauges) == 2
    assert len(net.outfalls) == 3


def test_generate_city_network_deterministic_seed() -> None:
    net_a = generate_city_network(city_id="c", grid_n=8, seed=99)
    net_b = generate_city_network(city_id="c", grid_n=8, seed=99)
    assert round(net_a.nodes[0].x, 6) == round(net_b.nodes[0].x, 6)
    assert round(net_a.nodes[0].y, 6) == round(net_b.nodes[0].y, 6)
    assert round(net_a.pipes[0].length_m, 3) == round(net_b.pipes[0].length_m, 3)


def test_generate_rain_series_has_monotonic_ts() -> None:
    start = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    end = start + dt.timedelta(hours=1)
    s = generate_rain_series("a", start, end, freq="1min", scenario="normal", seed=5)
    ts = s.df["ts"].tolist()
    assert ts == sorted(ts)
    assert len(ts) == 60


def test_generate_pipe_hydraulics_deterministic_seed() -> None:
    start = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    end = start + dt.timedelta(hours=1)
    rain_a = generate_rain_series("rg", start, end, freq="1min", scenario="normal", seed=1)
    river_a = generate_river_level_series("rv", rain_a, scenario="normal", seed=2)
    series_a = generate_pipe_hydraulics_series(
        "p1",
        rain_a,
        river_a,
        diameter_m=0.8,
        capacity_est_m3s=0.2,
        sensitivity=1.1,
        scenario="normal",
        seed=3,
    )
    rain_b = generate_rain_series("rg", start, end, freq="1min", scenario="normal", seed=1)
    river_b = generate_river_level_series("rv", rain_b, scenario="normal", seed=2)
    series_b = generate_pipe_hydraulics_series(
        "p1",
        rain_b,
        river_b,
        diameter_m=0.8,
        capacity_est_m3s=0.2,
        sensitivity=1.1,
        scenario="normal",
        seed=3,
    )
    depth_vals_a = series_a[0].df["value"].tolist()[:3]
    flow_vals_a = series_a[2].df["value"].tolist()[:3]
    depth_vals_b = series_b[0].df["value"].tolist()[:3]
    flow_vals_b = series_b[2].df["value"].tolist()[:3]
    assert [round(v, 6) for v in depth_vals_a] == [round(v, 6) for v in depth_vals_b]
    assert [round(v, 6) for v in flow_vals_a] == [round(v, 6) for v in flow_vals_b]
