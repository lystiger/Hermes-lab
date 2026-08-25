import asyncio
from datetime import datetime, timezone, timedelta
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskNode, TaskStatus
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.recovery import RecoveryManager
from runtime.engine import ReactiveJobEngine


@pytest.mark.anyio
async def test_rpo_zero_canonical_events_retained_across_simulated_crash():
    """
    Test P & Q: RPO = 0 canonical events.
    Every acknowledged durable event persisted before simulated crash is present
    and reconstructed with exact monotonically ordered sequence numbers.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    job = JobRecord(job_id="job_rpo_test", goal="Test RPO zero guarantee")
    await bridge.emit_job_created(job)
    job.state = JobState.PLANNING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    t1 = TaskNode(task_id="T1", job_id="job_rpo_test", description="Inspect repo")
    t2 = TaskNode(task_id="T2", job_id="job_rpo_test", description="Build model", dependencies=["T1"])
    await bridge.emit_task_created(t1)
    await bridge.emit_task_created(t2)

    await bridge.emit_task_started(t1, actor_id="actor_code")
    await bridge.emit_task_completed(t1, actor_id="actor_code", artifacts=[{"id": "art_1", "label": "inspection_report"}])

    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.PLANNING)

    # Simulated sudden process death: destroy all in-memory references
    del job
    del t1
    del t2
    del bridge

    # Inspect event store directly
    events = await store.list_events("job_rpo_test")
    assert len(events) == 7

    # Verify monotonic sequences
    sequences = [e.sequence for e in events]
    assert sequences == [1, 2, 3, 4, 5, 6, 7]

    # Reconstruct state
    reconstructed = RuntimeStateProjector.project(events)
    assert reconstructed.job.state == JobState.EXECUTING
    assert reconstructed.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T2").status == TaskStatus.PENDING
    assert len(reconstructed.artifacts) == 1
    assert reconstructed.artifacts[0]["id"] == "art_1"


@pytest.mark.anyio
async def test_rto_timestamps_and_derived_metric_consistency():
    """
    Test R: RTO timing telemetry records failure_detected_at, recovery_started_at,
    execution_resumed_at, and calculates positive, consistent rto_seconds.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    job = JobRecord(job_id="job_rto_test", goal="Test RTO calculation")
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)
    t1 = TaskNode(task_id="T1", job_id="job_rto_test", description="T1")
    await bridge.emit_task_created(t1)

    detected_interruption = (datetime.now(timezone.utc) - timedelta(seconds=12.5)).isoformat()

    manager = RecoveryManager(event_store=store)
    engine, metrics = await manager.recover_and_rehydrate(
        job_id="job_rto_test",
        detected_interruption_at=detected_interruption,
    )

    assert metrics.job_id == "job_rto_test"
    assert metrics.failure_detected_at == detected_interruption
    assert metrics.rto_seconds >= 12.0
    assert metrics.execution_resumed_at is not None
    assert metrics.recovery_completed_at is not None

    # Check recovery event in store
    events = await store.list_events("job_rto_test")
    comp_event = next(e for e in events if e.event_type == "recovery.completed")
    assert comp_event.payload["rtoSeconds"] >= 12.0
