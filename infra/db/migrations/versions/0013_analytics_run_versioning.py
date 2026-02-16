"""analytics run versioning

Revision ID: 0013_analytics_run_versioning
Revises: 0012_job_queue
Create Date: 2026-02-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_analytics_run_versioning"
down_revision = "0012_job_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytics_event",
        sa.Column("run_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analytics_hotspot_daily",
        sa.Column("run_id", sa.String(length=64), nullable=True),
    )

    # backfill run_id from latest run per city
    op.execute(
        """
        WITH latest_runs AS (
            SELECT DISTINCT ON (city_id) city_id, run_id
            FROM analytics_run
            ORDER BY city_id, created_at DESC
        )
        UPDATE analytics_event e
        SET run_id = lr.run_id
        FROM latest_runs lr
        WHERE e.city_id = lr.city_id AND e.run_id IS NULL;
        """
    )
    op.execute(
        """
        WITH latest_runs AS (
            SELECT DISTINCT ON (city_id) city_id, run_id
            FROM analytics_run
            ORDER BY city_id, created_at DESC
        )
        UPDATE analytics_hotspot_daily h
        SET run_id = lr.run_id
        FROM latest_runs lr
        WHERE h.city_id = lr.city_id AND h.run_id IS NULL;
        """
    )

    op.alter_column("analytics_event", "run_id", nullable=False)
    op.alter_column("analytics_hotspot_daily", "run_id", nullable=False)

    op.create_foreign_key(
        "fk_analytics_event_run_id",
        "analytics_event",
        "analytics_run",
        ["run_id"],
        ["run_id"],
    )
    op.create_foreign_key(
        "fk_analytics_hotspot_run_id",
        "analytics_hotspot_daily",
        "analytics_run",
        ["run_id"],
        ["run_id"],
    )

    op.drop_constraint("analytics_hotspot_daily_pkey", "analytics_hotspot_daily", type_="primary")
    op.create_primary_key(
        "analytics_hotspot_daily_pkey",
        "analytics_hotspot_daily",
        ["run_id", "city_id", "day", "metric", "asset_id"],
    )

    op.create_index(
        "ix_analytics_event_run_id",
        "analytics_event",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_hotspot_run_id",
        "analytics_hotspot_daily",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_hotspot_run_metric_score",
        "analytics_hotspot_daily",
        ["run_id", "metric", "score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_hotspot_run_metric_score", table_name="analytics_hotspot_daily")
    op.drop_index("ix_analytics_hotspot_run_id", table_name="analytics_hotspot_daily")
    op.drop_index("ix_analytics_event_run_id", table_name="analytics_event")
    op.drop_constraint("analytics_hotspot_daily_pkey", "analytics_hotspot_daily", type_="primary")
    op.create_primary_key(
        "analytics_hotspot_daily_pkey",
        "analytics_hotspot_daily",
        ["city_id", "day", "metric", "asset_id"],
    )
    op.drop_constraint("fk_analytics_hotspot_run_id", "analytics_hotspot_daily", type_="foreignkey")
    op.drop_constraint("fk_analytics_event_run_id", "analytics_event", type_="foreignkey")
    op.drop_column("analytics_hotspot_daily", "run_id")
    op.drop_column("analytics_event", "run_id")
