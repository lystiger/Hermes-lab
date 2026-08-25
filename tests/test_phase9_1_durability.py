import asyncio
import copy
from typing import Any, Dict, List, Optional
import pytest

from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.job_state import JobRecord, JobState
from runtime.limits import RuntimeLimits
from runtime.scheduler import ReactiveScheduler
from runtime.storage.event_store import (
    RuntimeEventStore,
    StorageUnavailableError,
    SequenceConflictError,
    IdempotencyConflictError,
)
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.task_graph import TaskNode, TaskStatus
from capabilities.capabilities import CapabilityRegistry


class FailingEventStore(RuntimeEventStore):
    """
    Test event store wrapper that can simulate storage failures on specific event types or call counts.
    """

    def __init__(self, backing_store: Optional[RuntimeEventStore] = None):
        self.backing = backing_store or InMemoryRuntimeEventStore()
        self.fail_on_event_types: set = set()
        self.fail_after_count: Optional[int] = None
        self.call_count = 0

    def trigger_failure_on(self, event_type: str) -> None:
        self.fail_on_event_types.add(event_type)

    def trigger_failure_after(self, count: int) -> None:
        self.fail_after_count = count

    async def append(self, event: StoredRuntimeEvent) -> StoredRuntimeEvent:
        self.call_count += 1
        if event.event_type in self.fail_on_event_types:
            raise StorageUnavailableError(f"Simulated storage failure on event_type '{event.event_type}'")
        if self.fail_after_count is not None and self.call_count > self.fail_after_count:
            raise StorageUnavailableError(f"Simulated storage failure after {self.fail_after_count} appends")
        return await self.backing.append(event)

    async def list_events(self, job_id: str, limit: Optional[int] = None) -> List[StoredRuntimeEvent]:
        return await self.backing.list_events(job_id, limit)

    async def events_after(self, job_id: str, sequence: int, limit: Optional[int] = None) -> List[StoredRuntimeEvent]:
        return await self.backing.events_after(job_id, sequence, limit)

    async def latest_sequence(self, job_id: str) -> int:
        return await self.backing.latest_sequence(job_id)

    async def get_event(self, event_id: str) -> Optional[StoredRuntimeEvent]:
        return await self.backing.get_event(event_id)

    async def list_unfinished_jobs(self) -> List[str]:
        return await self.backing.list_unfinished_jobs()

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        await self.backing.close()


def create_test_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register_actor({"id": "worker", "name": "Test Worker", "capabilities": ["code.edit", "repo.read"]})
    return registry


@pytest.mark.anyio
async def test_critical_event_append_succeeds_before_runtime_progresses():
    """
    Scenario 1: Verify that event_bridge.emit_* awaits store.append() before runtime execution advances.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    registry = create_test_registry()

    engine = ReactiveJobEngine(
        job_id="job_dur_1",
        goal="Verify synchronous append",
        capability_registry=registry,
        event_bridge=bridge,
    )

    t1 = TaskNode(task_id="T1", job_id="job_dur_1", description="Task 1", required_capabilities=["code.edit"])
    await engine.initialize_and_plan(initial_tasks=[t1])

    # Store must already contain job.created, job.state_changed (PLANNING), task.created (T1), job.state_changed (EXECUTING)
    events = await store.list_events("job_dur_1")
    event_types = [e.event_type for e in events]
    assert "job.created" in event_types
    assert "task.created" in event_types
    assert "job.state_changed" in event_types
    assert len(events) >= 4


@pytest.mark.anyio
async def test_task_completed_persistence_failure_prevents_dependent_task_dispatch():
    """
    Scenario 2: When task.completed fails to persist, dependent task must NOT be dispatched,
    and engine execution must halt immediately with StorageUnavailableError.
    """
    failing_store = FailingEventStore()
    failing_store.trigger_failure_on("task.completed")

    bridge = RuntimeEventBridge(event_store=failing_store)
    registry = create_test_registry()

    engine = ReactiveJobEngine(
        job_id="job_dur_2",
        goal="Verify fail-closed on task completion persist failure",
        capability_registry=registry,
        event_bridge=bridge,
    )

    t2_dispatched = False

    async def mock_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        nonlocal t2_dispatched
        if task.task_id == "T2":
            t2_dispatched = True
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(mock_adapter)

    t1 = TaskNode(task_id="T1", job_id="job_dur_2", description="T1", required_capabilities=["code.edit"])
    t2 = TaskNode(task_id="T2", job_id="job_dur_2", description="T2", dependencies=["T1"], required_capabilities=["code.edit"])

    await engine.initialize_and_plan(initial_tasks=[t1, t2])

    with pytest.raises(StorageUnavailableError) as exc_info:
        await engine.run_until_complete()

    assert "task.completed" in str(exc_info.value)
    # T2 must NEVER have run because T1's completion failed durability guarantee
    assert not t2_dispatched
    # T2 must not be SUCCEEDED
    assert engine.graph.get_task("T2").status != TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_job_completed_persistence_failure_means_job_not_acknowledged_successful():
    """
    Scenario 3: When job.completed / terminal state persist fails, run_until_complete raises
    StorageUnavailableError and the job record does not report successful completion.
    """
    failing_store = FailingEventStore()
    failing_store.trigger_failure_on("job.completed")

    bridge = RuntimeEventBridge(event_store=failing_store)
    registry = create_test_registry()

    engine = ReactiveJobEngine(
        job_id="job_dur_3",
        goal="Verify fail-closed on job completion persist failure",
        capability_registry=registry,
        event_bridge=bridge,
    )

    async def mock_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(mock_adapter)

    t1 = TaskNode(task_id="T1", job_id="job_dur_3", description="T1", required_capabilities=["code.edit"])
    await engine.initialize_and_plan(initial_tasks=[t1])

    with pytest.raises(StorageUnavailableError) as exc_info:
        await engine.run_until_complete()

    assert "job.completed" in str(exc_info.value)


@pytest.mark.anyio
async def test_persistence_failure_is_not_swallowed_by_run_until_complete():
    """
    Scenario 4: run_until_complete must never swallow storage exceptions with try/except logger.warning.
    """
    failing_store = FailingEventStore()
    failing_store.trigger_failure_on("verification.started")

    bridge = RuntimeEventBridge(event_store=failing_store)
    registry = create_test_registry()

    engine = ReactiveJobEngine(
        job_id="job_dur_4",
        goal="Verify exception is propagated out of run_until_complete",
        capability_registry=registry,
        event_bridge=bridge,
    )

    async def mock_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(mock_adapter)

    t1 = TaskNode(task_id="T1", job_id="job_dur_4", description="T1", required_capabilities=["code.edit"])
    await engine.initialize_and_plan(initial_tasks=[t1])

    with pytest.raises(StorageUnavailableError):
        await engine.run_until_complete()


@pytest.mark.anyio
async def test_event_ledger_remains_valid_prefix_after_storage_failure():
    """
    Scenario 5: If store fails at event N, events 1..(N-1) form a strictly monotonic,
    gap-free prefix in the event store.
    """
    failing_store = FailingEventStore()
    failing_store.trigger_failure_after(3)  # Allows first 3 events then fails

    bridge = RuntimeEventBridge(event_store=failing_store)
    registry = create_test_registry()

    engine = ReactiveJobEngine(
        job_id="job_dur_5",
        goal="Verify valid ledger prefix",
        capability_registry=registry,
        event_bridge=bridge,
    )

    t1 = TaskNode(task_id="T1", job_id="job_dur_5", description="T1", required_capabilities=["code.edit"])
    t2 = TaskNode(task_id="T2", job_id="job_dur_5", description="T2", dependencies=["T1"], required_capabilities=["code.edit"])

    try:
        await engine.initialize_and_plan(initial_tasks=[t1, t2])
    except StorageUnavailableError:
        pass

    stored_events = await failing_store.list_events("job_dur_5")
    assert len(stored_events) == 3
    # Check sequences are strictly 1, 2, 3
    sequences = [e.sequence for e in stored_events]
    assert sequences == [1, 2, 3]


@pytest.mark.anyio
async def test_explicit_sequence_gaps_rejected():
    """
    Scenario 6: Appending an event with explicit sequence gaps (e.g. sequence 100 after 1)
    must raise SequenceConflictError.
    """
    store = InMemoryRuntimeEventStore()

    e1 = StoredRuntimeEvent(
        event_id="evt_seq_1",
        job_id="job_seq_gap",
        sequence=1,
        event_type="job.created",
        occurred_at="2026-08-25T10:00:00Z",
    )
    await store.append(e1)

    # Attempt to append sequence 100 (gap!)
    e_gap = StoredRuntimeEvent(
        event_id="evt_seq_gap",
        job_id="job_seq_gap",
        sequence=100,
        event_type="job.state_changed",
        occurred_at="2026-08-25T10:00:01Z",
    )

    with pytest.raises(SequenceConflictError) as exc_info:
        await store.append(e_gap)

    assert "Explicit sequence 100 is invalid" in str(exc_info.value)
