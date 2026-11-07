"""Tests for UNPROVEN verdict retry and blocking (Change 2).

Change 2 specification:
- In runtime/engine.py, an "unproven" verdict from a verifier or security task does not
  create repair and recheck tasks.
- The task fails as a normal attempt so the scheduler retries the same check once.
- If the retry is also unproven, the job blocks with the reason
  "verification incomplete: checked N of M".
"""

import asyncio
import json
from pathlib import Path

import pytest

from capabilities.capabilities import CapabilityRegistry
from runner.agents.claude import ClaudeAdapter
from runner.agents.codex import CodexAdapter
from runner.agents.registry import AgentRegistry
from runner.backends.base import ExecutionBackend, ExecutionResult
from runner.backends.registry import BackendRegistry
from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.execution import ExecutionManager
from runtime.hermes_adapter import HermesActorAdapter
from runtime.job_state import JobState
from runtime.limits import RuntimeLimits
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.task_graph import TaskNode, TaskStatus


class MockExecutionBackend(ExecutionBackend):
    name = "mock-verifier-backend"

    def __init__(self, responses=None, stdout: str = "", returncode: int = 0, **kwargs):
        self._responses = list(responses) if responses is not None else None
        self._stdout = stdout
        self._returncode = returncode
        self.call_count = 0

    def execute(self, request):
        self.call_count += 1
        if self._responses:
            out = self._responses.pop(0)
            if isinstance(out, ExecutionResult):
                return out
            return ExecutionResult(
                command=request.command,
                returncode=0,
                stdout=out,
                stderr="",
                backend=self.name,
            )
        return ExecutionResult(
            command=request.command,
            returncode=self._returncode,
            stdout=self._stdout,
            stderr="",
            backend=self.name,
        )

    def release_job(self, job_id):
        pass


def _create_test_engine(
    tmp_path: Path,
    actor_id: str,
    backend: MockExecutionBackend,
    max_task_attempts: int = 2,
    max_repairs_per_job: int = 3,
) -> ReactiveJobEngine:
    backend_factory = lambda **kwargs: backend
    agent_reg = AgentRegistry({
        ClaudeAdapter.name: ClaudeAdapter,
        CodexAdapter.name: CodexAdapter,
    })
    backend_reg = BackendRegistry({MockExecutionBackend.name: backend_factory})

    adapter = HermesActorAdapter(
        target_repo=tmp_path / "repo",
        worktree_root=tmp_path / "wt",
        run_dir=tmp_path / "runs",
        agent_registry=agent_reg,
        backend_registry=backend_reg,
        job_id="job_unproven_test",
    )

    exec_mgr = ExecutionManager()
    exec_mgr.register_adapter(actor_id, adapter)

    cap_reg = CapabilityRegistry()
    cap_reg.register_actor({"id": actor_id, "capabilities": ["verification"]})

    engine = ReactiveJobEngine(
        job_id="job_unproven_test",
        goal="Verify unproven retry and blocked behavior",
        execution_manager=exec_mgr,
        capability_registry=cap_reg,
        limits=RuntimeLimits(max_task_attempts=max_task_attempts, max_repairs_per_job=max_repairs_per_job),
        event_bridge=RuntimeEventBridge(event_store=InMemoryRuntimeEventStore()),
    )
    return engine


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["verifier", "security"])
async def test_unproven_verdict_retries_without_repair_and_blocks_on_second_unproven(tmp_path: Path, role: str):
    """
    Assert that when a verifier or security task returns an unproven verdict,
    runtime/engine.py creates no repair task and no recheck task, and the task fails
    as a normal attempt so the scheduler retries it.
    A second unproven verdict blocks the job with the reason 'verification incomplete: checked N of M'.
    """
    unproven_payload_1 = {
        "verdict": "unproven",
        "summary": "First check incomplete",
        "checked": 3,
        "total": 10,
        "findings": ["gap in coverage"],
    }
    unproven_payload_2 = {
        "verdict": "unproven",
        "summary": "Second check incomplete",
        "checked": 3,
        "total": 10,
        "findings": ["gap in coverage"],
    }

    backend = MockExecutionBackend(responses=[
        json.dumps(unproven_payload_1),
        json.dumps(unproven_payload_2),
    ])
    actor_id = "codex"
    engine = _create_test_engine(tmp_path, actor_id=actor_id, backend=backend)

    task = TaskNode(
        task_id=f"T_{role}",
        job_id="job_unproven_test",
        assigned_actor=actor_id,
        status=TaskStatus.READY,
        max_attempts=2,
        required_capabilities=["verification"],
        metadata={"role": role, "backend": MockExecutionBackend.name},
    )
    await engine.initialize_and_plan(initial_tasks=[task])

    # First attempt: returns unproven verdict
    await engine.step()

    # 1. runtime/engine.py creates no repair task and no recheck task
    repair_tasks = [t for t in engine.graph.list_tasks() if t.task_id.startswith("repair_")]
    recheck_tasks = [t for t in engine.graph.list_tasks() if t.task_id.startswith("recheck_")]
    assert len(repair_tasks) == 0, f"Expected no repair tasks after unproven verdict, got {repair_tasks}"
    assert len(recheck_tasks) == 0, f"Expected no recheck tasks after unproven verdict, got {recheck_tasks}"
    assert engine.job.repair_count == 0

    # 2. Task fails as a normal attempt so scheduler retries it
    task_node = engine.graph.get_task(task.task_id)
    assert task_node.attempt == 1
    assert task_node.status == TaskStatus.READY

    # Second attempt: retry runs and also returns unproven verdict
    await engine.step()

    assert backend.call_count == 2
    assert task_node.attempt == 2

    # 3. Second unproven verdict blocks the job with reason 'verification incomplete: checked N of M'
    assert engine.job.state == JobState.BLOCKED
    expected_reason = "verification incomplete: checked 3 of 10"
    assert engine.job.blocked_reason == expected_reason, (
        f"Expected blocked reason '{expected_reason}', got '{engine.job.blocked_reason}'"
    )


@pytest.mark.anyio
async def test_second_unproven_verdict_blocks_with_checked_counts(tmp_path: Path):
    """
    A second unproven verdict with different checked and total counts blocks the job
    with reason 'verification incomplete: checked N of M' reflecting those counts.
    Tested with Claude JSON envelope output.
    """
    payload_1 = {
        "verdict": "unproven",
        "summary": "Partial coverage in Claude verifier",
        "checked": 4,
        "total": 12,
        "findings": [],
    }
    payload_2 = {
        "verdict": "unproven",
        "summary": "Still partial coverage in Claude verifier",
        "checked": 4,
        "total": 12,
        "findings": [],
    }

    claude_envelope_1 = json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": f"```json\n{json.dumps(payload_1)}\n```",
    })
    claude_envelope_2 = json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": f"```json\n{json.dumps(payload_2)}\n```",
    })

    backend = MockExecutionBackend(responses=[claude_envelope_1, claude_envelope_2])
    actor_id = "claude"
    engine = _create_test_engine(tmp_path, actor_id=actor_id, backend=backend)

    task = TaskNode(
        task_id="T_claude_verifier",
        job_id="job_unproven_test",
        assigned_actor=actor_id,
        status=TaskStatus.READY,
        max_attempts=2,
        required_capabilities=["verification"],
        metadata={"role": "verifier", "backend": MockExecutionBackend.name},
    )
    await engine.initialize_and_plan(initial_tasks=[task])

    # First attempt: returns unproven -> retried
    await engine.step()
    t = engine.graph.get_task(task.task_id)
    assert t.attempt == 1
    assert t.status == TaskStatus.READY
    assert not any(x.task_id.startswith("repair_") for x in engine.graph.list_tasks())

    # Second attempt: returns unproven -> blocks job
    await engine.step()
    assert backend.call_count == 2
    assert engine.job.state == JobState.BLOCKED
    expected_reason = "verification incomplete: checked 4 of 12"
    assert engine.job.blocked_reason == expected_reason, (
        f"Expected blocked reason '{expected_reason}', got '{engine.job.blocked_reason}'"
    )


@pytest.mark.anyio
async def test_checked_less_than_total_normalizes_to_unproven_and_retries_then_blocks(tmp_path: Path):
    """
    When a verifier returns verdict 'passed' or 'failed' but checked < total,
    CodexAdapter normalizes it to 'unproven' (Change 1).
    Engine must retry once without repair, then block on second unproven verdict with
    'verification incomplete: checked N of M'.
    """
    first_payload = {
        "verdict": "passed",
        "summary": "Check incomplete",
        "checked": 1,
        "total": 5,
        "findings": [],
    }
    second_payload = {
        "verdict": "failed",
        "summary": "Second check incomplete",
        "checked": 2,
        "total": 5,
        "repairable": True,
        "findings": ["defect X"],
    }

    backend = MockExecutionBackend(responses=[
        json.dumps(first_payload),
        json.dumps(second_payload),
    ])
    actor_id = "codex"
    engine = _create_test_engine(tmp_path, actor_id=actor_id, backend=backend)

    task = TaskNode(
        task_id="T_coverage_verifier",
        job_id="job_unproven_test",
        assigned_actor=actor_id,
        status=TaskStatus.READY,
        max_attempts=2,
        required_capabilities=["verification"],
        metadata={"role": "verifier", "backend": MockExecutionBackend.name},
    )
    await engine.initialize_and_plan(initial_tasks=[task])

    # First attempt
    await engine.step()
    t = engine.graph.get_task(task.task_id)
    assert t.attempt == 1
    assert t.status == TaskStatus.READY
    assert not any(x.task_id.startswith("repair_") for x in engine.graph.list_tasks())
    assert not any(x.task_id.startswith("recheck_") for x in engine.graph.list_tasks())

    # Second attempt
    await engine.step()
    assert backend.call_count == 2
    assert engine.job.state == JobState.BLOCKED
    expected_reason = "verification incomplete: checked 2 of 5"
    assert engine.job.blocked_reason == expected_reason, (
        f"Expected blocked reason '{expected_reason}', got '{engine.job.blocked_reason}'"
    )


@pytest.mark.anyio
async def test_non_verdict_failure_on_attempt_1_retries_first_unproven_on_attempt_2(tmp_path: Path):
    """If attempt 1 fails for a non-verdict reason, the first unproven verdict on attempt 2
    must still be retried rather than immediately blocking the job.
    """
    unproven_payload = {
        "verdict": "unproven",
        "summary": "Check incomplete on attempt 2",
        "checked": 2,
        "total": 5,
        "findings": ["incomplete"],
    }
    # Response 1: Non-verdict error (crash / command failed)
    resp1 = ExecutionResult(
        command="run check",
        returncode=1,
        stdout="",
        stderr="Process killed / crash",
        backend=MockExecutionBackend.name,
    )
    # Response 2: First unproven verdict
    resp2 = ExecutionResult(
        command="run check",
        returncode=0,
        stdout=json.dumps(unproven_payload),
        stderr="",
        backend=MockExecutionBackend.name,
    )
    # Response 3: Second unproven verdict (causes block)
    resp3 = ExecutionResult(
        command="run check",
        returncode=0,
        stdout=json.dumps(unproven_payload),
        stderr="",
        backend=MockExecutionBackend.name,
    )

    backend = MockExecutionBackend(responses=[resp1, resp2, resp3])
    actor_id = "codex"
    engine = _create_test_engine(tmp_path, actor_id=actor_id, backend=backend, max_task_attempts=3)

    task = TaskNode(
        task_id="T_non_verdict_retry",
        job_id="job_unproven_test",
        assigned_actor=actor_id,
        status=TaskStatus.READY,
        max_attempts=3,
        required_capabilities=["verification"],
        metadata={"role": "verifier", "backend": MockExecutionBackend.name},
    )
    await engine.initialize_and_plan(initial_tasks=[task])

    # Attempt 1: non-verdict failure
    await engine.step()
    t = engine.graph.get_task(task.task_id)
    assert t.attempt == 1
    assert t.status == TaskStatus.READY
    assert engine.job.state != JobState.BLOCKED

    # Attempt 2: first unproven verdict. Must NOT block immediately!
    await engine.step()
    t = engine.graph.get_task(task.task_id)
    assert t.attempt == 2
    assert t.status == TaskStatus.READY
    assert t.metadata.get("had_unproven") is True
    assert engine.job.state != JobState.BLOCKED

    # Attempt 3: second unproven verdict. Now it blocks.
    await engine.step()
    assert backend.call_count == 3
    assert engine.job.state == JobState.BLOCKED
    assert engine.job.blocked_reason == "verification incomplete: checked 2 of 5"
