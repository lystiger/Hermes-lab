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


def plan(request_kwargs):
    import asyncio
    base = dict(job_id="job_fb", goal="g", completed_tasks=[], failed_tasks=[], new_observations=[],
                current_graph=TaskGraph(job_id="job_fb"), produced_artifacts=[], replan_budget_remaining=2)
    base.update(request_kwargs)
    return asyncio.run(ProductionPlannerAdapter().plan(ReplanRequest(**base)))


def added(result):
    return [m.task for m in result.mutations if m.mutation_type == GraphMutationType.ADD_TASK]


def test_a_fallback_keeps_the_original_instructions_not_a_diagnostic():
    failed = failed_verifier()
    failed.description = "Write two.txt with the secret word"
    [fix] = added(plan(dict(reason=ReplanReason.TASK_FAILURE, failed_tasks=[failed])))
    assert fix.description == "Write two.txt with the secret word"
    assert fix.metadata["fallback_errors"] == [
        {"task_id": "write_two", "error": "Verifier task 'write_two' modified 1 files"}
    ]


def test_chained_fallbacks_carry_every_earlier_failure():
    failed = failed_verifier()
    [fix] = added(plan(dict(reason=ReplanReason.TASK_FAILURE, failed_tasks=[failed])))
    fix.attempt, fix.max_attempts, fix.error = 2, 2, "FAILED_TIMEOUT"
    [fix2] = added(plan(dict(reason=ReplanReason.TASK_FAILURE, failed_tasks=[fix])))
    assert [e["task_id"] for e in fix2.metadata["fallback_errors"]] == ["write_two", fix.task_id]
    assert fix2.metadata["fallback_errors"][1]["error"] == "FAILED_TIMEOUT"
    assert fix2.metadata["execution_backend"] == "openrig" and fix2.assigned_actor == "claude"


def test_the_fallback_prompt_explains_earlier_failures_even_with_a_prompt_file():
    from runtime.hermes_adapter import HermesActorAdapter

    [fix] = added(plan(dict(reason=ReplanReason.TASK_FAILURE, failed_tasks=[failed_verifier()])))
    section = HermesActorAdapter._fallback_failure_section(fix)
    assert "Previous attempts failed" in section
    assert "write_two: Verifier task 'write_two' modified 1 files" in section
    assert HermesActorAdapter._fallback_failure_section(TaskNode(task_id="plain")) == ""


def test_a_verification_repair_tied_to_a_task_keeps_its_routing_and_may_change_files():
    from runtime.observations import Observation

    graph = TaskGraph(job_id="job_fb")
    source = failed_verifier()
    graph.add_task(source)
    obs = Observation(job_id="job_fb", task_id="write_two", source="hermes.verifier",
                      kind="verification_failure", content="pytest failed")
    [repair] = added(plan(dict(reason=ReplanReason.VERIFICATION_REPAIR, new_observations=[obs], current_graph=graph)))

    assert repair.assigned_actor == "claude"
    assert repair.parent_task_id == "write_two"
    assert repair.metadata["execution_backend"] == "openrig"
    assert repair.metadata["role"] == "builder"
    assert repair.metadata["repair_for"] == "write_two"
    assert "prompt_file" not in repair.metadata
    assert repair.description.startswith("Fix verification failure: pytest failed")


def test_a_verification_repair_without_a_task_is_unchanged():
    from runtime.observations import Observation

    obs = Observation(job_id="job_fb", source="hermes.verifier", kind="verification_failure", content="lint failed")
    [repair] = added(plan(dict(reason=ReplanReason.VERIFICATION_REPAIR, new_observations=[obs])))
    assert repair.assigned_actor is None and repair.parent_task_id is None
    assert set(repair.metadata) == {"observation_ref", "error_details"}
