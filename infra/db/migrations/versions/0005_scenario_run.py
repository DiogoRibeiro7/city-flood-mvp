"""add scenario runs

Revision ID: 0005_scenario_run
Revises: 0004_asset_tag
Create Date: 2026-01-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_scenario_run"
down_revision = "0004_asset_tag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_run",
        sa.Column("scenario_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, index=True),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.add_column(
        "telemetry_observation",
        sa.Column("scenario_id", sa.String(length=64), sa.ForeignKey("scenario_run.scenario_id"), nullable=True),
    )
    op.create_index("ix_telemetry_observation_scenario_id", "telemetry_observation", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_telemetry_observation_scenario_id", table_name="telemetry_observation")
    op.drop_column("telemetry_observation", "scenario_id")
    op.drop_table("scenario_run")
