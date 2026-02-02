from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from geoalchemy2.elements import WKTElement
from shapely.geometry import LineString, Point, Polygon


@dataclass(frozen=True)
class GeneratedCity:
    city_id: str
    city_polygon: Polygon
    river: LineString
    nodes: list[Point]
    pipes: list["PipeSegment"]
    rain_gauges: list[Point]
    river_gauges: list[Point]
    outfalls: list[Point]


@dataclass(frozen=True)
class PipeSegment:
    line: LineString
    upstream_idx: int
    downstream_idx: int
    downstream_kind: Literal["node", "outfall"]
    length_m: float
    diameter_m: float
    slope: float
    capacity_est_m3s: float


def _mk_bbox_polygon(center_lon: float, center_lat: float, half_size_deg: float) -> Polygon:
    return Polygon(
        [
            (center_lon - half_size_deg, center_lat - half_size_deg),
            (center_lon + half_size_deg, center_lat - half_size_deg),
            (center_lon + half_size_deg, center_lat + half_size_deg),
            (center_lon - half_size_deg, center_lat + half_size_deg),
        ]
    )


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _line_length_m(line: LineString) -> float:
    coords = list(line.coords)
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        total += _haversine_m(lon1, lat1, lon2, lat2)
    return total


def _pipe_capacity_m3s(diameter_m: float, slope: float, manning_n: float = 0.013) -> float:
    # Manning full-pipe estimate
    radius = diameter_m / 2.0
    area = math.pi * radius * radius
    hydraulic_radius = diameter_m / 4.0
    return (1.0 / manning_n) * area * (hydraulic_radius ** (2.0 / 3.0)) * math.sqrt(slope)


def generate_city_network(
    city_id: str,
    center_lon: float = -8.61,
    center_lat: float = 41.15,
    half_size_deg: float = 0.08,
    grid_n: int = 20,
    jitter_ratio: float = 0.18,
    outfall_count: int = 3,
    seed: int = 7,
) -> GeneratedCity:
    """Generate a synthetic city drainage network.

    Design goals:
    - enough geometry to drive a real map UI
    - deterministic-ish structure (grid) but not too artificial
    """
    if grid_n < 5:
        raise ValueError("grid_n must be >= 5")

    rng = np.random.default_rng(seed)
    city_poly = _mk_bbox_polygon(center_lon, center_lat, half_size_deg)

    # river crossing the city (diagonal-ish)
    river_start = (center_lon - half_size_deg * 1.25, center_lat + half_size_deg * 0.9)
    river_end = (center_lon + half_size_deg * 1.2, center_lat - half_size_deg * 0.8)
    mid_offset_lon = float(rng.normal(0, half_size_deg * 0.12))
    mid_offset_lat = float(rng.normal(0, half_size_deg * 0.12))
    river_mid = (center_lon + mid_offset_lon, center_lat + mid_offset_lat)
    river = LineString([river_start, river_mid, river_end])

    # nodes on a grid with jitter
    nodes: list[Point] = []
    lon0 = center_lon - half_size_deg
    lat0 = center_lat - half_size_deg
    step = (2 * half_size_deg) / (grid_n - 1)
    for i in range(grid_n):
        for j in range(grid_n):
            jitter_lon = float(rng.normal(0, step * jitter_ratio))
            jitter_lat = float(rng.normal(0, step * jitter_ratio))
            lon = lon0 + i * step + jitter_lon
            lat = lat0 + j * step + jitter_lat
            lon = min(center_lon + half_size_deg, max(center_lon - half_size_deg, lon))
            lat = min(center_lat + half_size_deg, max(center_lat - half_size_deg, lat))
            nodes.append(Point(lon, lat))

    # outfalls along the river
    outfalls: list[Point] = []
    if outfall_count < 1:
        outfall_count = 1
    for t in np.linspace(0.15, 0.85, outfall_count):
        t_jitter = float(np.clip(t + rng.normal(0, 0.03), 0.05, 0.95))
        outfalls.append(Point(river.interpolate(t_jitter, normalized=True)))

    # elevation field for flow direction + slopes
    river_cache: dict[int, tuple[float, float, float]] = {}
    def node_elevation(idx: int) -> float:
        if idx in river_cache:
            return river_cache[idx][2]
        p = nodes[idx]
        proj = river.project(p)
        near = river.interpolate(proj)
        dist_m = _haversine_m(p.x, p.y, near.x, near.y)
        elev = (
            12.0
            + 0.008 * dist_m
            + 18.0 * (p.y - center_lat)
            - 12.0 * (p.x - center_lon)
            + float(rng.normal(0, 1.2))
        )
        river_cache[idx] = (near.x, near.y, elev)
        return elev

    # pipes connect to right and up (grid edges), with directed flow
    pipes: list[PipeSegment] = []
    def idx(i: int, j: int) -> int:
        return i * grid_n + j

    for i in range(grid_n):
        for j in range(grid_n):
            p = nodes[idx(i, j)]
            if i + 1 < grid_n:
                a = idx(i, j)
                b = idx(i + 1, j)
                pa = nodes[a]
                pb = nodes[b]
                line = LineString([pa, pb])
                length_m = max(_line_length_m(line), 1.0)
                elev_a = node_elevation(a)
                elev_b = node_elevation(b)
                if elev_a >= elev_b:
                    upstream_idx, downstream_idx = a, b
                    slope = max((elev_a - elev_b) / length_m, 0.0002)
                else:
                    upstream_idx, downstream_idx = b, a
                    slope = max((elev_b - elev_a) / length_m, 0.0002)
                mid = line.interpolate(0.5, normalized=True)
                proj = river.project(mid)
                near = river.interpolate(proj)
                dist_mid = _haversine_m(mid.x, mid.y, near.x, near.y)
                diameter_m = float(
                    np.clip(0.35 + 0.9 * math.exp(-dist_mid / 700.0) + rng.uniform(0.0, 0.1), 0.3, 1.6)
                )
                capacity = _pipe_capacity_m3s(diameter_m, slope)
                pipes.append(
                    PipeSegment(
                        line=line,
                        upstream_idx=upstream_idx,
                        downstream_idx=downstream_idx,
                        downstream_kind="node",
                        length_m=length_m,
                        diameter_m=diameter_m,
                        slope=slope,
                        capacity_est_m3s=capacity,
                    )
                )
            if j + 1 < grid_n:
                a = idx(i, j)
                b = idx(i, j + 1)
                pa = nodes[a]
                pb = nodes[b]
                line = LineString([pa, pb])
                length_m = max(_line_length_m(line), 1.0)
                elev_a = node_elevation(a)
                elev_b = node_elevation(b)
                if elev_a >= elev_b:
                    upstream_idx, downstream_idx = a, b
                    slope = max((elev_a - elev_b) / length_m, 0.0002)
                else:
                    upstream_idx, downstream_idx = b, a
                    slope = max((elev_b - elev_a) / length_m, 0.0002)
                mid = line.interpolate(0.5, normalized=True)
                proj = river.project(mid)
                near = river.interpolate(proj)
                dist_mid = _haversine_m(mid.x, mid.y, near.x, near.y)
                diameter_m = float(
                    np.clip(0.35 + 0.9 * math.exp(-dist_mid / 700.0) + rng.uniform(0.0, 0.1), 0.3, 1.6)
                )
                capacity = _pipe_capacity_m3s(diameter_m, slope)
                pipes.append(
                    PipeSegment(
                        line=line,
                        upstream_idx=upstream_idx,
                        downstream_idx=downstream_idx,
                        downstream_kind="node",
                        length_m=length_m,
                        diameter_m=diameter_m,
                        slope=slope,
                        capacity_est_m3s=capacity,
                    )
                )

    # connect nearby nodes to outfalls
    for outfall_idx, outfall in enumerate(outfalls):
        distances: list[tuple[float, int]] = []
        for i, p in enumerate(nodes):
            distances.append((_haversine_m(p.x, p.y, outfall.x, outfall.y), i))
        distances.sort(key=lambda x: x[0])
        for _, node_idx in distances[:2]:
            node = nodes[node_idx]
            line = LineString([node, outfall])
            length_m = max(_line_length_m(line), 1.0)
            elev_up = node_elevation(node_idx)
            elev_down = 5.0
            slope = max((elev_up - elev_down) / length_m, 0.0004)
            diameter_m = float(np.clip(0.5 + rng.uniform(0.1, 0.5), 0.4, 1.8))
            capacity = _pipe_capacity_m3s(diameter_m, slope)
            pipes.append(
                PipeSegment(
                    line=line,
                    upstream_idx=node_idx,
                    downstream_idx=outfall_idx,
                    downstream_kind="outfall",
                    length_m=length_m,
                    diameter_m=diameter_m,
                    slope=slope,
                    capacity_est_m3s=capacity,
                )
            )

    # gauges
    rain_gauges = [
        Point(center_lon - half_size_deg * 0.5, center_lat + half_size_deg * 0.4),
        Point(center_lon + half_size_deg * 0.4, center_lat - half_size_deg * 0.2),
    ]
    river_gauges = [
        Point(river.interpolate(0.3, normalized=True)),
        Point(river.interpolate(0.7, normalized=True)),
    ]

    return GeneratedCity(
        city_id=city_id,
        city_polygon=city_poly,
        river=river,
        nodes=nodes,
        pipes=pipes,
        rain_gauges=rain_gauges,
        river_gauges=river_gauges,
        outfalls=outfalls,
    )


def to_wkt(geom: Any, srid: int = 4326) -> WKTElement:
    """Convert shapely geometry to a GeoAlchemy WKTElement."""
    return WKTElement(geom.wkt, srid=srid)
