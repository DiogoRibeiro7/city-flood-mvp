"""performance indexes

Revision ID: 0007_perf_indexes
Revises: 0006_export_job
Create Date: 2026-02-02
"""

from __future__ import annotations

from alembic import op

revision = "0007_perf_indexes"
down_revision = "0006_export_job"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Analytics events: common filters by city/time and optional type
    op.create_index(
        "ix_analytics_event_city_start_ts",
        "analytics_event",
        ["city_id", "start_ts"],
    )
    op.create_index(
        "ix_analytics_event_city_type_start_ts",
        "analytics_event",
        ["city_id", "event_type", "start_ts"],
    )

    # Hotspots: filter by city+metric and order by score
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_hotspot_city_metric_score "
        "ON analytics_hotspot_daily (city_id, metric, score DESC);"
    )

    # Asset status: filter by city/status for counts
    op.create_index(
        "ix_asset_status_city_status",
        "asset_status_latest",
        ["city_id", "status"],
    )

    # Telemetry: speed metric discovery per asset/scenario
    op.create_index(
        "ix_telemetry_observation_asset_scenario_metric",
        "telemetry_observation",
        ["asset_id", "scenario_id", "metric"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telemetry_observation_asset_scenario_metric",
        table_name="telemetry_observation",
    )
    op.drop_index("ix_asset_status_city_status", table_name="asset_status_latest")
    op.execute("DROP INDEX IF EXISTS ix_hotspot_city_metric_score;")
    op.drop_index("ix_analytics_event_city_type_start_ts", table_name="analytics_event")
    op.drop_index("ix_analytics_event_city_start_ts", table_name="analytics_event")
