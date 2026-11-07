"""Tests for Change 5: Repair cycle budget and verify-repair convergence.

Change 5 specification:
1. In runtime/limits.py, the job-wide max_repairs_per_job default is 10, not 3.
2. In runtime/engine.py:
   - A check (one repair root) goes through at most 5 repair cycles.
   - A new cycle starts only if the failed recheck has fewer findings than the previous check.
   - A non-shrinking cycle, or a failing 5th cycle, blocks the job with the reason:
     'verification not converging: findings per cycle A, B, C'
"""

import pytest

from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.execution import TaskExecutionResult
from runtime.job_state import JobState
from runtime.limits import RuntimeLimits
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.task_graph import TaskNode, TaskStatus


class OptInPlanner:
    repairs_failed_verdicts = True

    async def plan(self, request):
        raise AssertionError("not used")


def _make_engine(max_repairs: int = None, job_id: str = "job_cycle_budget"):
    kwargs = {}
    if max_repairs is not None:
        kwargs["limits"] = RuntimeLimits(max_repairs_per_job=max_repairs)
    engine = ReactiveJobEngine(
        job_id=job_id,
        goal="Test cycle budget and convergence",
        planner=OptInPlanner(),
        event_bridge=RuntimeEventBridge(event_store=InMemoryRuntimeEventStore()),
        **kwargs,
    )
    # Move engine to EXECUTING state so BLOCKED transitions are legal
    engine.job.transition_to(JobState.PLANNING)
    engine.job.transition_to(JobState.EXECUTING)

    engine.graph.add_task(
        TaskNode(
            task_id="build",
            job_id=job_id,
            description="build components",
            status=TaskStatus.SUCCEEDED,
            metadata={"role": "builder"},
        )
    )
    verify = engine.graph.add_task(
        TaskNode(
            task_id="verify",
            job_id=job_id,
            description="Verify components",
            dependencies=["build"],
            required_capabilities=["verification"],
            assigned_actor="codex",
            metadata={"role": "verifier"},
        )
    )
    return engine, verify


def _failed_verdict(findings=None, summary="tests failed"):
    if findings is None:
        findings = ["error 1", "error 2"]
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


def test_job_wide_max_repairs_per_job_default_is_10():
    """Assert that the job-wide max_repairs_per_job default in runtime/limits.py is 10, not 3."""
    limits = RuntimeLimits()
    assert limits.max_repairs_per_job == 10, (
        f"Default max_repairs_per_job must be 10, got {limits.max_repairs_per_job}"
    )

    limits_from_dict = RuntimeLimits.from_dict({})
    assert limits_from_dict.max_repairs_per_job == 10, (
        f"RuntimeLimits.from_dict default max_repairs_per_job must be 10, got {limits_from_dict.max_repairs_per_job}"
    )

    # 0 in from_dict falls back to default 10 (matching other limit fields)
    limits_zero = RuntimeLimits.from_dict({"max_repairs_per_job": 0})
    assert limits_zero.max_repairs_per_job == 10, (
        f"RuntimeLimits.from_dict with 0 should fall back to default 10, got {limits_zero.max_repairs_per_job}"
    )


@pytest.mark.anyio
async def test_new_cycle_starts_only_if_recheck_has_fewer_findings():
    """Assert that a new cycle starts only if the failed recheck has fewer findings than the previous check.
    If the failed recheck has equal findings, no new repair cycle should start.
    """
    engine, verify = _make_engine(max_repairs=10)

    # Initial check fails with 3 findings -> Cycle 1 created
    handled1 = await engine._repair_failed_verdict(
        verify, _failed_verdict(findings=["issue A", "issue B", "issue C"])
    )
    assert handled1 is True
    recheck_1 = engine.graph.get_task("recheck_verify_1")
    assert recheck_1 is not None

    # Recheck 1 fails with 3 findings (equal findings, not fewer)
    # A new cycle must NOT start.
    handled2 = await engine._repair_failed_verdict(
        recheck_1, _failed_verdict(findings=["issue A", "issue B", "issue D"])
    )
    assert handled2 is True
    repair_2 = engine.graph.get_task("repair_verify_2")
    assert repair_2 is None, (
        "A new cycle must start only if the failed recheck has fewer findings than the previous check, "
        f"but repair_verify_2 was created despite findings not shrinking (3 -> 3)"
    )


@pytest.mark.anyio
async def test_non_shrinking_cycle_equal_findings_blocks_with_reason():
    """Assert that a non-shrinking cycle (equal findings) blocks the job with reason:
    'verification not converging: findings per cycle A, B, C'.
    """
    engine, verify = _make_engine(max_repairs=10)

    # Initial check fails with 3 findings -> Cycle 1 created
    handled1 = await engine._repair_failed_verdict(
        verify, _failed_verdict(findings=["bug 1", "bug 2", "bug 3"])
    )
    assert handled1 is True
    recheck_1 = engine.graph.get_task("recheck_verify_1")
    assert recheck_1 is not None

    # Recheck 1 fails with 3 findings (3 is not < 3: non-shrinking) -> Blocks job
    handled2 = await engine._repair_failed_verdict(
        recheck_1, _failed_verdict(findings=["bug 1", "bug 2", "bug 4"])
    )
    assert handled2 is True

    # No cycle 2 created
    assert engine.graph.get_task("repair_verify_2") is None, (
        "No new cycle should start when findings do not shrink"
    )
    assert engine.graph.get_task("recheck_verify_2") is None, (
        "No new recheck should be created when findings do not shrink"
    )

    # Job blocked with exact reason format
    assert engine.job.state == JobState.BLOCKED
    expected_reason = "verification not converging: findings per cycle 3, 3"
    assert engine.job.blocked_reason == expected_reason, (
        f"Expected blocked reason '{expected_reason}', got '{engine.job.blocked_reason}'"
    )


@pytest.mark.anyio
async def test_non_shrinking_cycle_growing_findings_blocks_with_reason():
    """Assert that a cycle where findings increase blocks the job with reason:
    'verification not converging: findings per cycle A, B, C'.
    """
    engine, verify = _make_engine(max_repairs=10)

    # Initial check fails with 2 findings -> Cycle 1 created
    await engine._repair_failed_verdict(
        verify, _failed_verdict(findings=["bug 1", "bug 2"])
    )
    recheck_1 = engine.graph.get_task("recheck_verify_1")
    assert recheck_1 is not None

    # Recheck 1 fails with 4 findings (4 > 2: findings grew) -> Blocks job
    await engine._repair_failed_verdict(
        recheck_1, _failed_verdict(findings=["bug 1", "bug 2", "bug 3", "bug 4"])
    )

    assert engine.graph.get_task("repair_verify_2") is None, (
        "No new cycle should start when findings increase"
    )
    assert engine.job.state == JobState.BLOCKED
    expected_reason = "verification not converging: findings per cycle 2, 4"
    assert engine.job.blocked_reason == expected_reason, (
        f"Expected blocked reason '{expected_reason}', got '{engine.job.blocked_reason}'"
    )


@pytest.mark.anyio
async def test_multi_cycle_convergence_failure_blocks_with_reason():
    """Assert that a cycle shrinking once (4 -> 3) and then failing to shrink (3 -> 3)
    blocks the job with reason 'verification not converging: findings per cycle 4, 3, 3'.
    """
    engine, verify = _make_engine(max_repairs=10)

    # Initial check: 4 findings -> Cycle 1
    await engine._repair_failed_verdict(
        verify, _failed_verdict(findings=["f1", "f2", "f3", "f4"])
    )
    recheck_1 = engine.graph.get_task("recheck_verify_1")
    assert recheck_1 is not None

    # Recheck 1: 3 findings (3 < 4: shrank) -> Cycle 2
    await engine._repair_failed_verdict(
        recheck_1, _failed_verdict(findings=["f1", "f2", "f3"])
    )
    recheck_2 = engine.graph.get_task("recheck_verify_2")
    assert recheck_2 is not None

    # Recheck 2: 3 findings (3 is not < 3: non-shrinking) -> Blocks
    await engine._repair_failed_verdict(
        recheck_2, _failed_verdict(findings=["f1", "f2", "f5"])
    )

    assert engine.graph.get_task("repair_verify_3") is None, (
        "No cycle 3 should start when findings do not shrink"
    )
    assert engine.job.state == JobState.BLOCKED
    expected_reason = "verification not converging: findings per cycle 4, 3, 3"
    assert engine.job.blocked_reason == expected_reason, (
        f"Expected blocked reason '{expected_reason}', got '{engine.job.blocked_reason}'"
    )


@pytest.mark.anyio
async def test_repair_root_capped_at_five_repair_cycles():
    """Assert that a check (one repair root) goes through at most 5 repair cycles,
    and a failing 5th cycle blocks the job with reason 'verification not converging: findings per cycle A, B, C'.
    """
    engine, verify = _make_engine(max_repairs=10)

    # Initial check fails with 6 findings -> Cycle 1
    await engine._repair_failed_verdict(
        verify, _failed_verdict(findings=["f1", "f2", "f3", "f4", "f5", "f6"])
    )
    assert engine.graph.get_task("repair_verify_1") is not None
    assert engine.graph.get_task("recheck_verify_1") is not None

    # Cycle 1 recheck fails with 5 findings (5 < 6: shrank) -> Cycle 2
    recheck_1 = engine.graph.get_task("recheck_verify_1")
    await engine._repair_failed_verdict(
        recheck_1, _failed_verdict(findings=["f1", "f2", "f3", "f4", "f5"])
    )
    assert engine.graph.get_task("repair_verify_2") is not None
    assert engine.graph.get_task("recheck_verify_2") is not None

    # Cycle 2 recheck fails with 4 findings (4 < 5: shrank) -> Cycle 3
    recheck_2 = engine.graph.get_task("recheck_verify_2")
    await engine._repair_failed_verdict(
        recheck_2, _failed_verdict(findings=["f1", "f2", "f3", "f4"])
    )
    assert engine.graph.get_task("repair_verify_3") is not None
    assert engine.graph.get_task("recheck_verify_3") is not None

    # Cycle 3 recheck fails with 3 findings (3 < 4: shrank) -> Cycle 4
    recheck_3 = engine.graph.get_task("recheck_verify_3")
    await engine._repair_failed_verdict(
        recheck_3, _failed_verdict(findings=["f1", "f2", "f3"])
    )
    assert engine.graph.get_task("repair_verify_4") is not None
    assert engine.graph.get_task("recheck_verify_4") is not None

    # Cycle 4 recheck fails with 2 findings (2 < 3: shrank) -> Cycle 5
    recheck_4 = engine.graph.get_task("recheck_verify_4")
    await engine._repair_failed_verdict(
        recheck_4, _failed_verdict(findings=["f1", "f2"])
    )
    assert engine.graph.get_task("repair_verify_5") is not None
    assert engine.graph.get_task("recheck_verify_5") is not None
    assert engine.job.state != JobState.BLOCKED

    # Cycle 5 recheck fails with 1 finding (1 < 2: shrank, but 5th cycle reached)
    # At most 5 repair cycles allowed per repair root.
    recheck_5 = engine.graph.get_task("recheck_verify_5")
    await engine._repair_failed_verdict(
        recheck_5, _failed_verdict(findings=["f1"])
    )

    # Cycle 6 must NOT be created
    assert engine.graph.get_task("repair_verify_6") is None, (
        "A 6th repair cycle must not be created; repair root capped at 5 cycles"
    )
    assert engine.graph.get_task("recheck_verify_6") is None, (
        "A 6th recheck task must not be created; repair root capped at 5 cycles"
    )

    # Failing 5th cycle blocks the job with the exact convergence reason
    assert engine.job.state == JobState.BLOCKED
    expected_reason = "verification not converging: findings per cycle 6, 5, 4, 3, 2, 1"
    assert engine.job.blocked_reason == expected_reason, (
        f"Expected blocked reason '{expected_reason}', got '{engine.job.blocked_reason}'"
    )


@pytest.mark.anyio
async def test_five_cycle_cap_is_enforced_per_repair_root():
    """Assert that the 5-cycle cap applies per repair root, so multiple checks in one job
    can each have repair cycles as long as each stays within 5 and the job stays within max_repairs_per_job (10).
    """
    engine, verify_a = _make_engine(job_id="job_multi_root")
    verify_b = engine.graph.add_task(
        TaskNode(
            task_id="verify_b",
            job_id="job_multi_root",
            description="Verify security aspects",
            dependencies=["build"],
            required_capabilities=["verification"],
            assigned_actor="codex",
            metadata={"role": "security"},
        )
    )

    # verify_a goes through 2 shrinking repair cycles (3 -> 2 -> 1)
    await engine._repair_failed_verdict(verify_a, _failed_verdict(findings=["a1", "a2", "a3"]))
    recheck_a1 = engine.graph.get_task("recheck_verify_1")
    await engine._repair_failed_verdict(recheck_a1, _failed_verdict(findings=["a1", "a2"]))
    assert engine.graph.get_task("repair_verify_2") is not None
    assert engine.job.state != JobState.BLOCKED

    # verify_b goes through 2 shrinking repair cycles (3 -> 2 -> 1)
    await engine._repair_failed_verdict(verify_b, _failed_verdict(findings=["b1", "b2", "b3"]))
    recheck_b_nodes = [t for t in engine.graph.list_tasks() if (t.metadata or {}).get("repair_root") == "verify_b"]
    assert len(recheck_b_nodes) >= 1
    recheck_b1 = recheck_b_nodes[-1]
    await engine._repair_failed_verdict(recheck_b1, _failed_verdict(findings=["b1", "b2"]))

    # Total repairs across roots is 4.
    # On current code with default max_repairs_per_job=3, this blocks after 3 repairs.
    # With change 5 (default 10 repairs, 5 per root), neither root exceeded 5 and 4 <= 10.
    assert engine.job.state != JobState.BLOCKED, (
        f"Job blocked prematurely with reason: {engine.job.blocked_reason}. "
        f"5-cycle cap must be per repair root, and default max_repairs_per_job must be 10."
    )
