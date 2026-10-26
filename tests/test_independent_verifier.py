"""A verifier task goes to an agent that did not build in the same job, when one is capable."""
import asyncio
from typing import Any, Dict

import pytest

from capabilities.capabilities import Capability, CapabilityRegistry
from runtime.execution import AgentRun, ExecutionManager, TaskExecutionResult
from runtime.scheduler import ReactiveScheduler
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus

BUILDER_CAPS = ["implementation", "verification", "testing.unit"]


def setup(actors):
    caps = CapabilityRegistry()
    for cap in BUILDER_CAPS:
        caps.register_capability(Capability(id=cap))
    for actor_id, actor_caps in actors.items():
        caps.register_actor({"id": actor_id, "capabilities": actor_caps})
    exec_mgr = ExecutionManager()

    async def done(task: TaskNode, run: AgentRun, ctx: Dict[str, Any]):
        return TaskExecutionResult(status="succeeded")

    for actor_id in actors:
        exec_mgr.register_adapter(actor_id, done)
    return ReactiveScheduler(capability_registry=caps, default_actor_concurrency=1), exec_mgr


def job(verify_role="verifier"):
    graph = TaskGraph(job_id="job_verify")
    graph.add_task(TaskNode(task_id="build", required_capabilities=["implementation"],
                            metadata={"role": "builder"}))
    verify = TaskNode(task_id="verify", required_capabilities=["verification", "testing.unit"],
                      metadata={"role": verify_role})
    verify.dependencies = ["build"]
    graph.add_task(verify)
    return graph


async def run_all(scheduler, exec_mgr, graph):
    for _ in range(2):
        await asyncio.gather(*await scheduler.schedule_ready_tasks(graph, exec_mgr))


@pytest.mark.anyio
async def test_verifier_skips_the_agent_that_built():
    # The builder's capabilities cover the verifier's, so plain ranking would pick it twice.
    scheduler, exec_mgr = setup({"antigravity": BUILDER_CAPS, "codex": ["verification", "testing.unit"]})
    graph = job()
    await run_all(scheduler, exec_mgr, graph)
    assert graph.get_task("build").assigned_actor == "antigravity"
    assert graph.get_task("verify").assigned_actor == "codex"
    assert graph.get_task("verify").status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_builder_verifies_when_no_other_agent_can():
    scheduler, exec_mgr = setup({"antigravity": BUILDER_CAPS, "claude": ["implementation"]})
    graph = job()
    await run_all(scheduler, exec_mgr, graph)
    assert graph.get_task("verify").assigned_actor == "antigravity"
    assert graph.get_task("verify").status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_other_roles_keep_the_best_match():
    scheduler, exec_mgr = setup({"antigravity": BUILDER_CAPS, "codex": ["verification", "testing.unit"]})
    graph = job(verify_role="hardener")
    await run_all(scheduler, exec_mgr, graph)
    assert graph.get_task("verify").assigned_actor == "antigravity"
