"""A builder that made no changes is not given the same work again when another agent can do it.

Regression: headless Antigravity stopped at its first disallowed command, produced no file changes,
and every fallback (fix_fix_fix_*) went back to Antigravity until the job ran out of replans.
"""
import asyncio
from typing import Any, Dict

import pytest

from capabilities.capabilities import Capability, CapabilityRegistry
from runtime.execution import AgentRun, ExecutionManager, TaskExecutionResult
from runtime.replanning import GraphMutationType, ProductionPlannerAdapter, ReplanReason, ReplanRequest
from runtime.scheduler import ReactiveScheduler
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus

NO_CHANGES = "FAILED_NO_CHANGES: builder task 'build' produced no file changes."


def failed_builder(error=NO_CHANGES, actor="antigravity", **metadata):
    task = TaskNode(task_id="build", job_id="job_nc", description="Write a.txt", assigned_actor=actor,
                    required_capabilities=["implementation"], metadata={"role": "builder", **metadata},
                    max_attempts=1)
    task.attempt, task.error = 1, error
    return task


async def fallback_async(failed):
    result = await ProductionPlannerAdapter().plan(ReplanRequest(
        job_id="job_nc", goal="g", reason=ReplanReason.TASK_FAILURE, completed_tasks=[],
        failed_tasks=[failed], current_graph=TaskGraph(job_id="job_nc"), new_observations=[],
        produced_artifacts=[], replan_budget_remaining=2,
    ))
    [fix] = [m.task for m in result.mutations if m.mutation_type == GraphMutationType.ADD_TASK]
    return fix


def fallback(failed):
    return asyncio.run(fallback_async(failed))


def setup(actors):
    caps = CapabilityRegistry()
    caps.register_capability(Capability(id="implementation"))
    for actor_id in actors:
        caps.register_actor({"id": actor_id, "capabilities": ["implementation"]})
    exec_mgr = ExecutionManager()

    async def done(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]):
        return TaskExecutionResult(status="succeeded")

    for actor_id in actors:
        exec_mgr.register_adapter(actor_id, done)
    return ReactiveScheduler(capability_registry=caps, default_actor_concurrency=1), exec_mgr


async def run(fix, actors):
    scheduler, exec_mgr = setup(actors)
    graph = TaskGraph(job_id="job_nc")
    graph.add_task(fix)
    await asyncio.gather(*await scheduler.schedule_ready_tasks(graph, exec_mgr))
    return graph.get_task(fix.task_id)


def test_a_no_change_fallback_avoids_the_agent_that_made_no_changes():
    fix = fallback(failed_builder())
    assert fix.metadata["avoid_actors"] == ["antigravity"]


def test_avoided_agents_accumulate_across_chained_fallbacks():
    fix = fallback(failed_builder())
    fix.attempt, fix.max_attempts, fix.error = 2, 2, NO_CHANGES
    fix.assigned_actor = "claude"
    assert fallback(fix).metadata["avoid_actors"] == ["antigravity", "claude"]


def test_other_failures_keep_the_same_agent():
    fix = fallback(failed_builder(error="FAILED_TIMEOUT"))
    assert "avoid_actors" not in fix.metadata


@pytest.mark.anyio
async def test_the_scheduler_reroutes_a_no_change_fallback():
    task = await run(await fallback_async(failed_builder()), ["antigravity", "claude"])
    assert task.assigned_actor == "claude"
    assert task.status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_the_same_agent_retries_when_no_other_can():
    task = await run(await fallback_async(failed_builder()), ["antigravity"])
    assert task.assigned_actor == "antigravity"
    assert task.status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_a_task_pinned_to_a_backend_keeps_its_agent():
    task = await run(await fallback_async(failed_builder(execution_backend="openrig")), ["antigravity", "claude"])
    assert task.assigned_actor == "antigravity"
