from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Callable, Dict, Optional
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from runtime.storage.models import JobLeaseModel

logger = logging.getLogger("hermes.runtime.lease")


@dataclass
class JobLease:
    """Represents exclusive execution ownership of a job by a runtime instance."""
    job_id: str
    owner_id: str
    acquired_at: str
    lease_until: str
    heartbeat_at: str

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now_dt = now or datetime.now(timezone.utc)
        try:
            expiry = datetime.fromisoformat(self.lease_until)
            return now_dt >= expiry
        except Exception:
            return True

    def is_active(self, now: Optional[datetime] = None) -> bool:
        return not self.is_expired(now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JobLeaseStore(ABC):
    """Abstract interface for atomic job execution lease management."""

    @abstractmethod
    async def acquire_lease(self, job_id: str, owner_id: str, duration_seconds: float = 60.0) -> bool:
        """
        Attempts to acquire or take over exclusive lease for a job.
        Returns True if acquired, False if currently held by another active executor.
        """
        pass

    @abstractmethod
    async def renew_lease(self, job_id: str, owner_id: str, duration_seconds: float = 60.0) -> bool:
        """
        Renews an existing lease held by owner_id. Returns True on success.
        """
        pass

    @abstractmethod
    async def release_lease(self, job_id: str, owner_id: str) -> bool:
        """
        Explicitly releases lease ownership. Returns True if released.
        """
        pass

    @abstractmethod
    async def get_lease(self, job_id: str) -> Optional[JobLease]:
        """
        Retrieves current lease details for a job if one exists.
        """
        pass


class InMemoryJobLeaseStore(JobLeaseStore):
    """Thread/coroutine-safe in-memory lease store for unit tests and local execution."""

    def __init__(self):
        self._leases: Dict[str, JobLease] = {}
        self._lock = asyncio.Lock()

    async def acquire_lease(self, job_id: str, owner_id: str, duration_seconds: float = 60.0) -> bool:
        async with self._lock:
            now = datetime.now(timezone.utc)
            existing = self._leases.get(job_id)
            if existing is not None and not existing.is_expired(now) and existing.owner_id != owner_id:
                logger.warning("Lease for job %s held by %s until %s (cannot acquire by %s)",
                               job_id, existing.owner_id, existing.lease_until, owner_id)
                return False

            now_iso = now.isoformat()
            until_iso = (now + timedelta(seconds=duration_seconds)).isoformat()
            self._leases[job_id] = JobLease(
                job_id=job_id,
                owner_id=owner_id,
                acquired_at=now_iso,
                lease_until=until_iso,
                heartbeat_at=now_iso,
            )
            return True

    async def renew_lease(self, job_id: str, owner_id: str, duration_seconds: float = 60.0) -> bool:
        async with self._lock:
            now = datetime.now(timezone.utc)
            existing = self._leases.get(job_id)
            if existing is None or existing.owner_id != owner_id:
                return False
            now_iso = now.isoformat()
            until_iso = (now + timedelta(seconds=duration_seconds)).isoformat()
            self._leases[job_id] = JobLease(
                job_id=job_id,
                owner_id=owner_id,
                acquired_at=existing.acquired_at,
                lease_until=until_iso,
                heartbeat_at=now_iso,
            )
            return True

    async def release_lease(self, job_id: str, owner_id: str) -> bool:
        async with self._lock:
            existing = self._leases.get(job_id)
            if existing is not None and existing.owner_id == owner_id:
                self._leases.pop(job_id, None)
                return True
            return False

    async def get_lease(self, job_id: str) -> Optional[JobLease]:
        async with self._lock:
            return self._leases.get(job_id)


class PostgresJobLeaseStore(JobLeaseStore):
    """PostgreSQL-backed atomic job lease store."""

    def __init__(self, engine_or_sessionmaker_or_url: Any):
        if isinstance(engine_or_sessionmaker_or_url, str):
            from sqlalchemy.ext.asyncio import create_async_engine
            db_url = engine_or_sessionmaker_or_url
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            engine = create_async_engine(db_url, pool_pre_ping=True)
            self._engine = engine
            self.sessionmaker = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        elif isinstance(engine_or_sessionmaker_or_url, AsyncEngine):
            self._engine = engine_or_sessionmaker_or_url
            self.sessionmaker = async_sessionmaker(
                engine_or_sessionmaker_or_url,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        else:
            self._engine = None
            self.sessionmaker = engine_or_sessionmaker_or_url

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    async def acquire_lease(self, job_id: str, owner_id: str, duration_seconds: float = 60.0) -> bool:
        async with self.sessionmaker() as session:
            async with session.begin():
                now = datetime.now(timezone.utc)
                until = now + timedelta(seconds=duration_seconds)

                stmt = select(JobLeaseModel).where(JobLeaseModel.job_id == job_id).with_for_update()
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing is not None:
                    # Check expiration or same owner
                    existing_until = existing.lease_until
                    if existing_until.tzinfo is None:
                        existing_until = existing_until.replace(tzinfo=timezone.utc)
                    if existing_until > now and existing.owner_id != owner_id:
                        logger.warning("Postgres lease for job %s held by %s until %s",
                                       job_id, existing.owner_id, existing.lease_until)
                        return False
                    existing.owner_id = owner_id
                    existing.acquired_at = now
                    existing.lease_until = until
                    existing.heartbeat_at = now
                else:
                    new_lease = JobLeaseModel(
                        job_id=job_id,
                        owner_id=owner_id,
                        acquired_at=now,
                        lease_until=until,
                        heartbeat_at=now,
                    )
                    session.add(new_lease)
                await session.flush()
                return True

    async def renew_lease(self, job_id: str, owner_id: str, duration_seconds: float = 60.0) -> bool:
        async with self.sessionmaker() as session:
            async with session.begin():
                now = datetime.now(timezone.utc)
                until = now + timedelta(seconds=duration_seconds)
                stmt = (
                    update(JobLeaseModel)
                    .where(JobLeaseModel.job_id == job_id, JobLeaseModel.owner_id == owner_id)
                    .values(lease_until=until, heartbeat_at=now)
                )
                result = await session.execute(stmt)
                return result.rowcount > 0

    async def release_lease(self, job_id: str, owner_id: str) -> bool:
        async with self.sessionmaker() as session:
            async with session.begin():
                stmt = delete(JobLeaseModel).where(
                    JobLeaseModel.job_id == job_id,
                    JobLeaseModel.owner_id == owner_id,
                )
                result = await session.execute(stmt)
                return result.rowcount > 0

    async def get_lease(self, job_id: str) -> Optional[JobLease]:
        async with self.sessionmaker() as session:
            stmt = select(JobLeaseModel).where(JobLeaseModel.job_id == job_id)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return JobLease(
                job_id=model.job_id,
                owner_id=model.owner_id,
                acquired_at=model.acquired_at.isoformat() if hasattr(model.acquired_at, "isoformat") else str(model.acquired_at),
                lease_until=model.lease_until.isoformat() if hasattr(model.lease_until, "isoformat") else str(model.lease_until),
                heartbeat_at=model.heartbeat_at.isoformat() if hasattr(model.heartbeat_at, "isoformat") else str(model.heartbeat_at),
            )


class JobLeaseManager:
    """Manages periodic heartbeat renewal of job execution leases."""

    def __init__(
        self,
        lease_store: JobLeaseStore,
        owner_id: Optional[str] = None,
        duration_seconds: float = 60.0,
        heartbeat_interval_seconds: float = 15.0,
        on_lease_lost: Optional[Callable[[str], Any]] = None,
    ):
        self.lease_store = lease_store
        self.owner_id = owner_id or f"hermes-node-{uuid.uuid4().hex[:8]}"
        self.duration_seconds = duration_seconds
        self.heartbeat_interval = heartbeat_interval_seconds
        self.on_lease_lost = on_lease_lost
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}

    async def acquire_and_start_heartbeat(self, job_id: str) -> bool:
        acquired = await self.lease_store.acquire_lease(
            job_id=job_id,
            owner_id=self.owner_id,
            duration_seconds=self.duration_seconds,
        )
        if not acquired:
            return False

        task = asyncio.create_task(self._heartbeat_loop(job_id), name=f"lease-hb-{job_id}")
        self._heartbeat_tasks[job_id] = task
        return True

    async def release_and_stop_heartbeat(self, job_id: str) -> bool:
        task = self._heartbeat_tasks.pop(job_id, None)
        if task and not task.done():
            task.cancel()
        return await self.lease_store.release_lease(job_id=job_id, owner_id=self.owner_id)

    async def _heartbeat_loop(self, job_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                success = False
                try:
                    success = await self.lease_store.renew_lease(
                        job_id=job_id,
                        owner_id=self.owner_id,
                        duration_seconds=self.duration_seconds,
                    )
                except Exception as exc:
                    logger.error("Exception during lease heartbeat for job %s: %s", job_id, exc)
                    success = False

                if not success:
                    logger.error("Failed to renew lease for job %s; lost ownership. Triggering fencing.", job_id)
                    if self.on_lease_lost:
                        try:
                            res = self.on_lease_lost(job_id)
                            if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                                await res
                        except Exception as exc:
                            logger.error("Error invoking on_lease_lost callback for job %s: %s", job_id, exc)
                    break
        except asyncio.CancelledError:
            pass
