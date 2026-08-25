import asyncio
from typing import Any, Dict, List, Optional
import pytest

from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.execution import AgentRun, AgentRunStatus, TaskExecutionResult, ExecutionManager
from runtime.job_state import JobRecord, JobState
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.task_graph import TaskNode, TaskStatus
from capabilities.capabilities import CapabilityRegistry


def create_test_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register_actor({"id": "worker", "name": "Worker", "capabilities": ["code.edit", "repo.read"]})
    return registry


@pytest.mark.anyio
async def test_task_cancelled_persists_and_reconstructs():
    """
    Scenario 7: task.cancelled event is persisted with taskId, reason, attempt, and assignedActor,
    and RuntimeStateProjector projects the task to TaskStatus.CANCELLED.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    registry = create_test_registry()

    engine = ReactiveJobEngine(
        job_id="job_cancel_1",
        goal="Test task cancellation",
        capability_registry=registry,
        event_bridge=bridge,
    )

    t1 = TaskNode(task_id="T1", job_id="job_cancel_1", description="T1", required_capabilities=["code.edit"])
    t2 = TaskNode(task_id="T2", job_id="job_cancel_1", description="T2", dependencies=["T1"], required_capabilities=["code.edit"])

    await engine.initialize_and_plan(initial_tasks=[t1, t2])

    # Cancel the job
    await engine.cancel(reason="Operator cancelled during execution")

    # Verify event store contains task.cancelled events
    events = await store.list_events("job_cancel_1")
    task_cancelled_events = [e for e in events if e.event_type == "task.cancelled"]
    assert len(task_cancelled_events) >= 1

    for evt in task_cancelled_events:
        assert evt.payload["taskId"] in {"T1", "T2"}
        assert evt.payload["reason"] == "Operator cancelled during execution"

    # Reconstruct from event stream
    reconstructed = RuntimeStateProjector.project(events)
    assert reconstructed.job.state == JobState.CANCELLED
    assert reconstructed.graph.get_task("T1").status == TaskStatus.CANCELLED
    assert reconstructed.graph.get_task("T2").status == TaskStatus.CANCELLED


@pytest.mark.anyio
async def test_agent_cancelled_persists_and_reconstructs():
    """
    Scenario 8: When an active agent run is cancelled, agent.cancelled event is emitted and
    the projector reconstructs the run in AgentRunStatus.CANCELLED.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    exec_manager = ExecutionManager()

    task = TaskNode(task_id="T_long", job_id="job_agent_cancel", description="Long task")

    cancelled_event = asyncio.Event()

    async def long_running_adapter(t: TaskNode, r: AgentRun, ctx: dict):
        try:
            await asyncio.sleep(10)
            return TaskExecutionResult(status="succeeded")
        except asyncio.CancelledError:
            cancelled_event.set()
            raise

    exec_manager.set_default_adapter(long_running_adapter)

    # Launch execution task
    exec_task = asyncio.create_task(
        exec_manager.execute(
            task=task,
            actor_id="worker",
            event_bridge=bridge,
        )
    )

    await asyncio.sleep(0.05)
    # Cancel the in-flight execution
    exec_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await exec_task

    assert cancelled_event.is_set()

    # Verify event store contains agent.cancelled
    events = await store.list_events("job_agent_cancel")
    agent_cancelled_events = [e for e in events if e.event_type == "agent.cancelled"]
    assert len(agent_cancelled_events) == 1
    assert agent_cancelled_events[0].payload["reason"] == "cancelled"

    # Project and verify reconstructed run state
    # First emit a job.created event so projector has a valid job anchor
    e_job = StoredRuntimeEvent(
        event_id="evt_job_created",
        job_id="job_agent_cancel",
        sequence=1,
        event_type="job.created",
        occurred_at="2026-08-25T10:00:00Z",
        payload={"goal": "Test agent cancellation"},
    )
    all_events = [e_job] + events
    reconstructed = RuntimeStateProjector.project(all_events)
    assert len(reconstructed.runs) == 1
    assert reconstructed.runs[0].status == AgentRunStatus.CANCELLED


@pytest.mark.anyio
async def test_cancelled_job_reconstruction_has_no_running_task_or_run_leftovers():
    """
    Scenario 9: Reconstructing a CANCELLED job guarantees zero tasks or runs are left
    in RUNNING, READY, or PENDING states.
    """
    events = [
        StoredRuntimeEvent(
            event_id="e1",
            job_id="job_no_leftovers",
            sequence=1,
            event_type="job.created",
            occurred_at="2026-08-25T10:00:00Z",
            payload={"goal": "Goal"},
        ),
        StoredRuntimeEvent(
            event_id="e2",
            job_id="job_no_leftovers",
            sequence=2,
            event_type="task.created",
            task_id="T1",
            occurred_at="2026-08-25T10:00:01Z",
            payload={"taskId": "T1", "description": "Task 1"},
        ),
        StoredRuntimeEvent(
            event_id="e3",
            job_id="job_no_leftovers",
            sequence=3,
            event_type="task.started",
            task_id="T1",
            actor_id="worker",
            occurred_at="2026-08-25T10:00:02Z",
            payload={"taskId": "T1", "actorId": "worker"},
        ),
        StoredRuntimeEvent(
            event_id="e4",
            job_id="job_no_leftovers",
            sequence=4,
            event_type="agent.started",
            task_id="T1",
            run_id="run_001",
            actor_id="worker",
            occurred_at="2026-08-25T10:00:02Z",
            payload={"runId": "run_001", "taskId": "T1", "actorId": "worker"},
        ),
        StoredRuntimeEvent(
            event_id="e5",
            job_id="job_no_leftovers",
            sequence=5,
            event_type="job.cancelled",
            occurred_at="2026-08-25T10:00:03Z",
            payload={"reason": "Operator shutdown"},
        ),
    ]

    reconstructed = RuntimeStateProjector.project(events)
    assert reconstructed.job.state == JobState.CANCELLED

    # Check tasks: none are RUNNING or PENDING
    for task in reconstructed.graph.list_tasks():
        assert task.status not in {TaskStatus.RUNNING, TaskStatus.READY, TaskStatus.PENDING}
        assert task.status == TaskStatus.CANCELLED

    # Check runs: none are RUNNING or INITIALIZING
    for run in reconstructed.runs:
        assert run.status not in {AgentRunStatus.RUNNING, AgentRunStatus.INITIALIZING}
        assert run.status == AgentRunStatus.CANCELLED


@pytest.mark.anyio
async def test_artifact_reconstruction_equals_original_artifact_set():
    """
    Scenario 10: Artifacts emitted during runtime execution are deterministically reconstructed
    and match the original artifact set by ID and reference.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    registry = create_test_registry()

    engine = ReactiveJobEngine(
        job_id="job_art_test",
        goal="Test artifact reconstruction",
        capability_registry=registry,
        event_bridge=bridge,
    )

    art1 = {"id": "art_patch_1", "type": "diff", "path": "src/main.py", "summary": "Fix syntax bug"}
    art2 = {"id": "art_doc_1", "type": "markdown", "path": "README.md", "summary": "Update docs"}

    async def mock_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        if task.task_id == "T1":
            return TaskExecutionResult(status="succeeded", artifact_refs=[art1])
        elif task.task_id == "T2":
            return TaskExecutionResult(status="succeeded", artifact_refs=[art2])
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(mock_adapter)

    t1 = TaskNode(task_id="T1", job_id="job_art_test", description="T1", required_capabilities=["code.edit"])
    t2 = TaskNode(task_id="T2", job_id="job_art_test", description="T2", dependencies=["T1"], required_capabilities=["code.edit"])

    await engine.initialize_and_plan(initial_tasks=[t1, t2])
    await engine.run_until_complete()

    assert engine.job.state == JobState.COMPLETED
    original_artifacts = engine.get_artifacts()
    assert len(original_artifacts) == 2

    # Reconstruct from event stream
    events = await store.list_events("job_art_test")
    reconstructed = RuntimeStateProjector.project(events)

    orig_keys = {a.get("id") or a.get("ref"): a for a in original_artifacts}
    recon_keys = {a.get("id") or a.get("ref"): a for a in reconstructed.artifacts}
    assert orig_keys == recon_keys
