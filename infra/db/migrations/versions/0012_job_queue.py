"""job_queue"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0012_job_queue"
down_revision = "0011_export_job_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_queue",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_job_queue_status", "job_queue", ["status"], unique=False)
    op.create_index("ix_job_queue_job_type", "job_queue", ["job_type"], unique=False)
    op.create_index("ix_job_queue_scheduled", "job_queue", ["scheduled_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_queue_scheduled", table_name="job_queue")
    op.drop_index("ix_job_queue_job_type", table_name="job_queue")
    op.drop_index("ix_job_queue_status", table_name="job_queue")
    op.drop_table("job_queue")
