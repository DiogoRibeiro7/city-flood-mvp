"""add ingest idempotency

Revision ID: 0002_ingest_idempotency
Revises: 0001_init
Create Date: 2026-01-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_ingest_idempotency"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingest_idempotency",
        sa.Column("idempotency_key", sa.String(length=128), primary_key=True),
        sa.Column("device_id", sa.String(length=64), sa.ForeignKey("asset.asset_id"), nullable=False, index=True),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("ingest_idempotency")
