"""A restart resumes goal-planned jobs with the settings they were launched with."""
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from jobs.job_launcher import JobLauncher
from jobs.job_service import job_service
from runtime.capacity import CapacityRegistry, ProviderFailureClass
from runtime.hermes_adapter import HermesActorAdapter
from runtime.job_state import JobState
from runtime.lease import InMemoryJobLeaseStore
from runtime.limits import RuntimeLimits
from runtime.planning.planner import GroundedPlanner
from runtime.recovery import restore_provider_limits
from runtime.storage import config as storage_config
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.task_graph import TaskNode
from tests.test_goal_route import make_repo, plan_json


@pytest.fixture
def stores(monkeypatch):
    events, leases = InMemoryRuntimeEventStore(), InMemoryJobLeaseStore()
    monkeypatch.setattr(storage_config, "_GLOBAL_EVENT_STORE", events)
    monkeypatch.setattr(storage_config, "_GLOBAL_LEASE_STORE", leases)
    return events, leases


async def planned_job(tmp_path, **kwargs):
    """A goal-planned job whose plan exists but whose tasks have not run, as if Hermes stopped there."""
    repo = make_repo(tmp_path / "repo")

    async def model(prompt):
        return plan_json("Add an API")

    res = await JobLauncher().launch_goal_async(goal="Add an API", target_repo=repo, model_client=model, dry_run=True,
                                                skip_agent_exec=True, start_background=False, **kwargs)
    job_id = res["jobId"]
    job_service._engines.pop(job_id, None)  # the process that ran it is gone
    return job_id


@pytest.mark.anyio
async def test_a_resumed_goal_job_gets_its_launch_settings_back(tmp_path, stores):
    limits = RuntimeLimits(max_repairs_per_job=1, max_engine_steps=40)
    job_id = await planned_job(tmp_path, target_subdir="app", exclude_agents=["antigravity"], limits=limits)
    launcher = JobLauncher()
    launcher._start_engine_background = lambda engine: None

    await launcher.resume_async(job_id)
    engine = job_service.get_engine(job_id)

    actor = engine.execution_manager._default_adapter
    assert isinstance(actor, HermesActorAdapter) and actor.target_subdir == "app" and actor.skip_agent_exec
    assert isinstance(engine.planner, GroundedPlanner) and engine.planner.repairs_failed_verdicts
    assert engine.limits.max_repairs_per_job == 1 and engine.limits.max_engine_steps == 40
    assert "antigravity" not in {a.id for a in engine.scheduler.capability_registry.list_actors()}
    assert {t.task_id for t in engine.graph.list_tasks()} == {"build_api", "harden_api", "verify_api"}

    for task in launcher._lease_managers.values():
        task[1].cancel()


@pytest.mark.anyio
async def test_a_resumed_goal_job_runs_to_completion(tmp_path, stores):
    job_id = await planned_job(tmp_path)
    launcher = JobLauncher()
    launcher._start_engine_background = lambda engine: None

    await launcher.resume_async(job_id)
    job = await job_service.get_engine(job_id).run_until_complete()

    assert job.state == JobState.COMPLETED
    launcher._lease_managers[job_id][1].cancel()


@pytest.mark.anyio
async def test_startup_resumes_orphaned_goal_jobs_once_the_dead_owners_lease_expires(tmp_path, stores):
    _, leases = stores
    job_id = await planned_job(tmp_path)
    await leases.acquire_lease(job_id, "dead-process", duration_seconds=0.3)
    launcher = JobLauncher()
    launcher._start_engine_background = lambda engine: None

    assert await launcher.resume_orphaned_goal_jobs(lease_wait_seconds=5) == [job_id]
    assert (await leases.get_lease(job_id)).owner_id != "dead-process"
    launcher._lease_managers[job_id][1].cancel()


@pytest.mark.anyio
async def test_startup_leaves_a_job_another_live_process_holds(tmp_path, stores):
    _, leases = stores
    job_id = await planned_job(tmp_path)
    await leases.acquire_lease(job_id, "live-process", duration_seconds=60)
    launcher = JobLauncher()
    launcher._start_engine_background = lambda engine: None

    assert await launcher.resume_orphaned_goal_jobs(lease_wait_seconds=0.2) == []
    assert (await leases.get_lease(job_id)).owner_id == "live-process"


def limit_event(kind, provider, resets_at, seq):
    return StoredRuntimeEvent(event_id=f"e{seq}", job_id="j", sequence=seq, event_type=kind,
                              occurred_at=datetime.now(timezone.utc).isoformat(), payload={"providerId": provider, "resetsAt": resets_at.isoformat()})


def test_a_usage_limit_in_force_is_restored_and_an_expired_one_is_not():
    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    registry = CapacityRegistry()
    events = [
        limit_event("provider.quota_exhausted", "anthropic", now + timedelta(hours=2), 1),
        limit_event("provider.rate_limited", "openai", now - timedelta(minutes=1), 2),
    ]

    restored = restore_provider_limits(events, registry, now=now)

    assert list(restored) == ["anthropic"]
    assert not registry.is_provider_available("anthropic")
    assert registry.is_provider_available("openai")


def test_the_latest_limit_event_for_a_provider_wins():
    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    events = [
        limit_event("provider.quota_exhausted", "anthropic", now + timedelta(hours=2), 1),
        limit_event("provider.rate_limited", "anthropic", now - timedelta(seconds=1), 2),
    ]
    assert restore_provider_limits(events, CapacityRegistry(), now=now) == {}


@pytest.mark.anyio
async def test_quota_events_record_when_the_limit_resets(stores):
    from runtime.events import RuntimeEventBridge

    events, _ = stores
    await RuntimeEventBridge(event_store=events).emit_provider_quota_exhausted("anthropic", job_id="j", retry_after=600)
    payload = (await events.list_events("j"))[-1].payload
    resets_at = datetime.fromisoformat(payload["resetsAt"])
    assert timedelta(minutes=9) < resets_at - datetime.now(timezone.utc) <= timedelta(minutes=10)


def test_a_reused_worktree_drops_files_an_interrupted_attempt_left(tmp_path):
    repo = make_repo(tmp_path / "repo")
    adapter = HermesActorAdapter(target_repo=repo, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    path = adapter._ensure_worktree(tmp_path / "wt" / "t", branch="task/t", base_branch="main")
    (path / "half_written.py").write_text("x = (")
    (path / "app" / "api.py").write_text("broken")

    adapter._ensure_worktree(path, branch="task/t", base_branch="main")

    assert not (path / "half_written.py").exists()
    assert (path / "app" / "api.py").read_text() == "def route():\n    return 1\n"
    subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, capture_output=True)


def test_the_engine_step_cap_comes_from_the_limits():
    assert RuntimeLimits().max_engine_steps == 500
    assert RuntimeLimits.from_dict({"maxEngineSteps": 900}).max_engine_steps == 900


def test_a_task_worktree_gets_the_repos_venv_but_never_commits_it(tmp_path):
    repo = make_repo(tmp_path / "repo")
    (repo / ".gitignore").write_text(".venv/\n")
    (repo / ".venv" / "bin").mkdir(parents=True)
    subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "ignore venv"], cwd=repo, check=True)
    adapter = HermesActorAdapter(target_repo=repo, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    path = adapter._ensure_worktree(tmp_path / "wt" / "t", branch="task/t", base_branch="main")

    adapter._seed_dependencies(path)

    assert (path / ".venv").is_symlink() and (path / ".venv" / "bin").is_dir()
    assert adapter.inspect_changed_files(path) == []
    (path / "app" / "new.py").write_text("x = 1\n")
    assert adapter.inspect_changed_files(path) == ["?? app/new.py"]
    subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, capture_output=True)


def test_a_verifier_is_told_what_the_job_changed(tmp_path):
    repo = make_repo(tmp_path / "repo")
    adapter = HermesActorAdapter(target_repo=repo, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    path = adapter._ensure_worktree(tmp_path / "wt" / "v", branch="task/v", base_branch="main")
    (path / "app" / "api.py").write_text("def route():\n    return 2\n")
    subprocess.run(["git", "commit", "-qam", "change"], cwd=path, check=True)

    section = adapter._job_changes_section(path)

    assert "M\tapp/api.py" in section and "+    return 2" in section
    assert "do not\nneed" not in section and "no git operations" in section
    subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, capture_output=True)


def test_an_unchanged_job_says_so(tmp_path):
    repo = make_repo(tmp_path / "repo")
    adapter = HermesActorAdapter(target_repo=repo, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    path = adapter._ensure_worktree(tmp_path / "wt" / "v", branch="task/v", base_branch="main")
    assert "has not changed any file yet" in adapter._job_changes_section(path)
    subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, capture_output=True)


def test_agent_prompts_carry_the_role_not_a_persona(tmp_path):
    adapter = HermesActorAdapter(target_repo=tmp_path, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run")
    task = TaskNode(task_id="v", job_id="j", description="Check it", metadata={"role": "verifier"})

    prompt = adapter.build_effective_prompt("Check it", current_agent="codex", role="verifier", task=task)

    assert "AGENT IDENTITY" not in prompt and "Speaking Style" not in prompt
    assert "Your role in this task: verifier." in prompt and "Do not modify any file" in prompt


def test_the_planner_always_reads_the_projects_agent_instructions(tmp_path):
    from runtime.planning.reconnaissance import RepositoryReconnaissance

    (tmp_path / "AGENTS.md").write_text("# Rules\nRun ./scripts/verify before finishing.\n")
    (tmp_path / "skills" / "n8n-workflow").mkdir(parents=True)
    (tmp_path / "skills" / "n8n-workflow" / "SKILL.md").write_text("# n8n workflows\n")
    for i in range(40):
        (tmp_path / f"api_route_model_{i}.py").write_text("x = 1\n")

    evidence = RepositoryReconnaissance.collect(tmp_path, "Add a Discord notifier", limits=RuntimeLimits(max_evidence_files=5))

    paths = [f.path for f in evidence.files]
    assert paths[0] == "AGENTS.md" and "skills/n8n-workflow/SKILL.md" in paths
