from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


AssetType = Literal[
    "river_segment",
    "node",
    "pipe",
    "outfall",
    "rain_gauge",
    "river_gauge",
    "tank",
    "pump",
]


class CityOut(BaseModel):
    city_id: str
    name: str
    country: str


class AssetOut(BaseModel):
    asset_id: str
    city_id: str
    asset_type: AssetType
    name: str
    geom_geojson: dict | None = None
    props: dict = Field(default_factory=dict)


class Paging(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class ListResponse(BaseModel):
    data: list
    paging: Paging = Field(default_factory=Paging)


class ObservationOut(BaseModel):
    ts: dt.datetime
    value: float


class ObservationsOut(BaseModel):
    metric: str
    series: list[ObservationOut]
    request_id: str


class CityStatusOut(BaseModel):
    city_id: str
    risk: str
    active_events: int
    hotspots: int
    updated_at: dt.datetime
    request_id: str


class HotspotOut(BaseModel):
    asset_id: str
    score: float
    details: dict = Field(default_factory=dict)


class EventOut(BaseModel):
    event_id: str
    event_type: str
    severity: int
    start_ts: dt.datetime
    end_ts: dt.datetime
    asset_ids: list[str]
    summary: str
