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
    value: float | None


class ObservationsOut(BaseModel):
    metric: str
    series: list[ObservationOut]
    request_id: str


class ScenarioRunOut(BaseModel):
    scenario_id: str
    name: str
    start_ts: dt.datetime
    end_ts: dt.datetime


class TelemetryQaOut(BaseModel):
    city_id: str
    day: dt.date
    metric: str
    assets: int
    buckets_expected: int
    buckets_present: int
    gaps: int
    suspect_count: int


class ExportJobQuery(BaseModel):
    asset_ids: list[str]
    city_id: str | None = None
    asset_type: AssetType | None = None
    metric: str
    from_ts: dt.datetime = Field(..., alias="from")
    to_ts: dt.datetime = Field(..., alias="to")
    granularity: str = "5m"
    agg: str = "avg"


class ExportJobRequest(BaseModel):
    type: Literal["export_csv"]
    query: ExportJobQuery


class ExportJobLogOut(BaseModel):
    ts: dt.datetime
    level: str
    message: str
    details: dict = Field(default_factory=dict)


class ExportJobOut(BaseModel):
    job_id: str
    job_type: str
    status: str
    progress: float
    file_path: str | None = None
    error_message: str | None = None
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    row_count: int | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    logs: list[ExportJobLogOut] = Field(default_factory=list)


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
    confidence: float
    details: dict = Field(default_factory=dict)


class CitySummaryOut(BaseModel):
    city_id: str
    now: dt.datetime
    rain_mmph: float
    river_level_m: float
    status_counts: dict


class EventOut(BaseModel):
    event_id: str
    event_type: str
    severity: int
    confidence: float
    start_ts: dt.datetime
    end_ts: dt.datetime
    asset_ids: list[str]
    summary: str


class AnalyticsRunOut(BaseModel):
    run_id: str
    city_id: str
    start_ts: dt.datetime
    end_ts: dt.datetime
    status: str
    version: str
    params: dict
    metrics: dict
    created_at: dt.datetime
    updated_at: dt.datetime


class AnalyticsEventDiffSummary(BaseModel):
    base_count: int
    compare_count: int
    added: list[EventOut] = Field(default_factory=list)
    removed: list[EventOut] = Field(default_factory=list)


class HotspotDiffItem(BaseModel):
    asset_id: str
    metric: str
    day: dt.date
    score_before: float | None = None
    score_after: float | None = None
    delta: float | None = None


class AnalyticsHotspotDiffSummary(BaseModel):
    base_count: int
    compare_count: int
    changed: list[HotspotDiffItem] = Field(default_factory=list)
    added: list[HotspotDiffItem] = Field(default_factory=list)
    removed: list[HotspotDiffItem] = Field(default_factory=list)


class AnalyticsRunDiffOut(BaseModel):
    city_id: str
    base_run_id: str
    compare_run_id: str
    base_version: str
    compare_version: str
    metrics_delta: dict
    events: AnalyticsEventDiffSummary
    hotspots: AnalyticsHotspotDiffSummary


class CalibrationThresholds(BaseModel):
    rain_event_threshold_mmph: float | None = None
    rain_event_min_duration_minutes: int | None = None
    overflow_fill_threshold: float | None = None
    overflow_min_duration_minutes: int | None = None
    risk_fill_watch: float | None = None
    risk_fill_warning: float | None = None


class CalibrationRecommendationOut(BaseModel):
    city_id: str
    from_ts: dt.datetime
    to_ts: dt.datetime
    seasonality: str
    thresholds: dict[str, CalibrationThresholds]


class CalibrationOverrideIn(BaseModel):
    city_id: str
    season: str = "all"
    thresholds: CalibrationThresholds
    notes: str | None = None


class CalibrationOverrideOut(BaseModel):
    override_id: str
    city_id: str
    season: str
    thresholds: CalibrationThresholds
    notes: str | None = None
    created_at: dt.datetime


class IngestEventIn(BaseModel):
    ts: dt.datetime
    type: str
    value: float
    quality_flag: str = "ok"


class IngestRequest(BaseModel):
    device_id: str
    sent_at: dt.datetime
    events: list[IngestEventIn]


class IngestEventResult(BaseModel):
    ts: dt.datetime
    type: str
    status: Literal["accepted", "rejected"]
    reason: str | None = None


class IngestResponse(BaseModel):
    device_id: str
    received: int
    accepted: int
    rejected: int
    results: list[IngestEventResult]


class JobQueueOut(BaseModel):
    job_id: str
    job_type: str
    status: str
    payload: dict
    attempts: int
    max_attempts: int
    scheduled_at: dt.datetime
    locked_at: dt.datetime | None = None
    locked_by: str | None = None
    last_error: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
