from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, JSON, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from geoalchemy2 import Geometry


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
    props: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
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


class AnalyticsEvent(Base):
    __tablename__ = "analytics_event"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AnalyticsHotspotDaily(Base):
    __tablename__ = "analytics_hotspot_daily"

    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("asset.asset_id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AssetStatusLatest(Base):
    __tablename__ = "asset_status_latest"

    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("asset.asset_id"), primary_key=True)
    city_id: Mapped[str] = mapped_column(String(64), ForeignKey("city.city_id"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
