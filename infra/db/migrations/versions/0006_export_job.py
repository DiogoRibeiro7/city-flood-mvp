"""add export job

Revision ID: 0006_export_job
Revises: 0005_scenario_run
Create Date: 2026-01-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_export_job"
down_revision = "0005_scenario_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_job",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("job_type", sa.String(length=32), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, index=True),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("query", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("export_job")
