"""jsonb and partial indexes

Revision ID: 0008_jsonb_and_partial_indexes
Revises: 0007_perf_indexes
Create Date: 2026-02-02
"""

from __future__ import annotations

from alembic import op

revision = "0008_jsonb_and_partial_indexes"
down_revision = "0007_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fast JSONB lookups on asset.props (upstream/downstream node ids)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_asset_props_upstream_node "
        "ON asset ((props->>'upstream_node_id'));"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_asset_props_downstream_node "
        "ON asset ((props->>'downstream_node_id'));"
    )

    # Speed default telemetry queries where scenario_id IS NULL
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_telemetry_observation_asset_metric_ts_default "
        "ON telemetry_observation (asset_id, metric, ts DESC) "
        "WHERE scenario_id IS NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_telemetry_observation_asset_metric_ts_default;")
    op.execute("DROP INDEX IF EXISTS ix_asset_props_downstream_node;")
    op.execute("DROP INDEX IF EXISTS ix_asset_props_upstream_node;")
