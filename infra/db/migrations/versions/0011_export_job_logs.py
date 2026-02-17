"""export job logs

Revision ID: 0011_export_job_logs
Revises: 0010_analytics_run_telemetry_qa
Create Date: 2026-02-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_export_job_logs"
down_revision = "0010_analytics_run_telemetry_qa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_job_log",
        sa.Column("log_id", sa.String(length=64), primary_key=True),
        sa.Column("job_id", sa.String(length=64), sa.ForeignKey("export_job.job_id"), nullable=False, index=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_export_job_log_job_id_created_at",
        "export_job_log",
        ["job_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_export_job_log_job_id_created_at", table_name="export_job_log")
    op.drop_table("export_job_log")
