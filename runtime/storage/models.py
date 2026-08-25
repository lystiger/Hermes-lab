from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Generic metadata for alembic and table definitions
metadata = MetaData()


class Base(DeclarativeBase):
    metadata = metadata


class RuntimeEventModel(Base):
    __tablename__ = "runtime_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    parent_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    causation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Use JSONB on PostgreSQL, standard JSON elsewhere
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_runtime_events_job_sequence"),
        Index("ix_runtime_events_job_seq", "job_id", "sequence"),
        Index("ix_runtime_events_job_type", "job_id", "event_type"),
    )


class JobLeaseModel(Base):
    __tablename__ = "job_leases"

    job_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    lease_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
