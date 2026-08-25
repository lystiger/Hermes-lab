import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import subprocess
import json
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskNode, TaskStatus
from runtime.lease import InMemoryJobLeaseStore, JobLeaseManager
from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.recovery import RecoveryManager, InterruptedTaskReconciler, RecoveryDisposition
from jobs.job_launcher import JobLauncher
from jobs.job_service import job_service


@pytest.mark.anyio
async def test_single_canonical_resume_owner_id_across_lifecycle(tmp_path: Path):
    """
    Test 1: Verification that a single canonical owner_id is generated and used
    for lease acquisition, heartbeat loop, and release during resume_async.
    """
    sprints_dir = tmp_path / "sprints"
    sprints_dir.mkdir()
    sprint_spec = {
        "name": "Sprint Fencing Test",
        "target_repo": str(tmp_path),
        "phases": [{"name": "p1"}],
    }
    (sprints_dir / "sprint_fence.json").write_text(json.dumps(sprint_spec), encoding="utf-8")

    event_store = InMemoryRuntimeEventStore()
    lease_store = InMemoryJobLeaseStore()

    from runtime.storage.config import set_global_event_store, set_global_lease_store
    set_global_event_store(event_store)
    set_global_lease_store(lease_store)

    job_id = "run_20260825_120000_sprint_fence"
    bridge = RuntimeEventBridge(event_store=event_store)
    job = JobRecord(
        job_id=job_id,
        goal="Test Lease Owner",
        metadata={"sprint_id": "sprint_fence"},
    )
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    launcher = JobLauncher(sprints_dir=sprints_dir)
    res = await launcher.resume_async(job_id=job_id, owner_id="custom_worker_node_42")

    assert res["resumed"] is True
    # Verify lease was acquired by custom_worker_node_42
    lease = await lease_store.get_lease(job_id)
    assert lease is not None
    assert lease.owner_id == "custom_worker_node_42"

    # Verify launcher stored the exact same owner in its tracker
    assert launcher._lease_managers[job_id][2] == "custom_worker_node_42"

    # Cancel and verify release uses the exact same owner
    await launcher.cancel_async(job_id)
    lease_after = await lease_store.get_lease(job_id)
    assert lease_after is None


@pytest.mark.anyio
async def test_lease_heartbeat_failure_fences_engine():
    """
    Test 2: When lease heartbeat renewal fails (e.g. lease stolen or expired),
    the on_lease_lost callback fires immediately, fencing the ReactiveJobEngine
    and halting execution.
    """
    lease_store = InMemoryJobLeaseStore()
    engine = ReactiveJobEngine(
        job_id="job_fence_test",
        goal="Test Fencing",
    )
    t1 = TaskNode(task_id="T1", job_id="job_fence_test", description="Running Task")
    await engine.initialize_and_plan(initial_tasks=[t1])

    # Acquire lease for owner_A
    mgr = JobLeaseManager(
        lease_store=lease_store,
        owner_id="owner_A",
        duration_seconds=10.0,
        heartbeat_interval_seconds=0.05,
        on_lease_lost=lambda jid: engine.fence(f"Lease lost for {jid}"),
    )
    await mgr.acquire_and_start_heartbeat("job_fence_test")

    # Simulate another worker taking over the lease after expiration (owner_B)
    lease_store._leases["job_fence_test"].owner_id = "owner_B"

    # Wait for heartbeat tick to fail and trigger fencing
    await asyncio.sleep(0.12)

    # Engine must now be fenced and in BLOCKED state
    assert getattr(engine, "_fenced", False) is True
    assert engine.job.state == JobState.BLOCKED

    # Step must immediately reject further execution
    should_continue = await engine.step()
    assert should_continue is False

    await mgr.release_and_stop_heartbeat("job_fence_test")


@pytest.mark.anyio
async def test_sprint_identity_persisted_in_canonical_job_metadata(tmp_path: Path):
    """
    Test 3: Sprint identity and specification metadata are durably stamped onto JobRecord
    and emitted at creation time, preserving identity across storage projection.
    """
    sprints_dir = tmp_path / "sprints"
    sprints_dir.mkdir()
    sprint_spec = {
        "name": "Canonical Sprint Alpha",
        "target_repo": str(tmp_path),
        "target_branch": "sprint/alpha/integration",
        "phases": [{"name": "phase_1", "role": "builder"}],
    }
    (sprints_dir / "sprint_alpha.json").write_text(json.dumps(sprint_spec), encoding="utf-8")

    event_store = InMemoryRuntimeEventStore()
    from runtime.storage.config import set_global_event_store
    set_global_event_store(event_store)

    launcher = JobLauncher(sprints_dir=sprints_dir)
    res = launcher.launch(sprint_id="sprint_alpha", start_background=False)
    job_id = res["jobId"]

    # Retrieve engine from job_service
    eng = job_service.get_engine(job_id)
    assert eng is not None
    await eng.step()  # triggers initialize_and_plan and emit_job_created

    # Inspect events in canonical store
    events = await event_store.list_events(job_id)
    created_event = next(e for e in events if e.event_type == "job.created")
    assert created_event.payload["metadata"]["sprint_id"] == "sprint_alpha"
    assert created_event.payload["metadata"]["spec_name"] == "Canonical Sprint Alpha"

    # Project state from canonical store
    projected = RuntimeStateProjector.project(events)
    assert projected.job.metadata["sprint_id"] == "sprint_alpha"
    assert projected.job.metadata["target_branch"] == "sprint/alpha/integration"


def init_git_repo(repo_dir: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hermes Test"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "hermes@test.local"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=repo_dir, check=True)
    subprocess.run(["git", "branch", "sprint/scoped_git/integration"], cwd=repo_dir, check=True)


def test_scoped_git_reconciliation_rejects_stale_commits(tmp_path: Path):
    """
    Test 4: InterruptedTaskReconciler rejects commits created before the job/task lifecycle,
    even if the commit message matches, and only accepts commits created within the current run.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    init_git_repo(repo_dir)
    target_branch = "sprint/scoped_git/integration"

    subprocess.run(["git", "checkout", target_branch], cwd=repo_dir, check=True, capture_output=True)

    # 1. Create a STALE commit with matching message from "yesterday"
    (repo_dir / "stale.py").write_text("# stale\n", encoding="utf-8")
    subprocess.run(["git", "add", "stale.py"], cwd=repo_dir, check=True)
    old_env = {
        **subprocess.os.environ,
        "GIT_AUTHOR_DATE": "2026-01-01T12:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-01T12:00:00Z",
    }
    subprocess.run(["git", "commit", "-m", "feat(phase_1): add backend service"], cwd=repo_dir, env=old_env, check=True)

    # Now create a current task started NOW (e.g. 2026-08-25)
    now_iso = datetime.now(timezone.utc).isoformat()
    t1 = TaskNode(
        task_id="phase_1",
        job_id="job_scoped_test",
        status=TaskStatus.RUNNING,
        started_at=now_iso,
        metadata={"commit_message": "feat(phase_1): add backend service"},
    )

    # Reconciler should reject the stale 2026-01-01 commit!
    disposition, evidence = InterruptedTaskReconciler.evaluate(
        task=t1,
        runs=[],
        artifacts=[],
        events=[],
        repo_path=repo_dir,
        target_branch=target_branch,
        job_created_at=now_iso,
    )
    assert disposition == RecoveryDisposition.RETRY_ELIGIBLE
    assert evidence.get("integrated") is not True

    # 2. Create a FRESH commit created right now
    (repo_dir / "fresh.py").write_text("# fresh\n", encoding="utf-8")
    subprocess.run(["git", "add", "fresh.py"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "feat(phase_1): add backend service"], cwd=repo_dir, check=True)

    # Reconciler should now accept the fresh commit!
    disposition_fresh, evidence_fresh = InterruptedTaskReconciler.evaluate(
        task=t1,
        runs=[],
        artifacts=[],
        events=[],
        repo_path=repo_dir,
        target_branch=target_branch,
        job_created_at=now_iso,
    )
    assert disposition_fresh == RecoveryDisposition.RECONCILE_INTERRUPTED
    assert evidence_fresh.get("integrated") is True
    assert evidence_fresh.get("commit_sha") is not None
