"""
Phase 8.1 — Runtime Integration & Invariant Hardening Test Suite.
Verifies:
1. Production integration of ReactiveJobEngine as the authoritative orchestration path.
2. Demotion of static sprint loop to execution infrastructure.
3. Dependency deadlock & stalled graph detection without looping until max steps.
4. TaskGraph invariants: duplicate task rejection, cycle detection, safe removal.
5. Repair/replan terminal transition safety without InvalidStateTransitionError.
6. Actor availability & per-actor concurrency tracking (ACTOR_BUSY vs NO_CAPABLE_ACTOR).
7. Authoritative runtime limits on task attempts and max tasks.
8. Execution timeouts producing TIMED_OUT AgentRun status and structured failure.
9. Event-reactive scheduling unlocking newly-ready dependent work immediately.
10. Control plane endpoints truthfully exposing live ReactiveJobEngine state.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pytest
import time
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient
from main import app
from events.event_bus import RuntimeEventBus, event_bus
from capabilities.capabilities import CapabilityRegistry, Capability, default_capability_registry
from runtime.job_state import JobState, JobRecord, InvalidStateTransitionError
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.observations import ObservationRegistry, Observation
from runtime.execution import (
    ExecutionManager,
    AgentRun,
    AgentRunStatus,
    TaskExecutionResult,
    ActorAdapter,
)
from runtime.verification import (
    VerifierAdapter,
    VerificationResult,
    VerificationStatus,
    VerificationCheck,
)
from runtime.limits import RuntimeLimits
from runtime.replanning import (
    ReplanReason,
    ReplanRequest,
    ReplanResult,
    GraphMutation,
    GraphMutationType,
    BoundedReplanner,
)
from runtime.events import RuntimeEventBridge
from runtime.scheduler import ReactiveScheduler, DispatchDecision
from runtime.engine import ReactiveJobEngine
from runtime.hermes_adapter import HermesActorAdapter, HermesVerifierAdapter
from jobs.job_service import job_service
from jobs.job_launcher import job_launcher


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1 & 2: Production Integration & Authority
# -----------------------------------------------------------------------------

def test_post_jobs_creates_and_registers_real_reactive_engine(client):
    """
    Verifies that POST /jobs creates and registers a real ReactiveJobEngine with JobService.
    """
    sprint_id = "test-phase8-1-prod"
    sprint_file = Path(f"sprints/{sprint_id}.json")
    sprint_file.parent.mkdir(parents=True, exist_ok=True)
    sprint_file.write_text(json.dumps({
        "sprint_id": sprint_id,
        "name": "Phase 8.1 Production Integration Test",
        "phases": [
            {"name": "setup", "agent": "antigravity", "prompt_file": "prompts/setup.md"},
            {"name": "build", "agent": "gemini", "prompt_file": "prompts/build.md", "dependencies": ["setup"]},
        ]
    }))

    try:
        resp = client.post("/jobs", json={"sprintId": sprint_id, "dryRun": True})
        assert resp.status_code == 202
        data = resp.json()
        job_id = data["jobId"]
        assert job_id.startswith("run_")
        assert data["sprintId"] == sprint_id
        assert data.get("mode") == "reactive_runtime"

        # Verify engine is registered in JobService
        engine = job_service.get_engine(job_id)
        assert engine is not None
        assert isinstance(engine, ReactiveJobEngine)
        assert engine.job.job_id == job_id
        assert engine.graph.count() == 2

    finally:
        if sprint_file.exists():
            sprint_file.unlink()


def test_production_execution_uses_reactive_job_engine_state(client):
    """
    Proves production execution state transitions truthfully follow ReactiveJobEngine lifecycle.
    """
    sprint_id = "test-phase8-1-exec"
    sprint_file = Path(f"sprints/{sprint_id}.json")
    sprint_file.parent.mkdir(parents=True, exist_ok=True)
    sprint_file.write_text(json.dumps({
        "sprint_id": sprint_id,
        "name": "Reactive Execution Lifecycle",
        "phases": [
            {"name": "phase_1", "agent": "antigravity", "prompt_file": "prompts/p1.md"},
        ]
    }))

    try:
        resp = client.post("/jobs", json={"sprintId": sprint_id, "dryRun": True})
        assert resp.status_code == 202
        job_id = resp.json()["jobId"]

        # Wait briefly for execution loop to complete
        time.sleep(0.5)

        job_resp = client.get(f"/jobs/{job_id}")
        assert job_resp.status_code == 200
        job_dto = job_resp.json()
        assert job_dto["status"] == "COMPLETED"
        assert job_dto["progress"] == 1.0

        # Tasks endpoint
        tasks_resp = client.get(f"/jobs/{job_id}/tasks")
        assert tasks_resp.status_code == 200
        tasks = tasks_resp.json()
        assert len(tasks) == 1
        assert tasks[0]["status"] == "SUCCEEDED"

        # Runs endpoint
        runs_resp = client.get(f"/jobs/{job_id}/runs")
        assert runs_resp.status_code == 200
        runs = runs_resp.json()
        assert len(runs) >= 1
        assert runs[0]["status"] == "succeeded"

    finally:
        if sprint_file.exists():
            sprint_file.unlink()


# -----------------------------------------------------------------------------
# 3: Dependency Deadlock & Stalled Graph Detection
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_dependency_failure_creates_stalled_graph_and_blocks_without_max_steps():
    """
    When dependency task fails and exhausts retries, dependent task cannot run.
    Engine detects stalled graph immediately and transitions to BLOCKED without cycling max_steps.
    """
    bridge = RuntimeEventBridge()
    limits = RuntimeLimits(max_task_attempts=1, max_replans_per_job=0)
    engine = ReactiveJobEngine(
        job_id="job_stalled_test",
        goal="Demonstrate stalled graph detection",
        limits=limits,
        event_bridge=bridge,
    )

    t1 = TaskNode(task_id="t1", job_id=engine.job.job_id, description="Failing task", required_capabilities=["implementation"], max_attempts=1)
    t2 = TaskNode(task_id="t2", job_id=engine.job.job_id, description="Dependent task", dependencies=["t1"], required_capabilities=["implementation"])

    # Register adapter where t1 fails
    async def failing_adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]):
        return TaskExecutionResult(status="failed", error="Fatal failure in t1")

    engine.execution_manager.set_default_adapter(failing_adapter)
    await engine.initialize_and_plan(initial_tasks=[t1, t2])

    # Run step 1: t1 runs and fails
    should_continue = await engine.step()

    # Graph is now stalled (t1 failed, t2 blocked on t1, no runnable tasks)
    assert engine.graph.is_stalled() is True
    assert engine.graph.has_runnable_tasks() is False
    assert engine.graph.has_running_tasks() is False
    assert len(engine.graph.find_dependency_blocked_tasks()) == 1

    # Run step 2: engine recognizes stalled state, attempts replan, exhausts replans -> BLOCKED immediately
    should_continue_2 = await engine.step()
    assert should_continue_2 is False
    assert engine.state == JobState.BLOCKED
    assert "Task graph blocked" in (engine.job.blocked_reason or "") or "stalled" in (engine.job.blocked_reason or "").lower() or "exhausted" in (engine.job.blocked_reason or "").lower()


# -----------------------------------------------------------------------------
# 4 & 5 & 6: TaskGraph Invariants (Duplicates, Cycles, Safe Removal)
# -----------------------------------------------------------------------------

def test_duplicate_task_id_rejected():
    """TaskGraph.add_task must reject duplicate task IDs with ValueError."""
    graph = TaskGraph(job_id="job_dup")
    t1 = TaskNode(task_id="task_alpha", description="Original task")
    graph.add_task(t1)

    t1_dup = TaskNode(task_id="task_alpha", description="Duplicate task overwrite attempt")
    with pytest.raises(ValueError, match="already exists"):
        graph.add_task(t1_dup)


def test_dependency_cycle_rejected():
    """TaskGraph.add_dependency must reject cycles immediately."""
    graph = TaskGraph(job_id="job_cycle")
    graph.add_task(TaskNode(task_id="A"))
    graph.add_task(TaskNode(task_id="B"))
    graph.add_task(TaskNode(task_id="C"))

    graph.add_dependency("B", "A")  # B depends on A
    graph.add_dependency("C", "B")  # C depends on B

    # Attempting A -> C creates cycle A -> C -> B -> A
    with pytest.raises(ValueError, match="cycle detected|circular dependency"):
        graph.add_dependency("A", "C")

    # Self dependency
    with pytest.raises(ValueError, match="cannot depend on itself"):
        graph.add_dependency("A", "A")


def test_safe_task_removal_preserves_dependents():
    """TaskGraph.remove_task cannot remove a task if other tasks depend on it."""
    graph = TaskGraph(job_id="job_safe_remove")
    graph.add_task(TaskNode(task_id="base_task"))
    graph.add_task(TaskNode(task_id="dependent_task", dependencies=["base_task"]))

    with pytest.raises(ValueError, match="Cannot remove task.*dependent task"):
        graph.remove_task("base_task")

    # Superseding is the safe mechanism
    graph.supersede_task("base_task", reason="Replaced by new architecture")
    assert graph.get_task("base_task").status == TaskStatus.SUPERSEDED


# -----------------------------------------------------------------------------
# 7: Repair / Replan Terminal State Safety
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_repair_exhausted_replan_budget_terminates_blocked_without_invalid_transition():
    """
    During VERIFYING -> REPAIRING, if replanning exhausts replan limit,
    engine must terminate in BLOCKED and NOT attempt an illegal transition to EXECUTING.
    """
    limits = RuntimeLimits(max_replans_per_job=0, max_repairs_per_job=2)

    # Verifier that returns REPAIRABLE
    class RepairableVerifier(VerifierAdapter):
        async def verify(self, job, graph, artifacts, context=None):
            return VerificationResult(
                status=VerificationStatus.REPAIRABLE,
                summary="Tests failed with minor syntax errors",
                repair_recommendations=[TaskNode(task_id="repair_1", description="Fix syntax")],
            )

    # Planner that triggers replan
    class DummyPlanner:
        async def plan(self, req: ReplanRequest):
            return ReplanResult(mutations=[], explanation="No plan possible")

    engine = ReactiveJobEngine(
        job_id="job_repair_budget_exhausted",
        goal="Test repair terminal safety",
        limits=limits,
        verifier=RepairableVerifier(),
        planner=DummyPlanner(),
    )

    t1 = TaskNode(task_id="t1", job_id=engine.job.job_id, description="Initial task")
    await engine.initialize_and_plan(initial_tasks=[t1])

    # Mark t1 succeeded
    engine.graph.mark_success("t1")

    # Step 1 transitions EXECUTING -> VERIFYING
    should_continue_1 = await engine.step()
    assert should_continue_1 is True
    assert engine.state == JobState.VERIFYING

    # Step 2 runs VERIFYING -> REPAIRING -> request_replan (replan budget exhausted) -> BLOCKED
    should_continue_2 = await engine.step()

    # Must terminate cleanly in BLOCKED without InvalidStateTransitionError
    assert engine.state == JobState.BLOCKED
    assert should_continue_2 is False


# -----------------------------------------------------------------------------
# 8 & 9: Actor Availability & Per-Actor Concurrency
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_actor_busy_defers_task_without_blocking():
    """
    When an actor is currently executing a task, another task requiring the same
    actor remains READY (deferred) and is NOT marked BLOCKED.
    """
    caps = CapabilityRegistry()
    caps.register_capability(Capability(id="code.python"))
    caps.register_actor({"id": "gemini", "capabilities": ["code.python"]})

    scheduler = ReactiveScheduler(capability_registry=caps, default_actor_concurrency=1)
    exec_mgr = ExecutionManager()

    # Block execution until release event
    unblock_event = asyncio.Event()

    async def blocking_adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]):
        await unblock_event.wait()
        return TaskExecutionResult(status="succeeded")

    exec_mgr.register_adapter("gemini", blocking_adapter)

    graph = TaskGraph(job_id="job_concurrency")
    t1 = TaskNode(task_id="t1", assigned_actor="gemini", required_capabilities=["code.python"])
    t2 = TaskNode(task_id="t2", assigned_actor="gemini", required_capabilities=["code.python"])
    graph.add_task(t1)
    graph.add_task(t2)

    # Launch ready tasks
    launched = await scheduler.schedule_ready_tasks(graph, exec_mgr)

    # t1 should be running on gemini
    assert len(launched) == 1
    assert graph.get_task("t1").status == TaskStatus.RUNNING
    assert graph.get_task("t2").status == TaskStatus.PENDING  # t2 was deferred because gemini is busy, NOT BLOCKED!
    assert scheduler.is_actor_available("gemini") is False

    # Unblock t1
    unblock_event.set()
    await asyncio.gather(*launched)

    # gemini is now released
    assert scheduler.is_actor_available("gemini") is True

    # Next scheduling cycle now dispatches t2
    launched_2 = await scheduler.schedule_ready_tasks(graph, exec_mgr)
    assert len(launched_2) == 1
    assert graph.get_task("t2").status == TaskStatus.RUNNING
    await asyncio.gather(*launched_2)
    assert graph.get_task("t2").status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_no_capable_actor_marks_blocked_vs_actor_busy_defers():
    """
    Distinguishes NO_CAPABLE_ACTOR (marks task BLOCKED) from ACTOR_BUSY (defers task).
    """
    caps = CapabilityRegistry()
    caps.register_capability(Capability(id="code.python"))
    caps.register_actor({"id": "gemini", "capabilities": ["code.python"]})

    scheduler = ReactiveScheduler(capability_registry=caps, default_actor_concurrency=1)
    exec_mgr = ExecutionManager()

    graph = TaskGraph(job_id="job_no_actor")
    t_impossible = TaskNode(task_id="t_imp", required_capabilities=["non_existent_capability"])
    graph.add_task(t_impossible)

    await scheduler.schedule_ready_tasks(graph, exec_mgr)
    # Impossible capability marks task BLOCKED
    assert graph.get_task("t_imp").status == TaskStatus.BLOCKED


@pytest.mark.anyio
async def test_globally_independent_tasks_execute_concurrently_across_distinct_actors():
    """
    Multiple independent tasks requiring different capabilities execute
    concurrently on distinct actors up to global concurrency limit.
    """
    caps = CapabilityRegistry()
    caps.register_capability(Capability(id="code.python"))
    caps.register_capability(Capability(id="review.code"))
    caps.register_actor({"id": "gemini", "capabilities": ["code.python"]})
    caps.register_actor({"id": "claude", "capabilities": ["review.code"]})

    scheduler = ReactiveScheduler(capability_registry=caps, limits=RuntimeLimits(concurrency_limit=3))
    exec_mgr = ExecutionManager()

    active_actors = set()
    concurrency_peak = 0

    async def mock_adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]):
        nonlocal concurrency_peak
        active_actors.add(run.actor_id)
        concurrency_peak = max(concurrency_peak, len(active_actors))
        await asyncio.sleep(0.05)
        active_actors.remove(run.actor_id)
        return TaskExecutionResult(status="succeeded")

    exec_mgr.register_adapter("gemini", mock_adapter)
    exec_mgr.register_adapter("claude", mock_adapter)

    graph = TaskGraph(job_id="job_parallel")
    t1 = TaskNode(task_id="t1", required_capabilities=["code.python"])
    t2 = TaskNode(task_id="t2", required_capabilities=["review.code"])
    graph.add_task(t1)
    graph.add_task(t2)

    tasks = await scheduler.schedule_ready_tasks(graph, exec_mgr)
    assert len(tasks) == 2
    await asyncio.gather(*tasks)

    assert concurrency_peak == 2
    assert graph.is_all_completed() is True


# -----------------------------------------------------------------------------
# 10: Authoritative Runtime Limits
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_max_task_attempts_runtime_limit_overrides_task_values():
    """
    RuntimeLimits.max_task_attempts strictly caps task.max_attempts.
    """
    limits = RuntimeLimits(max_task_attempts=2)
    engine = ReactiveJobEngine(
        job_id="job_limits",
        goal="Test max attempts limit enforcement",
        limits=limits,
    )

    t1 = TaskNode(task_id="t1", max_attempts=10, required_capabilities=["implementation"])
    await engine.initialize_and_plan(initial_tasks=[t1])

    # Task max_attempts must be capped to 2
    assert engine.graph.get_task("t1").max_attempts == 2


# -----------------------------------------------------------------------------
# 11: Execution Timeouts
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_execution_timeout_produces_timed_out_run_and_failed_result():
    """
    When adapter execution exceeds timeout_seconds, ExecutionManager marks run TIMED_OUT
    and returns structured failed TaskExecutionResult without crashing scheduler.
    """
    exec_mgr = ExecutionManager()

    async def slow_adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]):
        await asyncio.sleep(2.0)
        return TaskExecutionResult(status="succeeded")

    exec_mgr.register_adapter("slow_actor", slow_adapter)

    task = TaskNode(
        task_id="t_timeout",
        job_id="job_timeout",
        assigned_actor="slow_actor",
        metadata={"timeout_seconds": 0.05},
    )

    result = await exec_mgr.execute(task=task, actor_id="slow_actor")

    assert result.status == "failed"
    assert result.exit_reason == "timeout"
    assert "timed out" in str(result.error)

    runs = exec_mgr.list_runs_for_task("t_timeout")
    assert len(runs) == 1
    assert runs[0].status == AgentRunStatus.TIMED_OUT
    assert runs[0].exit_reason == "timeout"


# -----------------------------------------------------------------------------
# 12: Event-Reactive Scheduling (FIRST_COMPLETED Unlocks Dependent Work)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_event_reactive_scheduling_unlocks_dependent_task_immediately():
    """
    T2 is fast (0.05s) and T3 is slow (0.4s).
    T4 depends on T2.
    When T2 finishes, engine reacts immediately and starts T4 while T3 is still running.
    """
    engine = ReactiveJobEngine(
        job_id="job_reactive_speed",
        goal="Test first-completed event reactivity",
        limits=RuntimeLimits(concurrency_limit=5),
    )

    timestamps = {}

    async def variable_duration_adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]):
        t_id = task.task_id
        timestamps[f"{t_id}_start"] = time.time()
        if t_id == "T2":
            await asyncio.sleep(0.05)
        elif t_id == "T3":
            await asyncio.sleep(0.35)
        elif t_id == "T4":
            await asyncio.sleep(0.05)
        timestamps[f"{t_id}_end"] = time.time()
        return TaskExecutionResult(status="succeeded")

    engine.execution_manager.set_default_adapter(variable_duration_adapter)
    engine.scheduler.default_actor_concurrency = 5

    t2 = TaskNode(task_id="T2", job_id=engine.job.job_id, required_capabilities=["implementation"])
    t3 = TaskNode(task_id="T3", job_id=engine.job.job_id, required_capabilities=["implementation"])
    t4 = TaskNode(task_id="T4", job_id=engine.job.job_id, dependencies=["T2"], required_capabilities=["implementation"])

    await engine.initialize_and_plan(initial_tasks=[t2, t3, t4])

    # Drive engine to completion
    await engine.run_until_complete(max_steps=20)

    assert engine.state == JobState.COMPLETED
    assert engine.graph.is_all_completed() is True

    # Verify that T4 started BEFORE T3 finished
    t2_end = timestamps["T2_end"]
    t4_start = timestamps["T4_start"]
    t3_end = timestamps["T3_end"]

    assert t4_start >= t2_end - 0.01, "T4 should start after T2 completes"
    assert t4_start < t3_end, f"T4 started ({t4_start}) AFTER T3 ended ({t3_end}); event-reactive scheduling failed!"


# -----------------------------------------------------------------------------
# 13: JobService Truthful Endpoints
# -----------------------------------------------------------------------------

def test_job_service_endpoints_expose_live_production_engine_truthfully(client):
    """
    GET /jobs/{id}, /tasks, /runs, /observations, /events truthfully reflect live ReactiveJobEngine.
    """
    sprint_id = "test-phase8-1-truth"
    sprint_file = Path(f"sprints/{sprint_id}.json")
    sprint_file.parent.mkdir(parents=True, exist_ok=True)
    sprint_file.write_text(json.dumps({
        "sprint_id": sprint_id,
        "name": "Truthful Inspection Sprint",
        "phases": [
            {"name": "inspect", "agent": "gemini", "prompt_file": "prompts/inspect.md"},
        ]
    }))

    try:
        resp = client.post("/jobs", json={"sprintId": sprint_id, "dryRun": True})
        assert resp.status_code == 202
        job_id = resp.json()["jobId"]

        time.sleep(0.4)

        # GET /jobs/{id}
        j_resp = client.get(f"/jobs/{job_id}")
        assert j_resp.status_code == 200
        assert j_resp.json()["id"] == job_id
        assert j_resp.json()["status"] == "COMPLETED"

        # GET /jobs/{id}/tasks
        t_resp = client.get(f"/jobs/{job_id}/tasks")
        assert t_resp.status_code == 200
        tasks = t_resp.json()
        assert len(tasks) == 1
        assert tasks[0]["taskId"] == "inspect"
        assert tasks[0]["status"] == "SUCCEEDED"

        # GET /jobs/{id}/runs
        r_resp = client.get(f"/jobs/{job_id}/runs")
        assert r_resp.status_code == 200
        assert len(r_resp.json()) >= 1

        # GET /jobs/{id}/observations
        o_resp = client.get(f"/jobs/{job_id}/observations")
        assert o_resp.status_code == 200
        assert isinstance(o_resp.json(), list)

        # GET /jobs/{id}/events
        e_resp = client.get(f"/jobs/{job_id}/events")
        assert e_resp.status_code == 200
        events = e_resp.json()
        assert len(events) >= 1
        event_kinds = [e["kind"] for e in events]
        assert "job.created" in event_kinds

    finally:
        if sprint_file.exists():
            sprint_file.unlink()
