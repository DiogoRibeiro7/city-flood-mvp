from __future__ import annotations

import datetime as dt
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import ARRAY, JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class City(Base):
    __tablename__ = "city"

    city_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    geom = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Asset(Base):
    __tablename__ = "asset"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    geom = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True)
    props: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AssetTag(Base):
    __tablename__ = "asset_tag"

    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("asset.asset_id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class TelemetryObservation(Base):
    __tablename__ = "telemetry_observation"

    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("asset.asset_id"), primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality_flag: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="synthetic")
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    scenario_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("scenario_run.scenario_id"), nullable=True, index=True)


class IngestIdempotency(Base):
    __tablename__ = "ingest_idempotency"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("asset.asset_id"), index=True)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class ScenarioRun(Base):
    __tablename__ = "scenario_run"

    scenario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class ExportJob(Base):
    __tablename__ = "export_job"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    query: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", server_onupdate="now()"
    )


class ExportJobLog(Base):
    __tablename__ = "export_job_log"

    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("export_job.job_id"), index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class JobQueue(Base):
    __tablename__ = "job_queue"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="queued")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    scheduled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", server_onupdate="now()"
    )


class AnalyticsEvent(Base):
    __tablename__ = "analytics_event"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("analytics_run.run_id"), index=True)
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    start_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AnalyticsHotspotDaily(Base):
    __tablename__ = "analytics_hotspot_daily"

    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_run.run_id"), primary_key=True
    )
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("asset.asset_id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AssetStatusLatest(Base):
    __tablename__ = "asset_status_latest"

    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("asset.asset_id"), primary_key=True)
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AnalyticsRun(Base):
    __tablename__ = "analytics_run"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), index=True)
    start_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", server_onupdate="now()"
    )


class TelemetryQaDaily(Base):
    __tablename__ = "telemetry_qa_daily"

    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    assets: Mapped[int] = mapped_column(Integer, nullable=False)
    buckets_expected: Mapped[int] = mapped_column(Integer, nullable=False)
    buckets_present: Mapped[int] = mapped_column(Integer, nullable=False)
    gaps: Mapped[int] = mapped_column(Integer, nullable=False)
    suspect_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AnalyticsThresholdOverride(Base):
    __tablename__ = "analytics_threshold_override"

    override_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), index=True)
    season: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
