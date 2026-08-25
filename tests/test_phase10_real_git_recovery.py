import asyncio
import os
from pathlib import Path
import subprocess
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskNode, TaskStatus
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.verification import VerificationResult, VerificationStatus, CallableVerifierAdapter
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.recovery import RecoveryManager
from runtime.engine import ReactiveJobEngine


def init_git_repo(repo_dir: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hermes Test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "hermes@test.local"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=repo_dir, check=True)
    # Create integration branch
    subprocess.run(["git", "branch", "sprint/recovery_test/integration"], cwd=repo_dir, check=True)


@pytest.mark.anyio
async def test_true_crash_after_git_commit_reconciliation(tmp_path: Path):
    """
    True crash-after-merge-before-task.completed E2E test:
    Phase 1 writes code, commits to Git, and merges into integration branch.
    Simulates crash immediately after Git integration merge, before task.completed is emitted.
    Reconciliation inspects real Git repository log, reconciles Phase 1 as SUCCEEDED,
    and resumes execution seamlessly to Phase 2.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    init_git_repo(repo_dir)

    target_branch = "sprint/recovery_test/integration"

    store = InMemoryRuntimeEventStore()
    bridge_1 = RuntimeEventBridge(event_store=store)

    job = JobRecord(
        job_id="job_real_git_crash",
        goal="Implement fullstack module with real git commit",
        repository=str(repo_dir),
        branch=target_branch,
    )
    await bridge_1.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge_1.emit_job_state_changed(job, previous_state=JobState.CREATED)

    t1 = TaskNode(
        task_id="phase_1",
        job_id="job_real_git_crash",
        description="Phase 1: Backend service",
        metadata={
            "commit_message": "feat(phase_1): add backend service",
            "base_branch": target_branch,
        },
    )
    t2 = TaskNode(
        task_id="phase_2",
        job_id="job_real_git_crash",
        description="Phase 2: Frontend client",
        dependencies=["phase_1"],
        metadata={
            "commit_message": "feat(phase_2): add frontend client",
            "base_branch": target_branch,
        },
    )
    await bridge_1.emit_task_created(t1)
    await bridge_1.emit_task_created(t2)

    # 1. Phase 1 starts
    await bridge_1.emit_task_started(t1, actor_id="backend_agent")

    # 2. Phase 1 executes on Git: writes file and commits to target branch
    subprocess.run(["git", "checkout", target_branch], cwd=repo_dir, check=True, capture_output=True)
    (repo_dir / "backend.py").write_text("def run_backend(): return True\n", encoding="utf-8")
    subprocess.run(["git", "add", "backend.py"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "feat(phase_1): add backend service"], cwd=repo_dir, check=True)

    # 3. CRASH OCCURS HERE:
    # Process dies right after git commit / merge, BEFORE emit_task_completed was called!
    del bridge_1
    del job

    # Verify event store shows phase_1 is still RUNNING
    events_in_store = await store.list_events("job_real_git_crash")
    assert "task.completed" not in [e.event_type for e in events_in_store]

    # 4. Resume engine from canonical store
    bridge_2 = RuntimeEventBridge(event_store=store)
    manager = RecoveryManager(event_store=store)
    engine_2, metrics = await manager.recover_and_rehydrate(
        job_id="job_real_git_crash",
        event_bridge=bridge_2,
    )

    # Assert Phase 1 was durably reconciled from real Git log evidence
    assert "phase_1" in metrics.reconciled_tasks
    assert engine_2.graph.get_task("phase_1").status == TaskStatus.SUCCEEDED
    assert engine_2.graph.get_task("phase_2") in engine_2.graph.find_ready_tasks()

    # Wire Phase 2 execution adapter
    executed_phases = []

    async def session2_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        executed_phases.append(task.task_id)
        if task.task_id == "phase_2":
            subprocess.run(["git", "checkout", target_branch], cwd=repo_dir, check=True, capture_output=True)
            (repo_dir / "frontend.js").write_text("export const run = () => true;\n", encoding="utf-8")
            subprocess.run(["git", "add", "frontend.js"], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-m", "feat(phase_2): add frontend client"], cwd=repo_dir, check=True)
            return TaskExecutionResult(status="succeeded")
        return TaskExecutionResult(status="succeeded")

    engine_2.set_default_execution_adapter(session2_adapter)
    engine_2.set_verifier(CallableVerifierAdapter(lambda j, g, a, c: VerificationResult(
        status=VerificationStatus.PASSED,
        summary="All real git commits verified",
    )))

    # Step: Phase 2 executes
    await engine_2.step()
    assert engine_2.graph.get_task("phase_2").status == TaskStatus.SUCCEEDED
    assert executed_phases == ["phase_2"]  # Phase 1 was NEVER rerun!

    # Step: Verification and terminal completion
    await engine_2.step()
    assert engine_2.job.state == JobState.COMPLETED
