"""Index ingestion idempotency keys by expiry time.

Revision ID: 0018_ingest_expiry
Revises: 0017_notes
Create Date: 2026-10-30
"""

from __future__ import annotations

from alembic import op

revision = "0018_ingest_expiry"
down_revision = "0017_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This index serves bounded retention scans without blocking live writers.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_ingest_idempotency_created_at_key "
            "ON ingest_idempotency (created_at, idempotency_key);"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_ingest_idempotency_created_at_key;")
