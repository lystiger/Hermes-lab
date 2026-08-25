import asyncio
import copy
from datetime import datetime, timezone
import pytest
import uuid

from runtime.storage.event_store import (
    DuplicateEventError,
    IdempotencyConflictError,
    SequenceConflictError,
    StorageUnavailableError,
)
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.schema_registry import (
    CURRENT_SCHEMA_VERSION,
    InvalidEventEnvelopeError,
    StoredRuntimeEvent,
    UnsupportedSchemaVersionError,
    create_event,
)


@pytest.mark.anyio
async def test_append_and_retrieve_ordered_history():
    """Requirement A: Append events and retrieve exact ordered history."""
    store = InMemoryRuntimeEventStore()
    job_id = "job_test_001"

    # Append 5 events
    events_in = []
    for i in range(1, 6):
        evt = create_event(
            job_id=job_id,
            event_type=f"test.step_{i}",
            payload={"step": i, "detail": f"Step number {i}"},
        )
        stored = await store.append(evt)
        events_in.append(stored)
        assert stored.sequence == i

    # Retrieve all events
    events_out = await store.list_events(job_id)
    assert len(events_out) == 5
    for i, e in enumerate(events_out, start=1):
        assert e.sequence == i
        assert e.event_type == f"test.step_{i}"
        assert e.payload["step"] == i

    # Test events_after
    after_seq_2 = await store.events_after(job_id, sequence=2)
    assert len(after_seq_2) == 3
    assert [e.sequence for e in after_seq_2] == [3, 4, 5]

    # Test latest_sequence
    assert await store.latest_sequence(job_id) == 5

    # Test get_event
    single = await store.get_event(events_in[0].event_id)
    assert single is not None
    assert single.event_id == events_in[0].event_id
    assert single.event_type == "test.step_1"


@pytest.mark.anyio
async def test_per_job_independent_sequence_ordering():
    """Requirement B: Events for job A and job B have independent monotonically increasing sequences."""
    store = InMemoryRuntimeEventStore()
    job_a = "job_alpha"
    job_b = "job_beta"

    e_a1 = await store.append(create_event(job_id=job_a, event_type="job.created"))
    e_b1 = await store.append(create_event(job_id=job_b, event_type="job.created"))
    e_a2 = await store.append(create_event(job_id=job_a, event_type="task.created"))
    e_b2 = await store.append(create_event(job_id=job_b, event_type="task.created"))
    e_a3 = await store.append(create_event(job_id=job_a, event_type="task.started"))

    assert e_a1.sequence == 1
    assert e_a2.sequence == 2
    assert e_a3.sequence == 3

    assert e_b1.sequence == 1
    assert e_b2.sequence == 2

    assert await store.latest_sequence(job_a) == 3
    assert await store.latest_sequence(job_b) == 2


@pytest.mark.anyio
async def test_concurrent_appends_produce_deterministic_sequences():
    """Requirement C: Multiple concurrent appends for one job produce 1, 2, 3... with no duplicates."""
    store = InMemoryRuntimeEventStore()
    job_id = "job_concurrent_append"
    num_concurrent = 25

    async def _append_worker(idx: int):
        evt = create_event(
            job_id=job_id,
            event_type="task.progress",
            payload={"worker_idx": idx},
        )
        return await store.append(evt)

    # Launch all workers concurrently
    tasks = [_append_worker(i) for i in range(num_concurrent)]
    results = await asyncio.gather(*tasks)

    # Validate sequences
    sequences = [r.sequence for r in results]
    assert len(sequences) == num_concurrent
    assert sorted(sequences) == list(range(1, num_concurrent + 1))
    assert len(set(sequences)) == num_concurrent, "Duplicate sequence numbers were produced!"

    stored_list = await store.list_events(job_id)
    assert len(stored_list) == num_concurrent
    assert [e.sequence for e in stored_list] == list(range(1, num_concurrent + 1))


@pytest.mark.anyio
async def test_idempotent_append_retries():
    """Requirement D: Retrying the same event does not produce duplicate history; conflicting payload on same event_id fails."""
    store = InMemoryRuntimeEventStore()
    job_id = "job_idempotent"

    evt_id = str(uuid.uuid4())
    event_1 = create_event(
        event_id=evt_id,
        job_id=job_id,
        event_type="task.started",
        payload={"taskId": "T1", "attempt": 1},
    )

    # First append
    stored_1 = await store.append(event_1)
    assert stored_1.sequence == 1

    # Exact retry with same event_id and payload
    stored_2 = await store.append(event_1)
    assert stored_2.sequence == 1
    assert stored_2.event_id == evt_id

    # Store history must contain exactly 1 event
    all_events = await store.list_events(job_id)
    assert len(all_events) == 1

    # Append conflicting event with SAME event_id but DIFFERENT payload
    conflicting_event = create_event(
        event_id=evt_id,
        job_id=job_id,
        event_type="task.started",
        payload={"taskId": "T1", "attempt": 999},  # Conflicting attempt
    )
    with pytest.raises(IdempotencyConflictError):
        await store.append(conflicting_event)

    # Append conflicting event with SAME event_id but DIFFERENT event_type
    conflicting_type_event = create_event(
        event_id=evt_id,
        job_id=job_id,
        event_type="task.failed",  # Conflicting event_type
        payload={"taskId": "T1", "attempt": 1},
    )
    with pytest.raises(IdempotencyConflictError):
        await store.append(conflicting_type_event)


@pytest.mark.anyio
async def test_event_schema_validation():
    """Requirement E: Invalid payload/envelope rejected; unsupported schema version rejected."""
    # Empty event_id
    with pytest.raises(InvalidEventEnvelopeError):
        StoredRuntimeEvent(
            event_id="",
            job_id="job1",
            sequence=1,
            event_type="job.created",
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )

    # Empty job_id
    with pytest.raises(InvalidEventEnvelopeError):
        StoredRuntimeEvent(
            event_id=str(uuid.uuid4()),
            job_id="",
            sequence=1,
            event_type="job.created",
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )

    # Empty event_type
    with pytest.raises(InvalidEventEnvelopeError):
        StoredRuntimeEvent(
            event_id=str(uuid.uuid4()),
            job_id="job1",
            sequence=1,
            event_type="",
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )

    # Non-serializable payload
    class UnserializableObj:
        pass

    with pytest.raises(InvalidEventEnvelopeError):
        StoredRuntimeEvent(
            event_id=str(uuid.uuid4()),
            job_id="job1",
            sequence=1,
            event_type="job.created",
            occurred_at=datetime.now(timezone.utc).isoformat(),
            payload={"unserializable": UnserializableObj()},
        )

    # Unsupported schema version (> CURRENT_SCHEMA_VERSION)
    with pytest.raises(UnsupportedSchemaVersionError):
        StoredRuntimeEvent(
            event_id=str(uuid.uuid4()),
            job_id="job1",
            sequence=1,
            event_type="job.created",
            occurred_at=datetime.now(timezone.utc).isoformat(),
            schema_version=CURRENT_SCHEMA_VERSION + 1,
        )

    # Unsupported schema version (< 1)
    with pytest.raises(UnsupportedSchemaVersionError):
        StoredRuntimeEvent(
            event_id=str(uuid.uuid4()),
            job_id="job1",
            sequence=1,
            event_type="job.created",
            occurred_at=datetime.now(timezone.utc).isoformat(),
            schema_version=0,
        )


@pytest.mark.anyio
async def test_event_immutability():
    """Requirement N: Persisted event cannot be mutated through caller mutation."""
    store = InMemoryRuntimeEventStore()
    job_id = "job_immutability"

    payload = {"key": "original_value", "nested": {"count": 1}}
    evt = create_event(
        job_id=job_id,
        event_type="test.mutability",
        payload=payload,
    )

    stored = await store.append(evt)

    # Mutate original caller dictionary
    payload["key"] = "mutated_value"
    payload["nested"]["count"] = 999

    # Retrieve from store and assert it was not mutated
    retrieved = await store.get_event(stored.event_id)
    assert retrieved.payload["key"] == "original_value"
    assert retrieved.payload["nested"]["count"] == 1

    # Mutate retrieved event payload dictionary
    retrieved.payload["key"] = "second_mutation"

    # Re-retrieve from store
    re_retrieved = await store.get_event(stored.event_id)
    assert re_retrieved.payload["key"] == "original_value"


@pytest.mark.anyio
async def test_list_unfinished_jobs():
    """Verify list_unfinished_jobs correctly distinguishes running vs terminal jobs."""
    store = InMemoryRuntimeEventStore()

    # Job 1: Active
    await store.append(create_event(job_id="job_active_1", event_type="job.created"))
    await store.append(create_event(job_id="job_active_1", event_type="job.state_changed", payload={"previous_state": "created", "new_state": "executing"}))

    # Job 2: Completed
    await store.append(create_event(job_id="job_done_2", event_type="job.created"))
    await store.append(create_event(job_id="job_done_2", event_type="job.completed"))

    # Job 3: Blocked
    await store.append(create_event(job_id="job_blocked_3", event_type="job.created"))
    await store.append(create_event(job_id="job_blocked_3", event_type="job.blocked", payload={"reason": "Deadlock"}))

    # Job 4: Active
    await store.append(create_event(job_id="job_active_4", event_type="job.created"))

    unfinished = await store.list_unfinished_jobs()
    assert sorted(unfinished) == ["job_active_1", "job_active_4"]
