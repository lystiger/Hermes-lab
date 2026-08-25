import asyncio
import copy
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import replace

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from runtime.storage.event_store import (
    RuntimeEventStore,
    StorageUnavailableError,
    DuplicateEventError,
    IdempotencyConflictError,
    SequenceConflictError,
)
from runtime.storage.models import RuntimeEventModel
from runtime.storage.schema_registry import StoredRuntimeEvent

logger = logging.getLogger("hermes.runtime.storage.postgres")

TERMINAL_EVENT_TYPES = {
    "job.completed",
    "job.blocked",
    "job.failed",
    "job.cancelled",
}


def _model_to_dto(model: RuntimeEventModel) -> StoredRuntimeEvent:
    occurred_iso = (
        model.occurred_at.isoformat()
        if isinstance(model.occurred_at, datetime)
        else str(model.occurred_at)
    )
    payload = dict(model.payload) if isinstance(model.payload, dict) else {}
    return StoredRuntimeEvent(
        event_id=model.event_id,
        job_id=model.job_id,
        sequence=model.sequence,
        event_type=model.event_type,
        occurred_at=occurred_iso,
        schema_version=model.schema_version,
        task_id=model.task_id,
        run_id=model.run_id,
        actor_id=model.actor_id,
        parent_event_id=model.parent_event_id,
        causation_id=model.causation_id,
        correlation_id=model.correlation_id,
        payload=payload,
    )


class PostgresRuntimeEventStore(RuntimeEventStore):
    """
    PostgreSQL append-only implementation of RuntimeEventStore using asyncpg and SQLAlchemy.
    Uses transaction-level advisory locks and per-job in-process serialization for deterministic,
    concurrency-safe sequence allocation.
    """

    def __init__(
        self,
        database_url: str,
        engine: Optional[AsyncEngine] = None,
        pool_size: int = 10,
        max_overflow: int = 20,
    ):
        self.database_url = database_url
        if engine is not None:
            self.engine = engine
        else:
            # Ensure asyncpg dialect
            db_url = database_url
            if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            self.engine = create_async_engine(
                db_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True,
            )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._job_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._closed = False

    async def _get_job_lock(self, job_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if job_id not in self._job_locks:
                self._job_locks[job_id] = asyncio.Lock()
            return self._job_locks[job_id]

    async def health_check(self) -> bool:
        if self._closed:
            return False
        try:
            async with self.engine.connect() as conn:
                res = await conn.execute(text("SELECT 1"))
                return res.scalar() == 1
        except Exception as exc:
            logger.warning("Postgres health check failed: %s", exc)
            return False

    async def append(self, event: StoredRuntimeEvent) -> StoredRuntimeEvent:
        if self._closed:
            raise StorageUnavailableError("Event store is closed")

        lock = await self._get_job_lock(event.job_id)
        max_retries = 5 if event.sequence <= 0 else 1

        for attempt in range(max_retries):
            async with lock:
                try:
                    async with self.session_factory() as session:
                        async with session.begin():
                            # 1. Acquire transaction-level advisory lock on hashtext(job_id) if Postgres
                            # This serializes concurrent appends for the same job across processes/connections
                            bind = session.get_bind()
                            dialect_name = bind.dialect.name.lower() if bind else ""
                            is_postgres = dialect_name.startswith("postgres") or "postgresql" in dialect_name

                            if is_postgres:
                                try:
                                    await session.execute(
                                        text("SELECT pg_advisory_xact_lock(hashtext(:job_id))"),
                                        {"job_id": event.job_id},
                                    )
                                except Exception as exc:
                                    raise StorageUnavailableError(
                                        f"PostgreSQL advisory lock acquisition failed for job '{event.job_id}': {exc}"
                                    ) from exc

                            # 2. Check idempotency: check if event_id already exists (safely under lock)
                            stmt_existing = select(RuntimeEventModel).where(
                                RuntimeEventModel.event_id == event.event_id
                            )
                            res_existing = await session.execute(stmt_existing)
                            existing_model = res_existing.scalar_one_or_none()

                            if existing_model is not None:
                                existing_dto = _model_to_dto(existing_model)
                                if (
                                    existing_dto.job_id == event.job_id
                                    and existing_dto.event_type == event.event_type
                                    and existing_dto.payload == event.payload
                                    and existing_dto.task_id == event.task_id
                                    and existing_dto.run_id == event.run_id
                                    and existing_dto.actor_id == event.actor_id
                                    and existing_dto.schema_version == event.schema_version
                                ):
                                    logger.debug("Idempotent duplicate append for event %s", event.event_id)
                                    return existing_dto
                                else:
                                    raise IdempotencyConflictError(
                                        f"Event '{event.event_id}' already exists with conflicting data"
                                    )

                            # 3. Determine and validate next sequence
                            stmt_max = select(func.coalesce(func.max(RuntimeEventModel.sequence), 0)).where(
                                RuntimeEventModel.job_id == event.job_id
                            )
                            res_max = await session.execute(stmt_max)
                            max_seq = res_max.scalar() or 0

                            if event.sequence <= 0:
                                allocated_seq = max_seq + 1
                            else:
                                # Explicit sequence validation: must be exact next consecutive sequence (no gaps or duplicates)
                                if event.sequence != max_seq + 1:
                                    raise SequenceConflictError(
                                        f"Explicit sequence {event.sequence} is invalid; expected next sequence {max_seq + 1} for job '{event.job_id}'"
                                    )
                                allocated_seq = event.sequence

                            # Parse occurred_at
                            try:
                                occurred_dt = datetime.fromisoformat(event.occurred_at)
                            except (ValueError, TypeError):
                                occurred_dt = datetime.now(timezone.utc)

                            new_model = RuntimeEventModel(
                                event_id=event.event_id,
                                job_id=event.job_id,
                                sequence=allocated_seq,
                                event_type=event.event_type,
                                occurred_at=occurred_dt,
                                schema_version=event.schema_version,
                                task_id=event.task_id,
                                run_id=event.run_id,
                                actor_id=event.actor_id,
                                parent_event_id=event.parent_event_id,
                                causation_id=event.causation_id,
                                correlation_id=event.correlation_id,
                                payload=copy.deepcopy(event.payload),
                            )
                            session.add(new_model)
                            await session.flush()
                            return _model_to_dto(new_model)

                except (IdempotencyConflictError, SequenceConflictError):
                    raise
                except IntegrityError as exc:
                    # Check if event_id already exists in store (concurrent duplicate race)
                    try:
                        async with self.session_factory() as check_session:
                            stmt_existing = select(RuntimeEventModel).where(
                                RuntimeEventModel.event_id == event.event_id
                            )
                            res_existing = await check_session.execute(stmt_existing)
                            existing_model = res_existing.scalar_one_or_none()
                            if existing_model is not None:
                                existing_dto = _model_to_dto(existing_model)
                                if (
                                    existing_dto.job_id == event.job_id
                                    and existing_dto.event_type == event.event_type
                                    and existing_dto.payload == event.payload
                                    and existing_dto.task_id == event.task_id
                                    and existing_dto.run_id == event.run_id
                                    and existing_dto.actor_id == event.actor_id
                                    and existing_dto.schema_version == event.schema_version
                                ):
                                    return existing_dto
                                else:
                                    raise IdempotencyConflictError(
                                        f"Event '{event.event_id}' already exists with conflicting data"
                                    ) from exc
                    except (IdempotencyConflictError, StorageUnavailableError):
                        raise
                    except Exception:
                        pass

                    # If auto-sequencing on non-postgres backend, retry next sequence
                    if event.sequence <= 0 and attempt < max_retries - 1:
                        await asyncio.sleep(0.01 * (attempt + 1))
                        continue

                    err_msg = str(exc).lower()
                    if "uq_runtime_events_job_sequence" in err_msg or "unique constraint" in err_msg or "sequence" in err_msg:
                        raise SequenceConflictError(
                            f"Sequence conflict while appending event for job '{event.job_id}': {exc}"
                        ) from exc
                    if "primary key" in err_msg or "event_id" in err_msg:
                        raise DuplicateEventError(
                            f"Duplicate event_id '{event.event_id}': {exc}"
                        ) from exc
                    raise DuplicateEventError(f"Integrity error appending event: {exc}") from exc
                except OperationalError as exc:
                    raise StorageUnavailableError(f"PostgreSQL storage unavailable: {exc}") from exc
                except Exception as exc:
                    raise StorageUnavailableError(f"Database error during event append: {exc}") from exc

    async def list_events(self, job_id: str, limit: Optional[int] = None) -> List[StoredRuntimeEvent]:
        if self._closed:
            raise StorageUnavailableError("Event store is closed")
        try:
            async with self.session_factory() as session:
                stmt = (
                    select(RuntimeEventModel)
                    .where(RuntimeEventModel.job_id == job_id)
                    .order_by(RuntimeEventModel.sequence.asc())
                )
                if limit is not None and limit > 0:
                    stmt = stmt.limit(limit)
                res = await session.execute(stmt)
                models = res.scalars().all()
                return [_model_to_dto(m) for m in models]
        except OperationalError as exc:
            raise StorageUnavailableError(f"PostgreSQL storage unavailable: {exc}") from exc

    async def events_after(
        self, job_id: str, sequence: int, limit: Optional[int] = None
    ) -> List[StoredRuntimeEvent]:
        if self._closed:
            raise StorageUnavailableError("Event store is closed")
        try:
            async with self.session_factory() as session:
                stmt = (
                    select(RuntimeEventModel)
                    .where(
                        RuntimeEventModel.job_id == job_id,
                        RuntimeEventModel.sequence > sequence,
                    )
                    .order_by(RuntimeEventModel.sequence.asc())
                )
                if limit is not None and limit > 0:
                    stmt = stmt.limit(limit)
                res = await session.execute(stmt)
                models = res.scalars().all()
                return [_model_to_dto(m) for m in models]
        except OperationalError as exc:
            raise StorageUnavailableError(f"PostgreSQL storage unavailable: {exc}") from exc

    async def latest_sequence(self, job_id: str) -> int:
        if self._closed:
            raise StorageUnavailableError("Event store is closed")
        try:
            async with self.session_factory() as session:
                stmt = select(func.coalesce(func.max(RuntimeEventModel.sequence), 0)).where(
                    RuntimeEventModel.job_id == job_id
                )
                res = await session.execute(stmt)
                return res.scalar() or 0
        except OperationalError as exc:
            raise StorageUnavailableError(f"PostgreSQL storage unavailable: {exc}") from exc

    async def get_event(self, event_id: str) -> Optional[StoredRuntimeEvent]:
        if self._closed:
            raise StorageUnavailableError("Event store is closed")
        try:
            async with self.session_factory() as session:
                stmt = select(RuntimeEventModel).where(RuntimeEventModel.event_id == event_id)
                res = await session.execute(stmt)
                model = res.scalar_one_or_none()
                return _model_to_dto(model) if model else None
        except OperationalError as exc:
            raise StorageUnavailableError(f"PostgreSQL storage unavailable: {exc}") from exc

    async def list_unfinished_jobs(self) -> List[str]:
        if self._closed:
            raise StorageUnavailableError("Event store is closed")
        try:
            async with self.session_factory() as session:
                # Find all distinct job_ids that do not have terminal events
                stmt_terminal = select(RuntimeEventModel.job_id).where(
                    RuntimeEventModel.event_type.in_(TERMINAL_EVENT_TYPES)
                )
                stmt = (
                    select(RuntimeEventModel.job_id)
                    .where(~RuntimeEventModel.job_id.in_(stmt_terminal))
                    .distinct()
                )
                res = await session.execute(stmt)
                return sorted([r[0] for r in res.all()])
        except OperationalError as exc:
            raise StorageUnavailableError(f"PostgreSQL storage unavailable: {exc}") from exc

    async def close(self) -> None:
        self._closed = True
        await self.engine.dispose()
