"""
Phase 8.1.3 — Async Execution & Fail-Closed Runtime Test Suite.
Verifies:
1. Blocking Hermes agents run off the event loop, concurrently, with serialized Git mutation.
2. Worktree creation failures fail closed instead of degrading to an unversioned directory.
3. Integration fetch/reset failures fail closed instead of running against a stale base.
4. context.root is resolved once, at launcher/spec-normalization time.
5. Tool invocation has no permissive default policy and carries a runtime-stamped requester.
6. OBSERVATION_DISCOVERY performs one bounded graph expansion.
"""

import asyncio
import json
from pathlib import Path
import pytest
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskGraph, TaskNode
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.observations import Observation
from runtime.limits import RuntimeLimits
from runtime.replanning import (
    ProductionPlannerAdapter,
    ReplanReason,
    ReplanRequest,
    GraphMutationType,
    BoundedReplanner,
)
from runtime.hermes_adapter import (
    HermesActorAdapter,
    WorktreeError,
    ContextSpecError,
    resolve_context_spec,
)
from tools.tools import (
    ToolProfile,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolRegistry,
)


@pytest.fixture
def temp_git_repo():
    """Creates a temporary Git repository for worktree testing."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="hermes_813_repo_"))
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hermes 813 Tester"], cwd=str(tmp_dir), check=True)
    subprocess.run(["git", "config", "user.email", "t813@hermes.local"], cwd=str(tmp_dir), check=True)
    (tmp_dir / "README.md").write_text("# Hermes 8.1.3\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(tmp_dir), check=True, capture_output=True)
    yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _make_task(task_id: str, actor: str, **meta) -> TaskNode:
    return TaskNode(
        task_id=task_id,
        job_id="job_813",
        description=f"Task {task_id}",
        assigned_actor=actor,
        metadata=meta,
    )


def _make_run(task_id: str, actor: str) -> AgentRun:
    return AgentRun(run_id=f"run_{task_id}", job_id="job_813", task_id=task_id, actor_id=actor)


# -----------------------------------------------------------------------------
# 1. Async execution: blocking agents run off the event loop, Git stays serialized
# -----------------------------------------------------------------------------

AGENT_BLOCK_SECONDS = 0.6


@pytest.mark.anyio
async def test_concurrent_real_agents_do_not_block_event_loop(temp_git_repo):
    """
    Two real-agent tasks dispatched concurrently must:
      - overlap in wall-clock time (blocking work is off the event loop),
      - leave the event loop responsive while agents block,
      - and still serialize their integration Git mutations into one valid worktree.
    """
    wt_root = temp_git_repo / ".worktrees"
    run_dir = temp_git_repo / ".runs"

    overlap_gate = threading.Barrier(2, timeout=10)
    concurrent_peak = {"value": 0}
    live = {"count": 0}
    live_guard = threading.Lock()

    class BlockingAgent:
        """Blocks the calling thread; fails the barrier if the two never overlap."""

        def __init__(self, name: str):
            self.name = name

        def execute(self, context):
            with live_guard:
                live["count"] += 1
                concurrent_peak["value"] = max(concurrent_peak["value"], live["count"])
            try:
                # Both agents must be inside execute() at the same time or this raises.
                overlap_gate.wait()
                time.sleep(AGENT_BLOCK_SECONDS)
                (context.worktree / f"{self.name}.py").write_text(f"VALUE = '{self.name}'\n")
            finally:
                with live_guard:
                    live["count"] -= 1

            class Res:
                exit_code = 0
                stdout = f"{self.name} done"
                stderr = ""

            return Res()

    class Registry:
        def get(self, name):
            return BlockingAgent(name)

    adapter = HermesActorAdapter(
        target_repo=temp_git_repo,
        worktree_root=wt_root,
        run_dir=run_dir,
        agent_registry=Registry(),
        base_ref="main",
        target_branch="sprint/813/integration",
    )

    # Heartbeat proves the event loop keeps running while both agents block.
    heartbeat = {"ticks": 0, "stop": False}

    async def _heartbeat():
        while not heartbeat["stop"]:
            heartbeat["ticks"] += 1
            await asyncio.sleep(0.01)

    hb_task = asyncio.create_task(_heartbeat())
    started = time.monotonic()

    results = await asyncio.gather(
        adapter.execute_task(
            task=_make_task("alpha", "agent_alpha", worktree_dir="wt_alpha", branch="sprint/813/alpha"),
            run=_make_run("alpha", "agent_alpha"),
        ),
        adapter.execute_task(
            task=_make_task("beta", "agent_beta", worktree_dir="wt_beta", branch="sprint/813/beta"),
            run=_make_run("beta", "agent_beta"),
        ),
    )

    elapsed = time.monotonic() - started
    heartbeat["stop"] = True
    await hb_task

    assert [r.status for r in results] == ["succeeded", "succeeded"], [r.error for r in results]

    # Both agents were genuinely in flight together.
    assert concurrent_peak["value"] == 2
    # Concurrent, not serial: two 0.6s agents plus Git overhead, well under the 1.2s serial floor.
    assert elapsed < (AGENT_BLOCK_SECONDS * 2), f"execution serialized: {elapsed:.2f}s"
    # The loop kept scheduling while both agents blocked their threads.
    assert heartbeat["ticks"] > 5, f"event loop stalled: only {heartbeat['ticks']} ticks"

    # Git mutations were serialized into one consistent integration worktree.
    integration = wt_root / "integration"
    assert adapter._is_git_repo(integration)
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(integration), capture_output=True, text=True
    ).stdout
    assert "feat(alpha)" in log
    assert "feat(beta)" in log
    assert (integration / "agent_alpha.py").exists()
    assert (integration / "agent_beta.py").exists()

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(integration), capture_output=True, text=True
    ).stdout
    assert status.strip() == "", f"integration worktree left dirty: {status}"


# -----------------------------------------------------------------------------
# 2. Fail closed on worktree creation
# -----------------------------------------------------------------------------

def test_ensure_worktree_raises_instead_of_falling_back_to_plain_directory(temp_git_repo):
    """A failed `git worktree add` must raise, never degrade to an unversioned directory."""
    wt_root = temp_git_repo / ".worktrees"
    adapter = HermesActorAdapter(target_repo=temp_git_repo, worktree_root=wt_root)

    target = wt_root / "wt_bad_base"
    with pytest.raises(WorktreeError) as excinfo:
        adapter._ensure_worktree(target, branch="sprint/nope", base_branch="does-not-exist")

    assert "worktree creation failed" in str(excinfo.value).lower()
    assert not adapter._is_git_repo(target)


def test_ensure_worktree_refuses_occupied_non_git_directory(temp_git_repo):
    """An existing non-Git directory at the worktree path is refused, not reused."""
    wt_root = temp_git_repo / ".worktrees"
    adapter = HermesActorAdapter(target_repo=temp_git_repo, worktree_root=wt_root)

    squatter = wt_root / "wt_squatted"
    squatter.mkdir(parents=True)
    (squatter / "leftover.txt").write_text("stale untracked content")

    with pytest.raises(WorktreeError) as excinfo:
        adapter._ensure_worktree(squatter, branch="sprint/squat", base_branch="main")

    assert "not a Git worktree" in str(excinfo.value)


@pytest.mark.anyio
async def test_worktree_failure_fails_task_closed_without_running_agent(temp_git_repo):
    """
    Regression: a worktree that cannot be created must fail the task with a worktree_error
    exit reason, and the agent must never be invoked against an unversioned tree.
    """
    wt_root = temp_git_repo / ".worktrees"
    invoked: List[str] = []

    class ShouldNotRunAgent:
        name = "never"

        def execute(self, context):
            invoked.append(context.worktree.name)
            raise AssertionError("agent must not run when the worktree could not be prepared")

    class Registry:
        def get(self, name):
            return ShouldNotRunAgent()

    adapter = HermesActorAdapter(
        target_repo=temp_git_repo,
        worktree_root=wt_root,
        run_dir=temp_git_repo / ".runs",
        agent_registry=Registry(),
        base_ref="no-such-base-ref",
        target_branch="sprint/813/integration",
    )

    result = await adapter.execute_task(
        task=_make_task("doomed", "never", worktree_dir="wt_doomed", branch="sprint/813/doomed"),
        run=_make_run("doomed", "never"),
    )

    assert result.status == "failed"
    assert result.exit_reason == "worktree_error"
    assert result.metadata.get("fail_closed") is True
    assert invoked == []
    assert not (wt_root / "wt_doomed").exists()


# -----------------------------------------------------------------------------
# 3. Fail closed on integration fetch/reset
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_integration_sync_failure_fails_task_closed(temp_git_repo):
    """
    Regression: a failed fetch/reset from the integration branch must fail the task rather
    than silently leaving the agent to build on a stale base.
    """
    wt_root = temp_git_repo / ".worktrees"
    invoked: List[str] = []

    class ShouldNotRunAgent:
        name = "never"

        def execute(self, context):
            invoked.append(context.worktree.name)
            raise AssertionError("agent must not run against an unsynchronized worktree")

    class Registry:
        def get(self, name):
            return ShouldNotRunAgent()

    adapter = HermesActorAdapter(
        target_repo=temp_git_repo,
        worktree_root=wt_root,
        run_dir=temp_git_repo / ".runs",
        agent_registry=Registry(),
        base_ref="main",
        target_branch="sprint/813/integration",
    )

    real_run_cmd = adapter.run_cmd

    def failing_fetch(cmd, cwd=None, check=True):
        if cmd[:2] == ["git", "fetch"]:
            raise RuntimeError("Git command failed: could not read from remote repository")
        return real_run_cmd(cmd, cwd=cwd, check=check)

    adapter.run_cmd = failing_fetch

    result = await adapter.execute_task(
        task=_make_task("stale", "never", worktree_dir="wt_stale", branch="sprint/813/stale"),
        run=_make_run("stale", "never"),
    )

    assert result.status == "failed"
    assert result.exit_reason == "worktree_error"
    assert "synchronize" in str(result.error).lower()
    assert invoked == []

    # No commit was produced on the integration branch from this task.
    integration = wt_root / "integration"
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(integration), capture_output=True, text=True
    ).stdout
    assert "stale" not in log


def test_sync_raises_when_worktree_is_not_a_git_worktree(temp_git_repo):
    """Synchronizing a directory that is not a worktree of the repo is an error, not a warning."""
    adapter = HermesActorAdapter(target_repo=temp_git_repo, worktree_root=temp_git_repo / ".worktrees")
    bogus = temp_git_repo / ".worktrees" / "not_a_worktree"
    bogus.mkdir(parents=True)

    with pytest.raises(WorktreeError):
        adapter.sync_task_worktree_from_integration(bogus)


# -----------------------------------------------------------------------------
# 4. context.root resolved at launcher / spec normalization time
# -----------------------------------------------------------------------------

def test_resolve_context_spec_resolves_relative_root_against_spec_dir(tmp_path):
    """context.root is resolved relative to the spec directory, not the working directory."""
    spec_dir = tmp_path / "sprints"
    spec_dir.mkdir()
    ctx_root = tmp_path / "docs"
    ctx_root.mkdir()
    (ctx_root / "architecture.md").write_text("arch")

    normalized = resolve_context_spec(
        {"root": "../docs", "files": ["architecture.md"]},
        spec_dir=spec_dir,
    )

    assert Path(normalized["root"]) == ctx_root.resolve()
    assert normalized["files"] == ["architecture.md"]
    assert normalized["root_resolved"] is True


def test_resolve_context_spec_rejects_escaping_and_missing_roots(tmp_path):
    spec_dir = tmp_path / "sprints"
    spec_dir.mkdir()
    ctx_root = tmp_path / "docs"
    ctx_root.mkdir()
    (ctx_root / "ok.md").write_text("ok")

    with pytest.raises(ContextSpecError):
        resolve_context_spec({"root": "../nowhere", "files": ["ok.md"]}, spec_dir=spec_dir)

    with pytest.raises(ContextSpecError):
        resolve_context_spec({"root": str(ctx_root), "files": ["../outside.md"]}, spec_dir=spec_dir)

    with pytest.raises(ContextSpecError):
        resolve_context_spec({"root": str(ctx_root), "files": []}, spec_dir=spec_dir)


def test_adapter_rejects_unresolved_relative_context_root(tmp_path):
    """
    The adapter never re-resolves context.root itself: an unresolved relative root is a
    specification error, because resolving it here would silently pick a different directory
    than the launcher intended.
    """
    with pytest.raises(ContextSpecError) as excinfo:
        HermesActorAdapter(
            target_repo=tmp_path,
            spec={"context": {"root": "../../LysStack", "files": ["a.md"]}},
        )
    assert "absolute path" in str(excinfo.value)


def test_adapter_loads_context_bundle_from_resolved_root(tmp_path):
    ctx_root = tmp_path / "docs"
    ctx_root.mkdir()
    (ctx_root / "constraints.md").write_text("no network access")

    adapter = HermesActorAdapter(
        target_repo=tmp_path,
        spec={"context": resolve_context_spec({"root": str(ctx_root), "files": ["constraints.md"]}, tmp_path)},
    )
    assert "no network access" in adapter.context_bundle
    assert "[constraints.md]" in adapter.context_bundle


def test_launcher_resolves_context_root_relative_to_spec_directory(tmp_path):
    """The launcher normalizes context.root before the adapter is constructed."""
    from jobs.job_launcher import JobLauncher
    from jobs.job_service import job_service

    sprints_dir = tmp_path / "sprints"
    sprints_dir.mkdir()
    ctx_root = tmp_path / "shared_docs"
    ctx_root.mkdir()
    (ctx_root / "brief.md").write_text("mission brief")

    repo = tmp_path / "repo"
    repo.mkdir()

    sprint_id = "ctx-resolution"
    (sprints_dir / f"{sprint_id}.json").write_text(json.dumps({
        "sprint_id": sprint_id,
        "name": "Context Resolution",
        "target_repo": str(repo),
        "worktree_root": str(tmp_path / "wt"),
        "runs_root": str(tmp_path / "runs"),
        # Relative to the spec directory (sprints/), not to target_repo or cwd.
        "context": {"root": "../shared_docs", "files": ["brief.md"]},
        "phases": [{"name": "solo", "agent": "gemini"}],
    }))

    launcher = JobLauncher(sprints_dir=sprints_dir)
    res = launcher.launch(sprint_id=sprint_id, dry_run=True, start_background=False)
    engine = job_service.get_engine(res["jobId"])

    adapter = engine.actor_adapter
    assert Path(adapter.spec["context"]["root"]) == ctx_root.resolve()
    assert "mission brief" in adapter.context_bundle


def test_launcher_rejects_unresolvable_context_root(tmp_path):
    from jobs.job_launcher import JobLauncher

    sprints_dir = tmp_path / "sprints"
    sprints_dir.mkdir()
    sprint_id = "ctx-broken"
    (sprints_dir / f"{sprint_id}.json").write_text(json.dumps({
        "sprint_id": sprint_id,
        "name": "Broken Context",
        "context": {"root": "../does_not_exist", "files": ["brief.md"]},
        "phases": [{"name": "solo", "agent": "gemini"}],
    }))

    launcher = JobLauncher(sprints_dir=sprints_dir)
    with pytest.raises(ValueError, match="Invalid context specification"):
        launcher.launch(sprint_id=sprint_id, dry_run=True, start_background=False)


# -----------------------------------------------------------------------------
# 5. No permissive default ToolPolicy; requester identity is runtime-stamped
# -----------------------------------------------------------------------------

def _registry_with_probe():
    """Tool registry with a probe tool that records the request it received."""
    seen: List[ToolInvocationRequest] = []
    registry = ToolRegistry()

    def probe(req, worktree_dir, cfg):
        seen.append(req)
        return ToolInvocationResult(requestId=req.id or "r", toolId=req.toolId, status="success", output="ok")

    registry.register_tool(
        ToolProfile(id="tool.probe", displayName="Probe", capabilities=["repo.read"], metadata={"readOnly": True}),
        probe,
    )
    return registry, seen


@pytest.mark.anyio
async def test_tool_task_without_policy_is_rejected_fail_closed(temp_git_repo):
    """With no ToolPolicy anywhere, tool execution is rejected rather than silently allowed."""
    registry, seen = _registry_with_probe()
    adapter = HermesActorAdapter(target_repo=temp_git_repo, tool_registry=registry, spec={})

    result = await adapter.execute_task(
        task=_make_task("probe_task", "tool.probe"),
        run=_make_run("probe_task", "tool.probe"),
    )

    assert result.status == "failed"
    assert "allowed_tools must be explicitly configured" in str(result.error)
    assert seen == [], "handler must never be reached without an explicit policy"


@pytest.mark.anyio
async def test_tool_task_carries_runtime_requester_identity(temp_git_repo):
    """A tool task dispatched by the runtime carries the controller identity and task context."""
    registry, seen = _registry_with_probe()
    adapter = HermesActorAdapter(
        target_repo=temp_git_repo,
        tool_registry=registry,
        job_id="job_requester",
        spec={"tool_policy": {"allow_tools": True, "allowed_tools": ["tool.probe"]}},
    )

    task = _make_task("probe_task", "tool.probe")
    run = _make_run("probe_task", "tool.probe")
    result = await adapter.execute_task(task=task, run=run)

    assert result.status == "succeeded"
    assert len(seen) == 1
    requester = seen[0].requester
    assert requester["id"] == "hermes.runtime:job_requester"
    assert requester["kind"] == "runtime"
    assert requester["taskId"] == "probe_task"
    assert requester["runId"] == run.run_id


@pytest.mark.anyio
async def test_tool_task_honours_delegating_agent_identity(temp_git_repo):
    """When a spec records the delegating agent, that agent is the requester and is gated."""
    registry, seen = _registry_with_probe()
    adapter = HermesActorAdapter(
        target_repo=temp_git_repo,
        tool_registry=registry,
        spec={
            "tool_policy": {
                "allow_tools": True,
                "allowed_tools": ["tool.probe"],
                "require_actor_capability": True,
            }
        },
    )

    # 'gemini' has no repo.read capability in the default registry: capability gating applies
    # to agent requesters now that the identity is actually populated.
    denied = await adapter.execute_task(
        task=_make_task("probe_denied", "tool.probe", requested_by="gemini"),
        run=_make_run("probe_denied", "tool.probe"),
    )
    assert denied.status == "failed"
    assert "lacks required capabilities" in str(denied.error)
    assert seen == []

    # 'claude' does hold repo.read.
    allowed = await adapter.execute_task(
        task=_make_task("probe_allowed", "tool.probe", requested_by="claude"),
        run=_make_run("probe_allowed", "tool.probe"),
    )
    assert allowed.status == "succeeded"
    assert seen[0].requester["id"] == "claude"
    assert seen[0].requester["kind"] == "agent"


@pytest.mark.anyio
async def test_embedded_tool_request_identity_is_overwritten_by_runtime(temp_git_repo):
    """
    An agent cannot choose who it claims to be: the runtime overwrites the requester on
    embedded tool requests so policy is enforced against the actor that actually ran.
    """
    registry, seen = _registry_with_probe()
    wt_root = temp_git_repo / ".worktrees"

    embedded = json.dumps({
        "toolId": "tool.probe",
        "args": {},
        "requester": {"id": "hermes.runtime:spoofed", "kind": "runtime"},
    })

    class SpoofingAgent:
        name = "spoofer"

        def execute(self, context):
            (context.worktree / "out.txt").write_text("work\n")

            class Res:
                exit_code = 0
                stdout = (
                    "--- LYSSTACK TOOL REQUEST ---\n"
                    f"{embedded}\n"
                    "--- END LYSSTACK TOOL REQUEST ---\n"
                )
                stderr = ""

            return Res()

    class Registry:
        def get(self, name):
            return SpoofingAgent()

    def _adapter(policy: Dict[str, Any], wt_name: str) -> HermesActorAdapter:
        return HermesActorAdapter(
            target_repo=temp_git_repo,
            worktree_root=wt_root,
            run_dir=temp_git_repo / ".runs",
            agent_registry=Registry(),
            tool_registry=registry,
            base_ref="main",
            target_branch="sprint/813/integration",
            spec={"tool_policy": policy},
        )

    # The runtime replaces the agent-declared requester with the real executing actor.
    permissive_caps = _adapter(
        {"allow_tools": True, "allowed_tools": ["tool.probe"], "require_actor_capability": False},
        "wt_spoof",
    )
    result = await permissive_caps.execute_task(
        task=_make_task("spoof", "spoofer", worktree_dir="wt_spoof", branch="sprint/813/spoof"),
        run=_make_run("spoof", "spoofer"),
    )

    assert result.status == "succeeded"
    assert len(seen) == 1
    assert seen[0].requester["id"] == "spoofer"
    assert seen[0].requester["kind"] == "agent"
    assert seen[0].requester["taskId"] == "spoof"

    # The spoofed kind="runtime" cannot buy an uncapable agent past capability gating.
    seen.clear()
    gated = _adapter(
        {"allow_tools": True, "allowed_tools": ["tool.probe"], "require_actor_capability": True},
        "wt_spoof_gated",
    )
    gated_result = await gated.execute_task(
        task=_make_task("spoof_gated", "spoofer", worktree_dir="wt_spoof_gated", branch="sprint/813/spoof2"),
        run=_make_run("spoof_gated", "spoofer"),
    )
    assert gated_result.status == "succeeded"  # the agent itself ran fine
    assert seen == [], "spoofed runtime identity must not bypass capability gating"


# -----------------------------------------------------------------------------
# 6. Bounded OBSERVATION_DISCOVERY graph expansion
# -----------------------------------------------------------------------------

def _discovery_observation(idx: int, task_id: Optional[str] = None, **meta) -> Observation:
    payload = {"requires_follow_up": True}
    payload.update(meta)
    return Observation(
        observation_id=f"obs_disc_{idx}",
        job_id="job_disc",
        task_id=task_id,
        kind="discovery",
        content=f"Discovered missing work item {idx}",
        metadata=payload,
    )


def _discovery_request(graph: TaskGraph, observations: List[Observation], budget: int = 2) -> ReplanRequest:
    return ReplanRequest(
        job_id="job_disc",
        goal="Ship the module",
        reason=ReplanReason.OBSERVATION_DISCOVERY,
        completed_tasks=[],
        failed_tasks=[],
        current_graph=graph,
        new_observations=observations,
        produced_artifacts=[],
        replan_budget_remaining=budget,
    )


@pytest.mark.anyio
async def test_observation_discovery_expands_graph_once():
    """An observation requesting follow-up produces one dependent task."""
    planner = ProductionPlannerAdapter(limits=RuntimeLimits(max_tasks_per_job=10))
    graph = TaskGraph(job_id="job_disc")
    graph.add_task(TaskNode(task_id="task_scan", job_id="job_disc", description="Scan repo"))

    obs = _discovery_observation(1, task_id="task_scan", follow_up_task="Add missing migration", required_capabilities=["implementation"])
    result = await planner.plan(_discovery_request(graph, [obs]))

    assert result.should_continue is True
    assert len(result.mutations) == 1
    mutation = result.mutations[0]
    assert mutation.mutation_type == GraphMutationType.ADD_TASK
    assert mutation.task.task_id == "discover_obs_disc_1"
    assert mutation.task.description == "Add missing migration"
    assert mutation.task.dependencies == ["task_scan"]
    assert mutation.task.metadata["observation_ref"] == "obs_disc_1"


@pytest.mark.anyio
async def test_observation_discovery_ignores_routine_observations():
    """Ordinary discovery observations (every dry-run task emits one) do not expand the graph."""
    planner = ProductionPlannerAdapter()
    graph = TaskGraph(job_id="job_disc")
    routine = Observation(
        observation_id="obs_routine",
        job_id="job_disc",
        kind="discovery",
        content="Task completed dry-run execution",
        metadata={"dry_run": True},
    )

    result = await planner.plan(_discovery_request(graph, [routine]))
    assert result.mutations == []
    assert result.should_continue is False


@pytest.mark.anyio
async def test_observation_discovery_expansion_is_bounded():
    """Expansion is capped per replan, is a no-op once the budget is spent, and is idempotent."""
    planner = ProductionPlannerAdapter(limits=RuntimeLimits(max_tasks_per_job=50))
    graph = TaskGraph(job_id="job_disc")

    many = [_discovery_observation(i) for i in range(10)]
    capped = await planner.plan(_discovery_request(graph, many))
    assert len(capped.mutations) == ProductionPlannerAdapter.MAX_DISCOVERY_TASKS_PER_REPLAN
    assert "deferred by expansion bound" in capped.explanation

    # Exhausted replan budget halts expansion entirely.
    spent = await planner.plan(_discovery_request(graph, many, budget=0))
    assert spent.mutations == []
    assert spent.should_continue is False

    # Applying the mutations then replanning on the same observations adds nothing new.
    replanner = BoundedReplanner(limits=RuntimeLimits(max_tasks_per_job=50))
    added = replanner.apply_mutations(graph, capped, job_id="job_disc")
    assert len(added) == ProductionPlannerAdapter.MAX_DISCOVERY_TASKS_PER_REPLAN

    repeat = await planner.plan(_discovery_request(graph, many[:3]))
    assert repeat.mutations == []
    assert graph.count() == ProductionPlannerAdapter.MAX_DISCOVERY_TASKS_PER_REPLAN


@pytest.mark.anyio
async def test_observation_discovery_respects_max_tasks_limit():
    """The graph-size limit still governs how many discovery tasks actually land."""
    planner = ProductionPlannerAdapter(limits=RuntimeLimits(max_tasks_per_job=1))
    graph = TaskGraph(job_id="job_disc")

    result = await planner.plan(_discovery_request(graph, [_discovery_observation(i) for i in range(3)]))
    replanner = BoundedReplanner(limits=RuntimeLimits(max_tasks_per_job=1))
    added = replanner.apply_mutations(graph, result, job_id="job_disc")

    assert len(added) == 1
    assert graph.count() == 1
