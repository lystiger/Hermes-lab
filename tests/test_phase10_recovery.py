import asyncio
from datetime import datetime, timezone
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.execution import AgentRun, AgentRunStatus, TaskExecutionResult, ExecutionManager
from runtime.observations import Observation
from runtime.verification import VerificationResult, VerificationStatus
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.storage.projector import RuntimeStateProjector
from runtime.lease import InMemoryJobLeaseStore
from runtime.recovery import RecoveryManager, RecoveryDisposition, InterruptedTaskReconciler
from runtime.engine import ReactiveJobEngine
from capabilities.capabilities import CapabilityRegistry


def create_test_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register_actor({
        "id": "actor_code",
        "name": "Code Actor",
        "capabilities": ["code.edit", "code.review"],
    })
    reg.register_actor({
        "id": "actor_test",
        "name": "Test Actor",
        "capabilities": ["test.run"],
    })
    return reg


@pytest.mark.anyio
async def test_rehydrate_executing_dag_from_durable_events():
    """
    Test A & C: Rehydrate an EXECUTING DAG from durable events.
    Verifies SUCCEEDED, READY, and PENDING task statuses and dependencies are accurately restored.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    # 1. Simulate prior execution
    job = JobRecord(job_id="job_rec_1", goal="Build authentication subsystem")
    await bridge.emit_job_created(job)
    job.state = JobState.PLANNING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    t1 = TaskNode(task_id="T1", job_id="job_rec_1", description="DB schema", status=TaskStatus.SUCCEEDED)
    t2 = TaskNode(task_id="T2", job_id="job_rec_1", description="API route", status=TaskStatus.READY, dependencies=["T1"])
    t3 = TaskNode(task_id="T3", job_id="job_rec_1", description="Frontend form", status=TaskStatus.PENDING, dependencies=["T2"])

    await bridge.emit_task_created(t1)
    await bridge.emit_task_created(t2)
    await bridge.emit_task_created(t3)
    await bridge.emit_task_completed(t1, actor_id="actor_code")
    await bridge.emit_task_ready(t2)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.PLANNING)

    # 2. Recover and rehydrate engine
    engine, metrics = await ReactiveJobEngine.resume(
        job_id="job_rec_1",
        event_store=store,
        capability_registry=create_test_registry(),
    )

    assert engine.job.state == JobState.EXECUTING
    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert engine.graph.get_task("T2").status == TaskStatus.READY
    assert engine.graph.get_task("T3").status == TaskStatus.PENDING
    assert engine.graph.get_task("T2").dependencies == ["T1"]
    assert engine.graph.get_task("T3").dependencies == ["T2"]
    assert "T1" in metrics.preserved_tasks


@pytest.mark.anyio
async def test_succeeded_tasks_never_rerun_after_resume():
    """
    Test B: SUCCEEDED tasks are not re-executed upon resuming an engine.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    job = JobRecord(job_id="job_rec_succeeded", goal="Test no rerun")
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    t1 = TaskNode(task_id="T1", job_id="job_rec_succeeded", description="Task 1", required_capabilities=["code.edit"])
    await bridge.emit_task_created(t1)
    await bridge.emit_task_completed(t1, actor_id="actor_code")

    t2 = TaskNode(task_id="T2", job_id="job_rec_succeeded", description="Task 2", dependencies=["T1"], required_capabilities=["code.edit"])
    await bridge.emit_task_created(t2)

    executed_tasks = []

    async def tracking_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        executed_tasks.append(task.task_id)
        return TaskExecutionResult(status="succeeded")

    engine, _ = await ReactiveJobEngine.resume(
        job_id="job_rec_succeeded",
        event_store=store,
        capability_registry=create_test_registry(),
    )
    engine.set_default_execution_adapter(tracking_adapter)

    await engine.step()

    # T1 must NOT have run; only T2 should run
    assert "T1" not in executed_tasks
    assert "T2" in executed_tasks
    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert engine.graph.get_task("T2").status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_interrupted_running_task_without_side_effects_is_safely_requeued():
    """
    Test D: An interrupted RUNNING task with no commits or integration side effects
    is safely requeued (status set to READY).
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    job = JobRecord(job_id="job_rec_requeue", goal="Test safe requeue")
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    t1 = TaskNode(task_id="T1", job_id="job_rec_requeue", description="T1", required_capabilities=["code.edit"])
    await bridge.emit_task_created(t1)
    await bridge.emit_task_started(t1, actor_id="actor_code")
    # Process crash occurred while T1 was RUNNING

    engine, metrics = await ReactiveJobEngine.resume(
        job_id="job_rec_requeue",
        event_store=store,
        capability_registry=create_test_registry(),
    )

    assert "T1" in metrics.requeued_tasks
    assert engine.graph.get_task("T1").status == TaskStatus.READY


@pytest.mark.anyio
async def test_integrated_work_is_reconciled_instead_of_rerun():
    """
    Test E: If a task has evidence of committed/integrated side effects, recovery
    reconciles it as SUCCEEDED rather than repeating the model work.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    job = JobRecord(job_id="job_rec_reconcile", goal="Test reconcile evidence")
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    t1 = TaskNode(
        task_id="T1",
        job_id="job_rec_reconcile",
        description="T1",
        metadata={"commit_sha": "abc1234", "integrated": True},
    )
    await bridge.emit_task_created(t1)
    await bridge.emit_task_started(t1, actor_id="actor_code")

    engine, metrics = await ReactiveJobEngine.resume(
        job_id="job_rec_reconcile",
        event_store=store,
        capability_registry=create_test_registry(),
    )

    assert "T1" in metrics.reconciled_tasks
    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_attempts_observations_and_counters_survive_restart():
    """
    Test F & G: Attempts, replan_count, repair_count, and observations survive crash and rehydration.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    job = JobRecord(job_id="job_rec_counters", goal="Test counters")
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)
    job.state = JobState.PLANNING
    await bridge.emit_job_state_changed(job, previous_state=JobState.EXECUTING)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.PLANNING)
    job.state = JobState.REPAIRING
    await bridge.emit_job_state_changed(job, previous_state=JobState.EXECUTING)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.REPAIRING)

    t1 = TaskNode(task_id="T1", job_id="job_rec_counters", description="T1", attempt=1)
    await bridge.emit_task_created(t1)
    await bridge.emit_task_started(t1, actor_id="actor_code")
    await bridge.emit_task_failed(t1, actor_id="actor_code", error="Transient error")

    obs = Observation(
        observation_id="obs_1",
        job_id="job_rec_counters",
        kind="discovery",
        content="Discovered legacy route",
        task_id="T1",
    )
    await bridge.emit_observation_created(obs)

    engine, _ = await ReactiveJobEngine.resume(
        job_id="job_rec_counters",
        event_store=store,
        capability_registry=create_test_registry(),
    )

    assert engine.job.replan_count == 1
    assert engine.job.repair_count == 1
    assert engine.graph.get_task("T1").attempt == 1
    assert engine.observation_registry.get("obs_1") is not None
    assert engine.observation_registry.get("obs_1").content == "Discovered legacy route"


@pytest.mark.anyio
async def test_terminal_jobs_cannot_resume():
    """
    Test H & I: COMPLETED and CANCELLED jobs reject resumption with ValueError.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    # 1. Cancelled Job
    job_c = JobRecord(job_id="job_rec_cancelled", goal="Cancelled")
    await bridge.emit_job_created(job_c)
    job_c.state = JobState.CANCELLED
    await bridge.emit_job_state_changed(job_c, previous_state=JobState.CREATED)

    with pytest.raises(ValueError, match="Cannot resume terminal job"):
        await ReactiveJobEngine.resume(job_id="job_rec_cancelled", event_store=store)

    # 2. Completed Job
    job_done = JobRecord(job_id="job_rec_done", goal="Completed")
    await bridge.emit_job_created(job_done)
    job_done.state = JobState.COMPLETED
    await bridge.emit_job_state_changed(job_done, previous_state=JobState.CREATED)

    with pytest.raises(ValueError, match="Cannot resume terminal job"):
        await ReactiveJobEngine.resume(job_id="job_rec_done", event_store=store)


@pytest.mark.anyio
async def test_single_active_executor_and_lease_takeover():
    """
    Test N & O: Two runtime instances cannot actively execute the same job simultaneously,
    and lease expiration allows safe takeover.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    lease_store = InMemoryJobLeaseStore()

    job = JobRecord(job_id="job_rec_lease", goal="Test lease")
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)
    t1 = TaskNode(task_id="T1", job_id="job_rec_lease", description="T1")
    await bridge.emit_task_created(t1)

    manager = RecoveryManager(event_store=store, lease_store=lease_store)

    # 1. Instance A acquires lease
    engine_a, _ = await manager.recover_and_rehydrate(
        job_id="job_rec_lease",
        owner_id="node_a",
    )
    assert engine_a is not None

    # 2. Instance B attempts concurrent resume -> rejected
    with pytest.raises(RuntimeError, match="active lease held by another executor"):
        await manager.recover_and_rehydrate(
            job_id="job_rec_lease",
            owner_id="node_b",
        )

    # 3. Fast-forward expiration
    lease = await lease_store.get_lease("job_rec_lease")
    assert lease is not None
    # Simulate expiration by setting lease_until in the past
    lease.lease_until = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    lease_store._leases["job_rec_lease"] = lease

    # 4. Instance B takes over safely after expiration
    engine_b, _ = await manager.recover_and_rehydrate(
        job_id="job_rec_lease",
        owner_id="node_b",
    )
    assert engine_b is not None
    updated_lease = await lease_store.get_lease("job_rec_lease")
    assert updated_lease.owner_id == "node_b"
