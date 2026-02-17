"""add asset tags

Revision ID: 0004_asset_tag
Revises: 0003_timescale_policies
Create Date: 2026-01-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_asset_tag"
down_revision = "0003_timescale_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_tag",
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("asset.asset_id"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("asset_id", "key", "value"),
    )
    op.create_index("ix_asset_tag_asset_id", "asset_tag", ["asset_id"])
    op.create_index("ix_asset_tag_key_value", "asset_tag", ["key", "value"])


def downgrade() -> None:
    op.drop_index("ix_asset_tag_key_value", table_name="asset_tag")
    op.drop_index("ix_asset_tag_asset_id", table_name="asset_tag")
    op.drop_table("asset_tag")
