"""analytics confidence

Revision ID: 0014_analytics_confidence
Revises: 0013_analytics_run_versioning
Create Date: 2026-02-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_analytics_confidence"
down_revision = "0013_analytics_run_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytics_event",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "analytics_hotspot_daily",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
    )

    op.alter_column("analytics_event", "confidence", server_default=None)
    op.alter_column("analytics_hotspot_daily", "confidence", server_default=None)


def downgrade() -> None:
    op.drop_column("analytics_hotspot_daily", "confidence")
    op.drop_column("analytics_event", "confidence")
