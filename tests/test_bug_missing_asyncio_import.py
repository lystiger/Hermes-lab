"""
Bug: runtime/job_state.py and runtime/replanning.py call asyncio.iscoroutine and
asyncio.get_running_loop when an event bridge returns a coroutine, but neither module
imports asyncio. The call raises NameError instead of scheduling the coroutine.
"""
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.replanning import BoundedReplanner, GraphMutation, GraphMutationType, ReplanResult
from runtime.task_graph import TaskGraph, TaskNode


class _JobBridge:
    async def emit_job_state_changed(self, **kwargs):
        return None


class _TaskBridge:
    async def emit_task_created(self, node, reason=None):
        return None


@pytest.mark.anyio
async def test_job_state_and_replanning_import_asyncio():
    """
    Driving the public entry points with a bridge whose emit methods are coroutines must
    not raise NameError from the missing asyncio import in either module.
    """
    job = JobRecord(job_id="job-asyncio", goal="g")
    job.transition_to(JobState.PLANNING, event_bridge=_JobBridge())
    assert job.state == JobState.PLANNING

    graph = TaskGraph(job_id="job-asyncio")
    task = TaskNode(task_id="t-new", job_id="job-asyncio", description="d")
    result = ReplanResult(mutations=[GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=task)])
    affected = BoundedReplanner().apply_mutations(graph, result, "job-asyncio", event_bridge=_TaskBridge())
    assert affected == ["t-new"]
