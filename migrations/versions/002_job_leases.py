"""Job leases table migration

Revision ID: 002_job_leases
Revises: 001_initial_runtime_events
Create Date: 2026-08-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_job_leases"
down_revision: Union[str, None] = "001_initial_runtime_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_leases",
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
    )

    op.create_index("ix_job_leases_owner_id", "job_leases", ["owner_id"])
    op.create_index("ix_job_leases_lease_until", "job_leases", ["lease_until"])


def downgrade() -> None:
    op.drop_index("ix_job_leases_lease_until", table_name="job_leases")
    op.drop_index("ix_job_leases_owner_id", table_name="job_leases")
    op.drop_table("job_leases")
