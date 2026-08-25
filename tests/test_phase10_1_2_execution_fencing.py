import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
import time
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskNode, TaskStatus
from runtime.execution import AgentRun, AgentRunStatus, TaskExecutionResult
from runtime.hermes_adapter import HermesActorAdapter
from runtime.engine import ReactiveJobEngine
from runtime.lease import InMemoryJobLeaseStore, JobLeaseManager
from runtime.storage.projector import RuntimeStateProjector
from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.recovery import InterruptedTaskReconciler, RecoveryDisposition
from runner.agents.base import AgentAdapter, AgentContext
from runner.agents.registry import AgentRegistry


def init_git_repo(repo_dir: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hermes Test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "hermes@test.local"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=repo_dir, check=True)
    subprocess.run(["git", "branch", "sprint/integration"], cwd=repo_dir, check=True)


class BlockingAgentAdapter(AgentAdapter):
    """Custom test agent that blocks until explicitly signaled, simulating long model generation."""
    name = "blocking_agent"

    def __init__(self, block_event: threading.Event, continue_event: threading.Event):
        self.block_event = block_event
        self.continue_event = continue_event

    def build_command(self, context: AgentContext):
        return ["echo", "blocking"]

    def validate_result(self, result, context: AgentContext):
        return result

    def execute(self, context: AgentContext):
        # Notify test that agent is actively executing inside its worktree
        (context.worktree / "solution.py").write_text("print('fenced mutation attempt')\n", encoding="utf-8")
        self.block_event.set()

        # Wait until test signals continuation
        self.continue_event.wait(timeout=5.0)
        from runner.backends.base import ExecutionResult
        return ExecutionResult(command=("mock",), returncode=0, stdout="done", stderr="", backend="test")


@pytest.mark.anyio
async def test_blocking_worker_fenced_loses_lease_and_integration_head_unchanged(tmp_path: Path):
    """
    Core Phase 10.1.2 invariant:
    1. Real HermesActorAdapter starts a worker modifying a task worktree.
    2. Worker blocks mid-flight.
    3. Execution lease is lost / engine is fenced.
    4. Worker unblocks and attempts authoritative Git commit/merge.
    5. Fencing check fails closed; integration branch HEAD remains unchanged.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    init_git_repo(repo_dir)

    # Get initial integration HEAD
    head_res = subprocess.run(["git", "rev-parse", "sprint/integration"], cwd=repo_dir, capture_output=True, text=True, check=True)
    initial_integration_head = head_res.stdout.strip()

    block_evt = threading.Event()
    continue_evt = threading.Event()
    blocking_agent = BlockingAgentAdapter(block_evt, continue_evt)

    reg = AgentRegistry()
    reg.register(blocking_agent)

    worktree_root = tmp_path / "worktrees"
    adapter = HermesActorAdapter(
        target_repo=repo_dir,
        worktree_root=worktree_root,
        run_dir=tmp_path / "runs",
        agent_registry=reg,
        job_id="job_fencing_1012",
        target_branch="sprint/integration",
    )

    task = TaskNode(
        task_id="T_BLOCKING",
        job_id="job_fencing_1012",
        description="Write solution.py",
        assigned_actor="blocking_agent",
        metadata={"role": "builder"},
    )
    run = AgentRun(run_id="run_block_1", job_id="job_fencing_1012", task_id="T_BLOCKING", actor_id="blocking_agent")

    engine = ReactiveJobEngine(job_id="job_fencing_1012", goal="Test Authoritative Fencing", actor_adapter=adapter)
    context = {"engine": engine, "job": {"job_id": "job_fencing_1012"}}

    # Launch execution in background thread
    exec_task = asyncio.create_task(adapter.execute_task(task, run, context=context))

    # Wait for agent to block inside worktree
    await asyncio.to_thread(block_evt.wait, 5.0)
    assert block_evt.is_set()

    # Now fence the engine (e.g. heartbeat failure or lost lease)
    await engine.fence("Lost execution lease during worker generation")
    assert adapter.is_fenced is True

    # Release blocked worker so it tries to commit and merge into integration branch
    continue_evt.set()

    # Worker execution should finish with failure due to fencing
    res = await exec_task
    assert res.status == "failed"
    assert "fenced" in (res.error or "").lower()

    # Verify that integration branch HEAD was NOT modified!
    head_after = subprocess.run(["git", "rev-parse", "sprint/integration"], cwd=repo_dir, capture_output=True, text=True, check=True).stdout.strip()
    assert head_after == initial_integration_head


@pytest.mark.anyio
async def test_atomic_task_rerouted_projection():
    """
    Verifies that task.rerouted is projected as a single atomic transition
    updating assigned actor, resetting status to READY, and capturing telemetry.
    """
    events = [
        StoredRuntimeEvent(
            event_id="e1",
            job_id="job_reroute_test",
            sequence=1,
            event_type="job.created",
            payload={"job_id": "job_reroute_test", "goal": "Reroute Test", "metadata": {}},
            occurred_at=datetime.now(timezone.utc).isoformat(),
        ),
        StoredRuntimeEvent(
            event_id="e2",
            job_id="job_reroute_test",
            sequence=2,
            event_type="task.created",
            task_id="T1",
            payload={"task_id": "T1", "name": "Task 1", "assigned_actor": "actor_slow"},
            occurred_at=datetime.now(timezone.utc).isoformat(),
        ),
        StoredRuntimeEvent(
            event_id="e3",
            job_id="job_reroute_test",
            sequence=3,
            event_type="task.rerouted",
            task_id="T1",
            payload={
                "task_id": "T1",
                "from_actor": "actor_slow",
                "to_actor": "actor_fast",
                "reason": "rate_limit_exceeded",
            },
            occurred_at=datetime.now(timezone.utc).isoformat(),
        ),
    ]

    projected = RuntimeStateProjector.project(events)
    t1 = projected.graph.get_task("T1")
    assert t1 is not None
    assert t1.assigned_actor == "actor_fast"
    assert t1.status == TaskStatus.READY
    assert t1.metadata["last_reroute_reason"] == "rate_limit_exceeded"
    assert t1.metadata["previous_actor"] == "actor_slow"


def test_interrupted_reconciliation_verifies_integration_baseline_sha(tmp_path: Path):
    """
    Verifies that InterruptedTaskReconciler checks ancestor relation to integration_baseline_sha.
    A commit on an unrelated branch or prior commit is rejected if it is not a descendant of baseline.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    init_git_repo(repo_dir)

    # Base commit
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True).stdout.strip()

    # Candidate commit built on top of base
    (repo_dir / "file1.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "file1.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "feat(phase_A): task commit"], cwd=repo_dir, check=True)
    valid_commit_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True).stdout.strip()

    now_iso = datetime.now(timezone.utc).isoformat()
    t1 = TaskNode(
        task_id="phase_A",
        job_id="job_base_test",
        status=TaskStatus.RUNNING,
        started_at=now_iso,
        metadata={"commit_message": "feat(phase_A): task commit"},
    )

    # 1. Matching commit with correct baseline sha -> RECONCILE
    disp, evidence = InterruptedTaskReconciler.evaluate(
        task=t1,
        runs=[],
        artifacts=[],
        events=[],
        repo_path=repo_dir,
        target_branch="main",
        job_created_at=now_iso,
        integration_baseline_sha=base_sha,
    )
    assert disp == RecoveryDisposition.RECONCILE_INTERRUPTED
    assert evidence.get("commit_sha") == valid_commit_sha

    # 2. Candidate commit is identical to baseline sha (no new work) -> RETRY_ELIGIBLE
    t_stale = TaskNode(
        task_id="phase_A",
        job_id="job_base_test",
        status=TaskStatus.RUNNING,
        started_at=now_iso,
        metadata={"commit_message": "chore: initial commit"},
    )
    disp2, evidence2 = InterruptedTaskReconciler.evaluate(
        task=t_stale,
        runs=[],
        artifacts=[],
        events=[],
        repo_path=repo_dir,
        target_branch="main",
        job_created_at=now_iso,
        integration_baseline_sha=base_sha,
    )
    assert disp2 == RecoveryDisposition.RETRY_ELIGIBLE
