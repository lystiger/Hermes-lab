import asyncio
from datetime import datetime, timezone
import pytest
import uuid
from sqlalchemy.ext.asyncio import create_async_engine

from runtime.storage.event_store import (
    IdempotencyConflictError,
    SequenceConflictError,
    StorageUnavailableError,
)
from runtime.storage.models import Base
from runtime.storage.postgres_store import PostgresRuntimeEventStore
from runtime.storage.schema_registry import StoredRuntimeEvent, create_event


@pytest.fixture
async def async_db_store(tmp_path):
    """Creates a local async database store using a clean temp file."""
    db_file = tmp_path / "test_events.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    store = PostgresRuntimeEventStore(database_url=f"sqlite+aiosqlite:///{db_file}", engine=engine)
    yield store
    await store.close()


@pytest.mark.anyio
async def test_postgres_store_append_and_retrieve(async_db_store):
    """Test standard append and retrieval on async relational event store."""
    store = async_db_store
    job_id = "job_pg_test_01"

    # Health check
    assert await store.health_check() is True

    # Append 3 events
    e1 = await store.append(create_event(job_id=job_id, event_type="job.created", payload={"goal": "Async DB test"}))
    e2 = await store.append(create_event(job_id=job_id, event_type="task.created", payload={"taskId": "T1"}))
    e3 = await store.append(create_event(job_id=job_id, event_type="task.completed", payload={"taskId": "T1"}))

    assert e1.sequence == 1
    assert e2.sequence == 2
    assert e3.sequence == 3

    # List events
    events = await store.list_events(job_id)
    assert len(events) == 3
    assert [e.sequence for e in events] == [1, 2, 3]

    # Events after
    after_1 = await store.events_after(job_id, sequence=1)
    assert len(after_1) == 2
    assert [e.sequence for e in after_1] == [2, 3]

    # Latest sequence
    assert await store.latest_sequence(job_id) == 3

    # Get single event
    fetched = await store.get_event(e2.event_id)
    assert fetched is not None
    assert fetched.event_id == e2.event_id
    assert fetched.event_type == "task.created"
    assert fetched.payload["taskId"] == "T1"


@pytest.mark.anyio
async def test_postgres_store_concurrent_appends(async_db_store):
    """Test that concurrent appends against async store produce consecutive unique sequences."""
    store = async_db_store
    job_id = "job_pg_concurrent"
    num_events = 20

    async def _worker(idx: int):
        evt = create_event(
            job_id=job_id,
            event_type="worker.item",
            payload={"idx": idx},
        )
        return await store.append(evt)

    results = await asyncio.gather(*[_worker(i) for i in range(num_events)])

    sequences = [r.sequence for r in results]
    assert len(sequences) == num_events
    assert sorted(sequences) == list(range(1, num_events + 1))
    assert len(set(sequences)) == num_events


@pytest.mark.anyio
async def test_postgres_store_idempotent_deduplication(async_db_store):
    """Test idempotent retry handling vs conflicting payload failure."""
    store = async_db_store
    job_id = "job_pg_idempotency"

    evt_id = str(uuid.uuid4())
    evt = create_event(
        event_id=evt_id,
        job_id=job_id,
        event_type="agent.started",
        payload={"runId": "run_99", "actorId": "gemini"},
    )

    # First append
    s1 = await store.append(evt)
    assert s1.sequence == 1

    # Identical retry
    s2 = await store.append(evt)
    assert s2.sequence == 1
    assert s2.event_id == evt_id

    # Conflict on same event_id
    conflict = create_event(
        event_id=evt_id,
        job_id=job_id,
        event_type="agent.started",
        payload={"runId": "run_99", "actorId": "DIFFERENT_ACTOR"},
    )
    with pytest.raises(IdempotencyConflictError):
        await store.append(conflict)


@pytest.mark.anyio
async def test_postgres_store_unavailable_failure():
    """Requirement M: Configured store failure raises explicit StorageUnavailableError."""
    # Create store pointing to unreachable address
    bad_store = PostgresRuntimeEventStore(
        database_url="postgresql+asyncpg://nonexistent_user:badpass@127.0.0.1:59999/nonexistent_db"
    )

    # Health check must return False
    assert await bad_store.health_check() is False

    # Append must fail explicitly with StorageUnavailableError
    evt = create_event(job_id="job_fail", event_type="job.created")
    with pytest.raises(StorageUnavailableError):
        await bad_store.append(evt)

    await bad_store.close()
