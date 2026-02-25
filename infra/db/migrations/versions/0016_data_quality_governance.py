"""data quality governance"

Revision ID: 0016_data_quality_governance
Revises: 0015_analytics_threshold_override
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_data_quality_governance"
down_revision = "0015_analytics_threshold_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("city", sa.Column("telemetry_retention_days", sa.Integer(), nullable=True))
    op.add_column("city", sa.Column("compliance_tags", sa.ARRAY(sa.String(length=64)), nullable=True))
    op.add_column("city", sa.Column("retention_policy", sa.JSON(), nullable=True))

    op.create_table(
        "dataset_import",
        sa.Column("import_id", sa.String(length=64), primary_key=True),
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=True, index=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_uri", sa.String(length=512), nullable=True),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("dataset_version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="validated"),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_report", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_dataset_import_city_created",
        "dataset_import",
        ["city_id", "created_at"],
        unique=False,
    )

    op.add_column(
        "telemetry_observation",
        sa.Column("import_id", sa.String(length=64), sa.ForeignKey("dataset_import.import_id"), nullable=True),
    )
    op.add_column(
        "telemetry_observation",
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "telemetry_observation",
        sa.Column("source_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "telemetry_observation",
        sa.Column(
            "lineage",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_telemetry_observation_import_id",
        "telemetry_observation",
        ["import_id"],
        unique=False,
    )

    op.add_column(
        "telemetry_qa_daily",
        sa.Column("outlier_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "telemetry_qa_daily",
        sa.Column("drift_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("telemetry_qa_daily", "drift_count")
    op.drop_column("telemetry_qa_daily", "outlier_count")

    op.drop_index("ix_telemetry_observation_import_id", table_name="telemetry_observation")
    op.drop_column("telemetry_observation", "lineage")
    op.drop_column("telemetry_observation", "source_id")
    op.drop_column("telemetry_observation", "source_type")
    op.drop_column("telemetry_observation", "import_id")

    op.drop_index("ix_dataset_import_city_created", table_name="dataset_import")
    op.drop_table("dataset_import")

    op.drop_column("city", "retention_policy")
    op.drop_column("city", "compliance_tags")
    op.drop_column("city", "telemetry_retention_days")