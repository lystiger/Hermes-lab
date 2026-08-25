"""Initial runtime_events table migration

Revision ID: 001_initial_runtime_events
Revises: 
Create Date: 2026-08-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_runtime_events"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use dialect-agnostic JSON with PostgreSQL JSONB variant
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "runtime_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("run_id", sa.String(length=255), nullable=True),
        sa.Column("actor_id", sa.String(length=100), nullable=True),
        sa.Column("parent_event_id", sa.String(length=64), nullable=True),
        sa.Column("causation_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("payload", json_type, nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("job_id", "sequence", name="uq_runtime_events_job_sequence"),
    )

    op.create_index("ix_runtime_events_job_id", "runtime_events", ["job_id"])
    op.create_index("ix_runtime_events_event_type", "runtime_events", ["event_type"])
    op.create_index("ix_runtime_events_occurred_at", "runtime_events", ["occurred_at"])
    op.create_index("ix_runtime_events_task_id", "runtime_events", ["task_id"])
    op.create_index("ix_runtime_events_run_id", "runtime_events", ["run_id"])
    op.create_index("ix_runtime_events_job_seq", "runtime_events", ["job_id", "sequence"])
    op.create_index("ix_runtime_events_job_type", "runtime_events", ["job_id", "event_type"])


def downgrade() -> None:
    op.drop_index("ix_runtime_events_job_type", table_name="runtime_events")
    op.drop_index("ix_runtime_events_job_seq", table_name="runtime_events")
    op.drop_index("ix_runtime_events_run_id", table_name="runtime_events")
    op.drop_index("ix_runtime_events_task_id", table_name="runtime_events")
    op.drop_index("ix_runtime_events_occurred_at", table_name="runtime_events")
    op.drop_index("ix_runtime_events_event_type", table_name="runtime_events")
    op.drop_index("ix_runtime_events_job_id", table_name="runtime_events")
    op.drop_table("runtime_events")
