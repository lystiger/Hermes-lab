"""
Phase 8.1.4 — Follow-Up Observation Triggering & Cancellation Safety Test Suite.
Verifies:
1. Observations flagged requires_follow_up drive discovery replanning on their own.
2. Discovery replans are opportunistic: adding nothing does not BLOCK a healthy job.
3. Each observation triggers discovery at most once.
4. Cancellation stops in-flight execution, marks the graph, and releases actors.
5. run_until_complete never leaves worker tasks running past the run loop.
6. JobLauncher.cancel propagates cancellation into the engine.
"""

import asyncio
import pytest
from typing import Any, Dict, List, Optional

from capabilities.capabilities import CapabilityRegistry
from personas.persona import resolve_agent_profile
from runtime.engine import ReactiveJobEngine
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.job_state import JobState
from runtime.limits import RuntimeLimits
from runtime.observations import Observation, ObservationRegistry
from runtime.replanning import ProductionPlannerAdapter, ReplanResult
from runtime.task_graph import TaskNode, TaskStatus


def _registry(actor_id: str = "worker", capabilities: Optional[List[str]] = None) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    profile = resolve_agent_profile(actor_id)
    profile.capabilities = list(capabilities or ["implementation"])
    registry.register_actor(profile)
    return registry


def _engine(**kwargs) -> ReactiveJobEngine:
    defaults = dict(
        job_id="job_814",
        goal="Phase 8.1.4",
        capability_registry=_registry(),
        observation_registry=ObservationRegistry(),
        limits=RuntimeLimits(max_replans_per_job=3, max_task_attempts=1),
    )
    defaults.update(kwargs)
    return ReactiveJobEngine(**defaults)


def _task(task_id: str, actor: str = "worker") -> TaskNode:
    return TaskNode(
        task_id=task_id,
        job_id="job_814",
        description=f"Task {task_id}",
        assigned_actor=actor,
        required_capabilities=["implementation"],
    )


# -----------------------------------------------------------------------------
# 1-3. Automatic follow-up observation triggering
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_followup_observation_triggers_discovery_without_explicit_metadata():
    """
    An observation flagged requires_follow_up drives a discovery replan on its own; the
    adapter does not also have to set trigger_replan on the execution result.
    """
    engine = _engine(planner=ProductionPlannerAdapter(limits=RuntimeLimits(max_tasks_per_job=20)))

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        if task.task_id != "scan":
            return TaskExecutionResult(status="succeeded")
        return TaskExecutionResult(
            status="succeeded",
            observations=[
                Observation(
                    observation_id="obs_needs_migration",
                    job_id="job_814",
                    task_id="scan",
                    kind="discovery",
                    content="Schema drift detected",
                    metadata={
                        "requires_follow_up": True,
                        "follow_up_task": "Write the missing migration",
                        "required_capabilities": ["implementation"],
                    },
                )
            ],
            # Deliberately no trigger_replan metadata.
        )

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("scan")])
    await engine.step()

    follow_up = engine.graph.get_task("discover_obs_needs_migration")
    assert follow_up is not None, "follow-up observation did not expand the graph"
    assert follow_up.description == "Write the missing migration"
    assert follow_up.dependencies == ["scan"]
    assert engine.job.replan_count == 1
    assert engine.state == JobState.EXECUTING


@pytest.mark.anyio
async def test_discovery_replan_that_adds_nothing_does_not_block_the_job():
    """
    A discovery replan is opportunistic. A planner with nothing to add means "no extra work
    is needed", not "the job is stuck", so the job must not transition to BLOCKED.
    """
    class EmptyPlanner:
        async def plan(self, request):
            return ReplanResult(mutations=[], explanation="nothing to add", should_continue=False)

    engine = _engine(planner=EmptyPlanner())

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        return TaskExecutionResult(
            status="succeeded",
            observations=[
                Observation(
                    observation_id="obs_noop",
                    job_id="job_814",
                    task_id=task.task_id,
                    kind="discovery",
                    content="Something worth a look",
                    metadata={"requires_follow_up": True},
                )
            ],
        )

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("solo")])
    await engine.step()

    assert engine.state != JobState.BLOCKED
    assert engine.graph.get_task("solo").status == TaskStatus.SUCCEEDED

    # And the job still reaches its normal terminal state.
    await engine.run_until_complete(max_steps=10)
    assert engine.state == JobState.COMPLETED


@pytest.mark.anyio
async def test_failure_replan_still_blocks_when_planner_cannot_proceed():
    """The opportunistic path must not weaken failure-driven replanning."""
    class EmptyPlanner:
        async def plan(self, request):
            return ReplanResult(mutations=[], explanation="no recovery available", should_continue=False)

    engine = _engine(planner=EmptyPlanner())

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        return TaskExecutionResult(status="failed", error="boom")

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("doomed")])
    await engine.run_until_complete(max_steps=10)

    assert engine.state == JobState.BLOCKED


@pytest.mark.anyio
async def test_same_observation_triggers_discovery_only_once():
    """Re-triggering on an already-expanded observation would burn replan budget for nothing."""
    plan_calls: List[str] = []

    class CountingPlanner(ProductionPlannerAdapter):
        async def plan(self, request):
            plan_calls.append(str(request.reason))
            return await super().plan(request)

    engine = _engine(planner=CountingPlanner(limits=RuntimeLimits(max_tasks_per_job=20)))

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        # Every task re-emits the same observation id.
        return TaskExecutionResult(
            status="succeeded",
            observations=[
                Observation(
                    observation_id="obs_repeat",
                    job_id="job_814",
                    task_id=task.task_id,
                    kind="discovery",
                    content="Recurring finding",
                    metadata={"requires_follow_up": True, "follow_up_task": "Handle recurring finding"},
                )
            ],
        )

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("first")])
    await engine.run_until_complete(max_steps=15)

    discovery_replans = [r for r in plan_calls if "observation" in r.lower() or "discovery" in r.lower()]
    assert len(discovery_replans) == 1, plan_calls
    assert engine.job.replan_count == 1
    assert engine.state == JobState.COMPLETED


@pytest.mark.anyio
async def test_routine_observations_do_not_trigger_replanning():
    """Ordinary observations (every task emits some) must not spend replan budget."""
    engine = _engine(planner=ProductionPlannerAdapter())

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        return TaskExecutionResult(
            status="succeeded",
            observations=[
                Observation(
                    job_id="job_814",
                    task_id=task.task_id,
                    kind="execution_output",
                    content="Agent completed with exit code 0",
                    metadata={"exit_code": 0},
                )
            ],
        )

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("quiet")])
    await engine.run_until_complete(max_steps=10)

    assert engine.job.replan_count == 0
    assert engine.state == JobState.COMPLETED


# -----------------------------------------------------------------------------
# 4-6. Cancellation safety
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cancel_stops_inflight_execution_and_releases_actors():
    """
    Cancelling a job with work in flight transitions to CANCELLED, marks the running task
    cancelled, stops the worker, and releases the actor slot.
    """
    engine = _engine()
    entered = asyncio.Event()
    cancelled_inside = asyncio.Event()

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled_inside.set()
            raise
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("long_running")])

    step_task = asyncio.create_task(engine.step())
    await asyncio.wait_for(entered.wait(), timeout=5)

    assert await engine.cancel("Operator pulled the plug") is True

    assert engine.state == JobState.CANCELLED
    assert engine.graph.get_task("long_running").status == TaskStatus.CANCELLED
    await asyncio.wait_for(cancelled_inside.wait(), timeout=5)

    # The scheduler released the actor and its running-task slot.
    assert engine.scheduler.active_running_count == 0
    assert engine.scheduler.is_actor_available("worker") is True
    assert engine._active_async_tasks == set()

    step_task.cancel()
    await asyncio.gather(step_task, return_exceptions=True)

    # Cancelling an already-terminal job is a no-op.
    assert await engine.cancel("again") is False


@pytest.mark.anyio
async def test_run_until_complete_leaves_no_worker_tasks_running():
    """A finished run must not leave workers mutating state behind a job already reported done."""
    engine = _engine()
    engine.limits.concurrency_limit = 4

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        await asyncio.sleep(0.01 if task.task_id == "fast" else 0.05)
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("fast"), _task("slow")])
    await engine.run_until_complete(max_steps=15)

    assert engine.is_terminal
    assert engine._active_async_tasks == set()
    assert engine.scheduler.active_running_count == 0


@pytest.mark.anyio
async def test_cancelled_run_loop_stops_workers_and_marks_job_cancelled():
    """Cancelling the driving task stops the workers instead of orphaning them."""
    engine = _engine()
    entered = asyncio.Event()
    cancelled_inside = asyncio.Event()

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled_inside.set()
            raise
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("long_running")])

    runner = asyncio.create_task(engine.run_until_complete(max_steps=20))
    await asyncio.wait_for(entered.wait(), timeout=5)

    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner

    await asyncio.wait_for(cancelled_inside.wait(), timeout=5)
    assert engine.state == JobState.CANCELLED
    assert engine._active_async_tasks == set()
    assert engine.scheduler.active_running_count == 0


@pytest.mark.anyio
async def test_request_cancel_is_safe_from_outside_the_event_loop():
    """
    The control plane cancels synchronously. request_cancel must transition and signal the
    workers without needing to await, so JobLauncher.cancel can call it directly.
    """
    engine = _engine()
    entered = asyncio.Event()

    async def adapter(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]) -> TaskExecutionResult:
        entered.set()
        await asyncio.sleep(30)
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(adapter)
    await engine.initialize_and_plan(initial_tasks=[_task("long_running")])

    step_task = asyncio.create_task(engine.step())
    await asyncio.wait_for(entered.wait(), timeout=5)

    # Synchronous call, no await.
    assert engine.request_cancel("cancelled by control plane") is True
    assert engine.state == JobState.CANCELLED
    assert engine.graph.get_task("long_running").status == TaskStatus.CANCELLED

    await engine._cancel_active_tasks("drain")
    assert engine.scheduler.active_running_count == 0

    step_task.cancel()
    await asyncio.gather(step_task, return_exceptions=True)


def test_launcher_cancel_propagates_into_engine(monkeypatch):
    """JobLauncher.cancel drives engine cancellation, not just the driving task."""
    from jobs.job_launcher import job_launcher
    from jobs.job_service import job_service

    engine = _engine(job_id="job_launcher_cancel")
    job_service.register_engine(engine)

    assert job_launcher.cancel("job_launcher_cancel") is True
    assert engine.state == JobState.CANCELLED

    # Already terminal: nothing further to cancel.
    assert job_launcher.cancel("job_launcher_cancel") is False
