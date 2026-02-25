"""notes

Revision ID: 0017_notes
Revises: 0016_data_quality_governance
Create Date: 2026-02-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_notes"
down_revision = "0016_data_quality_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note",
        sa.Column("note_id", sa.String(length=64), primary_key=True),
        sa.Column("city_id", sa.String(length=64), sa.ForeignKey("city.city_id"), nullable=False),
        sa.Column("asset_id", sa.String(length=64), sa.ForeignKey("asset.asset_id"), nullable=True),
        sa.Column("event_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=120), nullable=False, server_default="Ops"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_note_city_created", "note", ["city_id", "created_at"], unique=False)
    op.create_index("ix_note_asset", "note", ["asset_id"], unique=False)
    op.create_index("ix_note_event", "note", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_note_event", table_name="note")
    op.drop_index("ix_note_asset", table_name="note")
    op.drop_index("ix_note_city_created", table_name="note")
    op.drop_table("note")