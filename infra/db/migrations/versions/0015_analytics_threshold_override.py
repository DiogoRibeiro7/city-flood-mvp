"""analytics threshold override

Revision ID: 0015_analytics_threshold_override
Revises: 0014_analytics_confidence
Create Date: 2026-02-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_analytics_threshold_override"
down_revision = "0014_analytics_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_threshold_override",
        sa.Column("override_id", sa.String(length=64), primary_key=True),
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=False, index=True),
        sa.Column("season", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("thresholds", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_threshold_override_city_season_created",
        "analytics_threshold_override",
        ["city_id", "season", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_threshold_override_city_season_created", table_name="analytics_threshold_override")
    op.drop_table("analytics_threshold_override")
