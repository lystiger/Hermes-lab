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


def make_engine(max_repairs=3):
    engine = ReactiveJobEngine(job_id="j", goal="g", planner=OptInPlanner(),
                               limits=RuntimeLimits(max_repairs_per_job=max_repairs),
                               event_bridge=RuntimeEventBridge(event_store=InMemoryRuntimeEventStore()))
    engine.graph.add_task(TaskNode(task_id="build", job_id="j", description="build", status=TaskStatus.SUCCEEDED,
                                   metadata={"role": "builder"}))
    verify = engine.graph.add_task(TaskNode(task_id="verify", job_id="j", description="Verify the page",
                                            dependencies=["build"], required_capabilities=["verification"],
                                            assigned_actor="codex", metadata={"role": "verifier"}))
    return engine, verify


def failed(findings, repairable=True):
    return TaskExecutionResult(status="failed", error="tests failed", metadata={
        "verdict": "failed", "verification_summary": "tests failed", "findings": findings, "repairable": repairable})


@pytest.mark.anyio
async def test_a_failed_verdict_adds_a_repair_and_a_recheck():
    engine, verify = make_engine()
    assert await engine._repair_failed_verdict(verify, failed(["test X fails"])) is True

    repair, recheck = engine.graph.get_task("repair_verify_1"), engine.graph.get_task("recheck_verify_1")
    assert repair.metadata["role"] == "builder" and "test X fails" in repair.description
    assert repair.required_capabilities == ["implementation"] and repair.dependencies == []
    assert recheck.dependencies == ["repair_verify_1"] and recheck.assigned_actor == "codex"
    assert recheck.metadata["role"] == "verifier" and "test X fails" in recheck.description
    assert verify.status == TaskStatus.SUPERSEDED and verify.superseded_by == "recheck_verify_1"
    assert engine.job.repair_count == 1

    # A second failure of the re-check chains from the same root.
    assert await engine._repair_failed_verdict(recheck, failed(["still failing"])) is True
    assert engine.graph.get_task("repair_verify_2") and engine.graph.get_task("recheck_verify_2")
    assert engine.graph.get_task("recheck_verify_2").metadata["original_description"] == "Verify the page"


@pytest.mark.anyio
async def test_the_loop_stops_at_the_repair_cap():
    engine, verify = make_engine(max_repairs=0)
    engine.job.transition_to(JobState.PLANNING)
    engine.job.transition_to(JobState.EXECUTING)
    assert await engine._repair_failed_verdict(verify, failed(["x"])) is True
    assert engine.job.state == JobState.BLOCKED
    assert engine.graph.get_task("repair_verify_1") is None


@pytest.mark.anyio
async def test_unrepairable_verdicts_and_non_verifiers_are_left_alone():
    engine, verify = make_engine()
    assert await engine._repair_failed_verdict(verify, failed(["x"], repairable=False)) is False
    builder = engine.graph.get_task("build")
    assert await engine._repair_failed_verdict(builder, failed(["x"])) is False
    engine.planner = type("OwnRepairs", (), {"plan": lambda self, r: None})()  # handles verdicts itself
    assert await engine._repair_failed_verdict(verify, failed(["x"])) is False
