from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from geoalchemy2.elements import WKTElement
from shapely.geometry import LineString, Point, Polygon


@dataclass(frozen=True)
class GeneratedCity:
    city_id: str
    city_polygon: Polygon
    river: LineString
    nodes: list[Point]
    pipes: list[LineString]
    rain_gauges: list[Point]
    river_gauges: list[Point]


def _mk_bbox_polygon(center_lon: float, center_lat: float, half_size_deg: float) -> Polygon:
    return Polygon(
        [
            (center_lon - half_size_deg, center_lat - half_size_deg),
            (center_lon + half_size_deg, center_lat - half_size_deg),
            (center_lon + half_size_deg, center_lat + half_size_deg),
            (center_lon - half_size_deg, center_lat + half_size_deg),
        ]
    )


def generate_city_network(
    city_id: str,
    center_lon: float = -8.61,
    center_lat: float = 41.15,
    half_size_deg: float = 0.08,
    grid_n: int = 20,
) -> GeneratedCity:
    """Generate a synthetic city drainage network.

    Design goals:
    - enough geometry to drive a real map UI
    - deterministic-ish structure (grid) but not too artificial
    """
    if grid_n < 5:
        raise ValueError("grid_n must be >= 5")

    city_poly = _mk_bbox_polygon(center_lon, center_lat, half_size_deg)

    # river crossing the city (diagonal-ish)
    river = LineString(
        [
            (center_lon - half_size_deg * 1.2, center_lat + half_size_deg * 0.8),
            (center_lon + half_size_deg * 1.2, center_lat - half_size_deg * 0.7),
        ]
    )

    # nodes on a grid
    nodes: list[Point] = []
    lon0 = center_lon - half_size_deg
    lat0 = center_lat - half_size_deg
    step = (2 * half_size_deg) / (grid_n - 1)
    for i in range(grid_n):
        for j in range(grid_n):
            nodes.append(Point(lon0 + i * step, lat0 + j * step))

    # pipes connect to right and up (grid edges)
    pipes: list[LineString] = []
    def idx(i: int, j: int) -> int:
        return i * grid_n + j

    for i in range(grid_n):
        for j in range(grid_n):
            p = nodes[idx(i, j)]
            if i + 1 < grid_n:
                pipes.append(LineString([p, nodes[idx(i + 1, j)]]))
            if j + 1 < grid_n:
                pipes.append(LineString([p, nodes[idx(i, j + 1)]]))

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
    )


def to_wkt(geom: Any, srid: int = 4326) -> WKTElement:
    """Convert shapely geometry to a GeoAlchemy WKTElement."""
    return WKTElement(geom.wkt, srid=srid)
