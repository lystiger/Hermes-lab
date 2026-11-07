"""Tests for Change 3: Fix + sweep repairs.

Change 3 specification:
In runtime/engine.py _repair_failed_verdict, the repair task description says:
- fix exactly the listed findings,
- then apply the same rule to every other item of the same kind in the work and fix any that break it,
- and list in the final message what was swept.
"""

import pytest

from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.execution import TaskExecutionResult
from runtime.limits import RuntimeLimits
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.task_graph import TaskNode, TaskStatus


class OptInPlanner:
    repairs_failed_verdicts = True

    async def plan(self, request):
        raise AssertionError("not used")


def _make_engine(role: str = "verifier"):
    engine = ReactiveJobEngine(
        job_id=f"job_sweep_{role}",
        goal=f"Test sweep repair for {role}",
        planner=OptInPlanner(),
        limits=RuntimeLimits(max_repairs_per_job=3),
        event_bridge=RuntimeEventBridge(event_store=InMemoryRuntimeEventStore()),
    )
    engine.graph.add_task(
        TaskNode(
            task_id="build",
            job_id=f"job_sweep_{role}",
            description="build components",
            status=TaskStatus.SUCCEEDED,
            metadata={"role": "builder"},
        )
    )
    check_task = engine.graph.add_task(
        TaskNode(
            task_id=f"check_{role}",
            job_id=f"job_sweep_{role}",
            description="Verify widget accessibility across the app",
            dependencies=["build"],
            required_capabilities=["verification"],
            assigned_actor="codex",
            metadata={"role": role},
        )
    )
    return engine, check_task


def _failed_verdict(findings=None, summary="tests failed"):
    if findings is None:
        findings = ["button-1 missing aria-label", "button-2 missing aria-label"]
    return TaskExecutionResult(
        status="failed",
        error=summary,
        metadata={
            "verdict": "failed",
            "verification_summary": summary,
            "findings": findings,
            "repairable": True,
        },
    )


@pytest.mark.parametrize("role", ["verifier", "security"])
@pytest.mark.anyio
async def test_repair_task_description_contains_sweep_instructions(role: str):
    """The repair task description built in _repair_failed_verdict must say:
    1. fix exactly the listed findings;
    2. then apply the same rule to every other item of the same kind in the work and fix any that break it;
    3. and list in the final message what was swept.
    """
    engine, check_task = _make_engine(role=role)
    findings = ["item A broken", "item B broken"]
    handled = await engine._repair_failed_verdict(check_task, _failed_verdict(findings=findings))
    assert handled is True

    repair_task = engine.graph.get_task(f"repair_check_{role}_1")
    assert repair_task is not None

    desc = repair_task.description.lower()

    assert "fix exactly the listed findings" in desc, (
        f"Repair description must say 'fix exactly the listed findings'.\n"
        f"Got:\n{repair_task.description}"
    )
    assert "apply the same rule to every other item of the same kind in the work and fix any that break it" in desc, (
        f"Repair description must say 'apply the same rule to every other item of the same kind in the work and fix any that break it'.\n"
        f"Got:\n{repair_task.description}"
    )
    assert "list in the final message what was swept" in desc, (
        f"Repair description must say 'list in the final message what was swept'.\n"
        f"Got:\n{repair_task.description}"
    )


@pytest.mark.anyio
async def test_repair_task_description_sweep_instructions_in_subsequent_cycle():
    """Subsequent repair cycles (e.g. cycle 2) must also include the fix + sweep repair instructions."""
    engine, check_task = _make_engine(role="verifier")
    await engine._repair_failed_verdict(check_task, _failed_verdict(["defect 1"]))

    recheck = engine.graph.get_task("recheck_check_verifier_1")
    assert recheck is not None

    handled = await engine._repair_failed_verdict(recheck, _failed_verdict(["defect 2"]))
    assert handled is True

    repair_cycle2 = engine.graph.get_task("repair_check_verifier_2")
    assert repair_cycle2 is not None

    desc = repair_cycle2.description.lower()

    assert "fix exactly the listed findings" in desc, (
        f"Repair description in cycle 2 must say 'fix exactly the listed findings'.\n"
        f"Got:\n{repair_cycle2.description}"
    )
    assert "apply the same rule to every other item of the same kind in the work and fix any that break it" in desc, (
        f"Repair description in cycle 2 must say 'apply the same rule to every other item of the same kind in the work and fix any that break it'.\n"
        f"Got:\n{repair_cycle2.description}"
    )
    assert "list in the final message what was swept" in desc, (
        f"Repair description in cycle 2 must say 'list in the final message what was swept'.\n"
        f"Got:\n{repair_cycle2.description}"
    )
