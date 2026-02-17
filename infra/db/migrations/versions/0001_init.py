"""init schema

Revision ID: 0001_init
Revises:
Create Date: 2026-01-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # --- core tables ---
    op.create_table(
        "city",
        sa.Column("city_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POLYGON", srid=4326), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "asset",
        sa.Column("asset_id", sa.String(length=64), primary_key=True),
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=False, index=True),
        sa.Column("asset_type", sa.String(length=40), nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True),
        sa.Column("props", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_asset_city_type", "asset", ["city_id", "asset_type"])
    op.execute("CREATE INDEX IF NOT EXISTS ix_asset_geom_gist ON asset USING GIST (geom);")

    op.create_table(
        "telemetry_observation",
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("asset.asset_id"), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("quality_flag", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="synthetic"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("asset_id", "metric", "ts"),
    )

    # Convert telemetry_observation into a hypertable (Timescale)
    op.execute("SELECT create_hypertable('telemetry_observation', 'ts', if_not_exists => TRUE);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_telemetry_observation_asset_ts "
        "ON telemetry_observation (asset_id, ts DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_telemetry_observation_ts_brin "
        "ON telemetry_observation USING BRIN (ts);"
    )

    op.create_table(
        "analytics_event",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=40), nullable=False, index=True),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_ids", sa.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "analytics_hotspot_daily",
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=False, index=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("asset.asset_id"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("city_id", "day", "metric", "asset_id"),
    )

    op.create_table(
        "asset_status_latest",
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("asset.asset_id"), primary_key=True),
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_telemetry_observation_ts_brin;")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_observation_asset_ts;")
    op.drop_table("asset_status_latest")
    op.drop_table("analytics_hotspot_daily")
    op.drop_table("analytics_event")
    op.drop_table("telemetry_observation")
    op.execute("DROP INDEX IF EXISTS ix_asset_geom_gist;")
    op.drop_index("ix_asset_city_type", table_name="asset")
    op.drop_table("asset")
    op.drop_table("city")
