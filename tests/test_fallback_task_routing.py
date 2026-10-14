"""A fallback for an exhausted task must run on the same agent and execution path.

Regression: fallback tasks were built from description and capabilities only, so a Claude task on
OpenRig was retried by whichever actor had the capabilities, on the default subprocess backend,
without its role guard. The job could then report COMPLETED although the real work never passed.
"""

import pytest

from runtime.replanning import GraphMutationType, ProductionPlannerAdapter, ReplanReason, ReplanRequest
from runtime.task_graph import TaskGraph, TaskNode


def failed_verifier():
    task = TaskNode(
        task_id="write_two",
        job_id="job_fb",
        description="/prompts/two.md",
        assigned_actor="claude",
        required_capabilities=["implementation"],
        dependencies=["write_one"],
        metadata={
            "role": "verifier",
            "execution_backend": "openrig",
            "prompt_file": "/prompts/two.md",
            "timeout_seconds": 300,
            "options": {"model": "sonnet"},
            "worktree_dir": "two",
            "branch": "e2e/two",
            "prior_runs": [{"run": "r1"}],
        },
        max_attempts=1,
    )
    task.attempt = 1
    task.error = "Verifier task 'write_two' modified 1 files"
    return task


@pytest.mark.anyio
async def test_fallback_keeps_the_agent_backend_role_and_prompt():
    failed = failed_verifier()
    result = await ProductionPlannerAdapter().plan(ReplanRequest(
        job_id="job_fb", goal="g", reason=ReplanReason.TASK_FAILURE, completed_tasks=[],
        failed_tasks=[failed], current_graph=TaskGraph(job_id="job_fb"), new_observations=[],
        produced_artifacts=[], replan_budget_remaining=2,
    ))

    [add] = [m for m in result.mutations if m.mutation_type == GraphMutationType.ADD_TASK]
    fix = add.task
    assert fix.assigned_actor == "claude"
    assert fix.parent_task_id == "write_two"
    assert fix.dependencies == ["write_one"]
    meta = fix.metadata
    assert meta["execution_backend"] == "openrig"
    assert meta["role"] == "verifier"
    assert meta["prompt_file"] == "/prompts/two.md"
    assert meta["timeout_seconds"] == 300
    assert meta["options"] == {"model": "sonnet"}
    assert meta["fallback_for"] == "write_two"
    # Fresh per-attempt state: never the failed task's worktree, branch or run history.
    assert not {"worktree_dir", "branch", "prior_runs"} & set(meta)
    # The failed task's own metadata is untouched.
    assert failed.metadata["worktree_dir"] == "two"


def test_a_fallback_prompt_sees_why_the_task_it_replaces_failed():
    from runtime.hermes_adapter import HermesActorAdapter

    class Registry:
        def list_for_task(self, task_id):
            return {"write_two": ["verifier modified 1 file"], "write_one": ["one.txt written"]}.get(task_id, [])

        def list_for_job(self, job_id):
            return []

    fix = TaskNode(task_id="fix_write_two_1", job_id="job_fb", parent_task_id="write_two", dependencies=["write_one"])
    assert HermesActorAdapter._prior_observations(fix, Registry()) == ["verifier modified 1 file", "one.txt written"]
