import asyncio
import os
from typing import List
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from unittest.mock import patch, AsyncMock

from runtime.storage.event_store import (
    IdempotencyConflictError,
    SequenceConflictError,
    StorageUnavailableError,
)
from runtime.storage.models import Base
from runtime.storage.postgres_store import PostgresRuntimeEventStore
from runtime.storage.schema_registry import StoredRuntimeEvent, create_event


@pytest.fixture
async def multi_store_setup(tmp_path):
    """
    Creates two completely independent PostgresRuntimeEventStore instances
    pointing to the same underlying database file.
    """
    db_file = tmp_path / "multi_store_events.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    # Initialize tables
    init_engine = create_async_engine(db_url)
    async with init_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_engine.dispose()

    # Store 1
    engine1 = create_async_engine(db_url, pool_size=5)
    store1 = PostgresRuntimeEventStore(database_url=db_url, engine=engine1)

    # Store 2
    engine2 = create_async_engine(db_url, pool_size=5)
    store2 = PostgresRuntimeEventStore(database_url=db_url, engine=engine2)

    yield store1, store2

    await store1.close()
    await store2.close()


@pytest.fixture
async def live_postgres_multi_store():
    """
    Creates two independent PostgresRuntimeEventStore instances pointing to live PostgreSQL container.
    Gracefully skips if live PostgreSQL is not reachable.
    """
    pg_url = os.environ.get("DATABASE_URL") or "postgresql+asyncpg://postgres:postgres@localhost:5432/hermes_lab"
    if pg_url.startswith("postgresql://") and "+asyncpg" not in pg_url:
        pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    try:
        init_engine = create_async_engine(pg_url, pool_size=2)
        async with init_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await init_engine.dispose()

        store1 = PostgresRuntimeEventStore(database_url=pg_url)
        store2 = PostgresRuntimeEventStore(database_url=pg_url)
        is_healthy = await store1.health_check()
        if not is_healthy:
            await store1.close()
            await store2.close()
            pytest.skip("Live PostgreSQL database is not reachable")
    except Exception:
        pytest.skip("Live PostgreSQL container not reachable")

    yield store1, store2

    await store1.close()
    await store2.close()


@pytest.mark.anyio
async def test_two_store_concurrent_sequence_allocation(multi_store_setup):
    """
    Scenario 11: Two independent store instances concurrently appending events for the same job.
    All events must be persisted with strictly unique sequences forming contiguous 1..N.
    """
    store1, store2 = multi_store_setup
    job_id = "job_multi_store_seq"

    async def append_worker(store: PostgresRuntimeEventStore, prefix: str, count: int) -> List[StoredRuntimeEvent]:
        appended = []
        for i in range(count):
            evt = create_event(
                job_id=job_id,
                event_type="task.created",
                payload={"taskId": f"{prefix}_{i}"},
            )
            res = await store.append(evt)
            appended.append(res)
        return appended

    # Run concurrent appends across both store instances
    results1, results2 = await asyncio.gather(
        append_worker(store1, "store1", 10),
        append_worker(store2, "store2", 10),
    )

    all_events = await store1.list_events(job_id)
    assert len(all_events) == 20

    sequences = [e.sequence for e in all_events]
    assert sequences == list(range(1, 21)), "Sequences across independent stores must form contiguous 1..20"
    assert len(set(sequences)) == 20, "No duplicate sequence numbers may exist"


@pytest.mark.anyio
async def test_two_store_concurrent_duplicate_event_id_idempotency(multi_store_setup):
    """
    Scenario 12: Concurrently appending the exact same event_id from two independent store instances
    must succeed idempotently for identical payloads, and raise IdempotencyConflictError for conflicting payloads.
    """
    store1, store2 = multi_store_setup
    job_id = "job_multi_store_idemp"
    event_id = "evt_shared_uuid_999"

    e1 = StoredRuntimeEvent(
        event_id=event_id,
        job_id=job_id,
        sequence=0,
        event_type="task.started",
        occurred_at="2026-08-25T10:00:00Z",
        payload={"taskId": "T_shared", "actorId": "worker_a"},
    )

    e2 = StoredRuntimeEvent(
        event_id=event_id,
        job_id=job_id,
        sequence=0,
        event_type="task.started",
        occurred_at="2026-08-25T10:00:00Z",
        payload={"taskId": "T_shared", "actorId": "worker_a"},
    )

    # Concurrently append from store1 and store2
    res1, res2 = await asyncio.gather(
        store1.append(e1),
        store2.append(e2),
    )

    assert res1.event_id == event_id
    assert res2.event_id == event_id
    assert res1.sequence == res2.sequence

    all_events = await store1.list_events(job_id)
    assert len(all_events) == 1, "Exactly one row must exist in the database"

    # Now attempt conflicting append with same event_id but different actor
    e_conflict = StoredRuntimeEvent(
        event_id=event_id,
        job_id=job_id,
        sequence=0,
        event_type="task.started",
        occurred_at="2026-08-25T10:00:00Z",
        payload={"taskId": "T_shared", "actorId": "worker_DIFFERENT"},
    )

    with pytest.raises(IdempotencyConflictError):
        await store2.append(e_conflict)


@pytest.mark.anyio
async def test_live_postgres_concurrent_sequence_allocation_and_idempotency(live_postgres_multi_store):
    """
    Scenario 13: True live PostgreSQL test verifying transaction advisory locking,
    concurrent sequence allocation across independent sessions, and idempotent deduplication.
    """
    store1, store2 = live_postgres_multi_store
    import uuid
    job_id = f"job_live_pg_{uuid.uuid4().hex[:8]}"

    # Concurrent appends across 2 distinct stores backed by real PostgreSQL
    async def worker(store: PostgresRuntimeEventStore, prefix: str, count: int) -> List[StoredRuntimeEvent]:
        events = []
        for i in range(count):
            evt = create_event(job_id=job_id, event_type="task.created", payload={"taskId": f"{prefix}_{i}"})
            res = await store.append(evt)
            events.append(res)
        return events

    r1, r2 = await asyncio.gather(
        worker(store1, "p1", 10),
        worker(store2, "p2", 10),
    )

    persisted = await store1.list_events(job_id)
    assert len(persisted) == 20
    seqs = [e.sequence for e in persisted]
    assert seqs == list(range(1, 21))

    # Duplicate append idempotency on real PostgreSQL
    shared_id = f"evt_live_{uuid.uuid4().hex[:8]}"
    dup_evt1 = StoredRuntimeEvent(
        event_id=shared_id,
        job_id=job_id,
        sequence=0,
        event_type="task.completed",
        occurred_at="2026-08-25T10:00:00Z",
        payload={"taskId": "T_final"},
    )
    dup_evt2 = StoredRuntimeEvent(
        event_id=shared_id,
        job_id=job_id,
        sequence=0,
        event_type="task.completed",
        occurred_at="2026-08-25T10:00:00Z",
        payload={"taskId": "T_final"},
    )

    d_res1, d_res2 = await asyncio.gather(
        store1.append(dup_evt1),
        store2.append(dup_evt2),
    )
    assert d_res1.event_id == shared_id
    assert d_res2.event_id == shared_id


@pytest.mark.anyio
async def test_postgres_advisory_lock_failure_fails_closed(tmp_path):
    """
    Scenario 14: When dialect is PostgreSQL and advisory lock acquisition fails,
    append() must raise StorageUnavailableError fail-closed.
    """
    db_file = tmp_path / "pg_lock_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    store = PostgresRuntimeEventStore(database_url="postgresql+asyncpg://mock/db", engine=engine)

    evt = create_event(job_id="job_lock_fail", event_type="job.created", payload={"goal": "Lock test"})

    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec:
        mock_exec.side_effect = RuntimeError("Advisory lock acquisition timeout or dead connection")
        with pytest.raises(StorageUnavailableError) as exc_info:
            await store.append(evt)
        assert "Database error during event append" in str(exc_info.value) or "PostgreSQL advisory lock" in str(exc_info.value)

    await store.close()
