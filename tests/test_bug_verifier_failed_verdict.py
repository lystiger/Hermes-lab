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
from runtime.execution import ExecutionManager
from runtime.hermes_adapter import HermesActorAdapter
from runtime.scheduler import ReactiveScheduler
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus


class MockExecutionBackend(ExecutionBackend):
    name = "mock-verifier-backend"

    def __init__(self, stdout: str = "", returncode: int = 0, **kwargs):
        self._stdout = stdout
        self._returncode = returncode

    def execute(self, request):
        return ExecutionResult(
            command=request.command,
            returncode=self._returncode,
            stdout=self._stdout,
            stderr="",
            backend=self.name,
        )


async def _execute_verifier_task(
    tmp_path: Path,
    actor_id: str,
    role: str,
    stdout_text: str,
    returncode: int = 0,
):
    backend_factory = lambda **kwargs: MockExecutionBackend(
        stdout=stdout_text, returncode=returncode, **kwargs
    )
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
        job_id="job_verifier_test",
    )

    exec_mgr = ExecutionManager()
    exec_mgr.register_adapter(actor_id, adapter)

    cap_reg = CapabilityRegistry()
    cap_reg.register_actor({"id": actor_id, "capabilities": ["verification"]})

    scheduler = ReactiveScheduler(capability_registry=cap_reg)

    graph = TaskGraph()
    task = TaskNode(
        task_id=f"T_{role}",
        job_id="job_verifier_test",
        assigned_actor=actor_id,
        status=TaskStatus.READY,
        max_attempts=1,
        metadata={"role": role, "backend": MockExecutionBackend.name},
    )
    graph.add_task(task)

    coros = await scheduler.schedule_ready_tasks(graph, exec_mgr)
    results = await asyncio.gather(*coros)
    executed_task, exec_result = results[0]
    return executed_task, exec_result


@pytest.mark.anyio
async def test_verifier_nested_failed_verdict_is_not_succeeded(tmp_path: Path):
    """
    A verifier-role task whose Claude JSON envelope result text contains a nested
    verdict of failed, with process exit code 0, must not be recorded SUCCEEDED.
    """
    verdict_payload = {
        "verdict": "failed",
        "summary": "T3 deliverables are absent: contract tests were not written.",
        "repairable": True,
        "blocked_by": None,
        "findings": ["deliverables missing"],
    }
    claude_stdout = json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": f"```json\n{json.dumps(verdict_payload, indent=2)}\n```",
    })

    task, exec_result = await _execute_verifier_task(
        tmp_path,
        actor_id="claude",
        role="verifier",
        stdout_text=claude_stdout,
        returncode=0,
    )

    assert exec_result.status != "succeeded"
    assert exec_result.status == "failed"
    assert task.status != TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_verifier_without_valid_verdict_fails_closed(tmp_path: Path):
    """
    A verifier or security task with no parseable verdict must be recorded FAILED.
    """
    for idx, role in enumerate(("verifier", "security")):
        claude_stdout = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Completed review with no issues noted, but missing structured verdict.",
        })

        task, exec_result = await _execute_verifier_task(
            tmp_path / f"case_{idx}_{role}",
            actor_id="claude",
            role=role,
            stdout_text=claude_stdout,
            returncode=0,
        )

        assert exec_result.status == "failed"
        assert task.status == TaskStatus.FAILED


@pytest.mark.anyio
async def test_verifier_passed_verdict_still_succeeds(tmp_path: Path):
    """
    Control test: a verifier task with an explicit passed verdict still succeeds.
    """
    codex_stdout = json.dumps({
        "verdict": "passed",
        "summary": "All verification assertions passed.",
        "findings": [],
    })

    task, exec_result = await _execute_verifier_task(
        tmp_path,
        actor_id="codex",
        role="verifier",
        stdout_text=codex_stdout,
        returncode=0,
    )

    assert exec_result.status == "succeeded"
    assert task.status == TaskStatus.SUCCEEDED
    assert exec_result.metadata.get("verdict") == "passed"
