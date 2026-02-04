"""rebuild selected indexes concurrently

Revision ID: 0009_concurrent_indexes
Revises: 0008_jsonb_and_partial_indexes
Create Date: 2026-02-02
"""

from __future__ import annotations

from alembic import op

revision = "0009_concurrent_indexes"
down_revision = "0008_jsonb_and_partial_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rebuild heavier indexes concurrently to avoid table locks in production.
    # Note: CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX IF EXISTS ix_hotspot_city_metric_score;")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_hotspot_city_metric_score "
            "ON analytics_hotspot_daily (city_id, metric, score DESC);"
        )

        op.execute("DROP INDEX IF EXISTS ix_analytics_event_city_type_start_ts;")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_analytics_event_city_type_start_ts "
            "ON analytics_event (city_id, event_type, start_ts);"
        )

        op.execute(
            "DROP INDEX IF EXISTS ix_telemetry_observation_asset_metric_ts_default;"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS "
            "ix_telemetry_observation_asset_metric_ts_default "
            "ON telemetry_observation (asset_id, metric, ts DESC) "
            "WHERE scenario_id IS NULL;"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX IF EXISTS ix_telemetry_observation_asset_metric_ts_default;")
        op.execute("DROP INDEX IF EXISTS ix_analytics_event_city_type_start_ts;")
        op.execute("DROP INDEX IF EXISTS ix_hotspot_city_metric_score;")
