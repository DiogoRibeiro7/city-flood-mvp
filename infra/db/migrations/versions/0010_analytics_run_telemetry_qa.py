"""analytics run + telemetry QA + export trace

Revision ID: 0010_analytics_run_telemetry_qa
Revises: 0009_concurrent_indexes
Create Date: 2026-02-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_analytics_run_telemetry_qa"
down_revision = "0009_concurrent_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("export_job", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_job", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_job", sa.Column("row_count", sa.Integer(), nullable=True))

    op.create_table(
        "analytics_run",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=False, index=True),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, index=True),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "telemetry_qa_daily",
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("metric", sa.String(length=64), primary_key=True),
        sa.Column("assets", sa.Integer(), nullable=False),
        sa.Column("buckets_expected", sa.Integer(), nullable=False),
        sa.Column("buckets_present", sa.Integer(), nullable=False),
        sa.Column("gaps", sa.Integer(), nullable=False),
        sa.Column("suspect_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_telemetry_qa_daily_city_metric_day",
        "telemetry_qa_daily",
        ["city_id", "metric", "day"],
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_qa_daily_city_metric_day", table_name="telemetry_qa_daily")
    op.drop_table("telemetry_qa_daily")
    op.drop_table("analytics_run")
    op.drop_column("export_job", "row_count")
    op.drop_column("export_job", "completed_at")
    op.drop_column("export_job", "started_at")
