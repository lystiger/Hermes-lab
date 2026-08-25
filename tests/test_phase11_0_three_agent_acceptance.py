import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from runtime.engine import ReactiveJobEngine
from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.scheduler import ReactiveScheduler
from runtime.execution import ExecutionManager, AgentRun, TaskExecutionResult
from runtime.observations import Observation, ObservationRegistry
from runtime.hermes_adapter import HermesActorAdapter
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from capabilities.capabilities import CapabilityRegistry
from runtime.capacity import CapacityRegistry
from runner.agents.registry import AgentRegistry
from runner.agents.antigravity import AntigravityAdapter
from runner.agents.claude import ClaudeAdapter
from runner.agents.codex import CodexAdapter
from runner.backends.base import ExecutionBackend, ExecutionRequest, ExecutionResult
from runner.backends.registry import BackendRegistry


AGY_MARKER = "AGY_DISCOVERY_MARKER_001"
CLAUDE_MARKER = "CLAUDE_HANDOFF_MARKER_11_0"


class DeterministicThreeAgentBackend(ExecutionBackend):
    """
    Deterministic mock backend at the external CLI process boundary.
    Simulates external process execution for real Antigravity, Claude, and Codex adapters,
    inspects captured prompts for required handoff markers, and applies code mutations.
    """
    name = "deterministic_three_agent"

    def __init__(
        self,
        run_dir: Optional[Path] = None,
        sprint_id: Optional[str] = None,
        logger: Any = None,
        fail_codex_first: bool = False,
    ):
        self.run_dir = run_dir
        self.sprint_id = sprint_id
        self.logger = logger
        self.fail_codex_first = fail_codex_first
        self.captured_prompts: Dict[str, str] = {}
        self.executed_agents: List[str] = []
        self.codex_invocations: int = 0

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        agent_name = request.agent_name
        cwd = request.cwd
        cmd = list(request.command)

        # Extract prompt passed to CLI command
        prompt = ""
        if agent_name in ("antigravity", "agy", "gemini"):
            for i, arg in enumerate(cmd):
                if arg == "-p" and i + 1 < len(cmd):
                    prompt = cmd[i + 1]
                    break
        elif agent_name == "claude":
            for i, arg in enumerate(cmd):
                if arg == "-p" and i + 1 < len(cmd):
                    prompt = cmd[i + 1]
                    break
        elif agent_name == "codex":
            prompt = cmd[-1] if cmd else ""

        self.captured_prompts[agent_name] = prompt
        self.executed_agents.append(agent_name)

        if agent_name in ("antigravity", "agy", "gemini"):
            # 1. Antigravity (Builder): writes initial feature code
            app_file = cwd / "app.py"
            app_file.write_text(
                'FEATURE = "agy"\n\n'
                'def add(a, b):\n'
                '    return a + b\n',
                encoding="utf-8",
            )

            # Stream-JSON events containing AGY marker
            event_step = json.dumps({
                "event": "step",
                "message": f"Building initial feature implementation: {AGY_MARKER}",
            })
            event_result = json.dumps({
                "event": "result",
                "status": "SUCCESS",
                "model": "gemini-2.0-flash",
                "usageMetadata": {
                    "promptTokenCount": 1800,
                    "candidatesTokenCount": 350,
                },
            })
            stdout = f"{event_step}\n{event_result}\n"
            runtime_metadata = {
                "usage": {"input_tokens": 1800, "output_tokens": 350},
                "observations": [{
                    "kind": "discovery",
                    "content": f"Antigravity core setup with marker {AGY_MARKER}: built add function.",
                }],
            }
            return ExecutionResult(
                command=request.command,
                returncode=0,
                stdout=stdout,
                stderr="",
                backend=self.name,
                runtime_metadata=runtime_metadata,
            )

        elif agent_name == "claude":
            # 2. Claude (Hardener): hardens code and creates tests
            app_file = cwd / "app.py"
            app_file.write_text(
                'FEATURE = "agy-hardened"\n\n'
                'def add(a, b):\n'
                '    """Hardened addition with type validation."""\n'
                '    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):\n'
                '        raise TypeError("Arguments must be numeric")\n'
                '    return a + b\n',
                encoding="utf-8",
            )

            test_dir = cwd / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_dir / "test_app.py"
            test_file.write_text(
                'from app import add, FEATURE\n'
                'import pytest\n\n'
                'def test_add():\n'
                '    assert add(1, 2) == 3\n'
                '    assert FEATURE == "agy-hardened"\n\n'
                'def test_add_type_error():\n'
                '    with pytest.raises(TypeError):\n'
                '        add("1", 2)\n',
                encoding="utf-8",
            )

            # Claude JSON output containing Claude marker
            claude_data = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "model": "claude-3-5-sonnet-20241022",
                "usage": {
                    "input_tokens": 2500,
                    "output_tokens": 420,
                },
                "content": [{"type": "text", "text": f"Hardened codebase with marker {CLAUDE_MARKER}"}],
            }
            stdout = json.dumps(claude_data)
            runtime_metadata = {
                "usage": {"input_tokens": 2500, "output_tokens": 420},
                "observations": [{
                    "kind": "discovery",
                    "content": f"Claude hardening complete with marker {CLAUDE_MARKER}: added type guards and tests.",
                }],
            }
            return ExecutionResult(
                command=request.command,
                returncode=0,
                stdout=stdout,
                stderr="",
                backend=self.name,
                runtime_metadata=runtime_metadata,
            )

        elif agent_name == "codex":
            # 3. Codex (Verifier): verifies code without mutations
            self.codex_invocations += 1

            if self.fail_codex_first and self.codex_invocations == 1:
                # Simulated verification failure on first attempt
                stdout = "Verification FAILED: detected unhandled edge case in math operations."
                return ExecutionResult(
                    command=request.command,
                    returncode=1,
                    stdout=stdout,
                    stderr="Verification failure on attempt 1",
                    backend=self.name,
                )
            else:
                # Verification success (no mutations to files)
                stdout = (
                    f"Verification PASSED: syntax valid, tests passed, no regressions detected. "
                    f"Verified {AGY_MARKER} and {CLAUDE_MARKER}."
                )
                return ExecutionResult(
                    command=request.command,
                    returncode=0,
                    stdout=stdout,
                    stderr="",
                    backend=self.name,
                )

        raise ValueError(f"Unknown agent: {agent_name}")


def _setup_disposable_git_repo(repo_dir: Path) -> Path:
    """Initializes a real Git repository with initial commit on main."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hermes Test"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@hermes.local"], cwd=repo_dir, check=True, capture_output=True)

    readme = repo_dir / "README.md"
    readme.write_text("# Test Disposable Repo\nPhase 11 Three-Agent Acceptance\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial repository commit"], cwd=repo_dir, check=True, capture_output=True)
    return repo_dir


@pytest.mark.anyio
async def test_phase11_0_three_agent_pass_path(tmp_path: Path):
    """
    Phase 11.0 Acceptance Gate - PASS PATH:
    Proves the complete three-agent organization:
      Antigravity (builder) -> Claude (hardener) -> Codex (verifier)
    executes end-to-end through real adapters, scheduler, execution manager,
    task graph, continuity/observation plumbing, Git integration worktree, and event store.
    """
    repo_dir = _setup_disposable_git_repo(tmp_path / "repo")
    worktree_root = tmp_path / "worktrees"
    run_dir = tmp_path / "runs"

    # 1. Event Store & Bridge
    event_store = InMemoryRuntimeEventStore()
    event_bridge = RuntimeEventBridge(event_store=event_store)

    # 2. Registries
    obs_reg = ObservationRegistry()
    cap_reg = CapabilityRegistry()
    capacity_reg = CapacityRegistry()

    cap_reg.register_actor({"id": "antigravity", "name": "Antigravity", "capabilities": ["python", "builder"]})
    cap_reg.register_actor({"id": "claude", "name": "Claude", "capabilities": ["python", "hardener", "testing"]})
    cap_reg.register_actor({"id": "codex", "name": "Codex", "capabilities": ["python", "verifier", "review"]})

    capacity_reg.register_actor_provider("antigravity", "google")
    capacity_reg.register_actor_provider("claude", "anthropic")
    capacity_reg.register_actor_provider("codex", "openai")

    # 3. Real Agent Adapters with Mock Backend
    backend_instance = DeterministicThreeAgentBackend(run_dir=run_dir, sprint_id="job_three_agent_pass")
    backend_reg = BackendRegistry({DeterministicThreeAgentBackend.name: lambda **kw: backend_instance})

    agent_reg = AgentRegistry({
        AntigravityAdapter.name: AntigravityAdapter,
        ClaudeAdapter.name: ClaudeAdapter,
        CodexAdapter.name: CodexAdapter,
    })

    # 4. Real HermesActorAdapter & ExecutionManager
    adapter = HermesActorAdapter(
        target_repo=repo_dir,
        worktree_root=worktree_root,
        run_dir=run_dir,
        dry_run=False,
        agent_registry=agent_reg,
        backend_registry=backend_reg,
        observation_registry=obs_reg,
        job_id="job_three_agent_pass",
    )

    exec_manager = ExecutionManager()
    exec_manager.register_adapter("antigravity", adapter)
    exec_manager.register_adapter("claude", adapter)
    exec_manager.register_adapter("codex", adapter)

    # 5. Real ReactiveScheduler
    scheduler = ReactiveScheduler(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        event_bridge=event_bridge,
    )

    # 6. Build Task Graph: T1(Antigravity) -> T2(Claude) -> T3(Codex)
    graph = TaskGraph()
    t1 = TaskNode(
        task_id="T1",
        job_id="job_three_agent_pass",
        description="Build initial arithmetic module",
        assigned_actor="antigravity",
        metadata={"role": "builder", "execution_backend": DeterministicThreeAgentBackend.name},
    )
    t2 = TaskNode(
        task_id="T2",
        job_id="job_three_agent_pass",
        description="Harden arithmetic module with type checks and tests",
        assigned_actor="claude",
        dependencies=["T1"],
        metadata={"role": "hardener", "execution_backend": DeterministicThreeAgentBackend.name},
    )
    t3 = TaskNode(
        task_id="T3",
        job_id="job_three_agent_pass",
        description="Verify arithmetic module test coverage and regression freedom",
        assigned_actor="codex",
        dependencies=["T2"],
        metadata={"role": "verifier", "execution_backend": DeterministicThreeAgentBackend.name},
    )

    # 7. Real ReactiveJobEngine
    engine = ReactiveJobEngine(
        job_id="job_three_agent_pass",
        goal="Deliver hardened and verified arithmetic module",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        execution_manager=exec_manager,
        event_bridge=event_bridge,
        observation_registry=obs_reg,
    )

    # Execute workflow to completion
    await engine.initialize_and_plan(initial_tasks=[t1, t2, t3])
    await engine.run_until_complete(max_steps=20)

    # =========================================================================
    # ASSERTIONS
    # =========================================================================

    # A. Terminal State
    assert engine.state == JobState.COMPLETED
    assert engine.is_terminal is True
    assert t1.status == TaskStatus.SUCCEEDED
    assert t2.status == TaskStatus.SUCCEEDED
    assert t3.status == TaskStatus.SUCCEEDED

    # B. Real Actor IDs Executed
    assert "antigravity" in backend_instance.executed_agents
    assert "claude" in backend_instance.executed_agents
    assert "codex" in backend_instance.executed_agents

    # C. Handoff & Continuity Assertions:
    # 1. Antigravity emits AGY_MARKER in discovery observation
    agy_obs = [o for o in obs_reg.list_for_task("T1") if AGY_MARKER in o.content]
    assert len(agy_obs) >= 1

    # 2. Claude receives AGY_MARKER in effective prompt via continuity plumbing
    claude_prompt = backend_instance.captured_prompts.get("claude", "")
    assert AGY_MARKER in claude_prompt, f"Expected {AGY_MARKER} in Claude prompt, got:\n{claude_prompt}"

    # 3. Claude emits CLAUDE_MARKER in discovery observation
    claude_obs = [o for o in obs_reg.list_for_task("T2") if CLAUDE_MARKER in o.content]
    assert len(claude_obs) >= 1

    # 4. Codex receives CLAUDE_MARKER in effective prompt via continuity plumbing
    codex_prompt = backend_instance.captured_prompts.get("codex", "")
    assert CLAUDE_MARKER in codex_prompt, f"Expected {CLAUDE_MARKER} in Codex prompt, got:\n{codex_prompt}"

    # D. Real Git / Worktree Assertions
    integration_wt = worktree_root / "integration"
    assert integration_wt.exists()

    app_py = integration_wt / "app.py"
    assert app_py.exists()
    app_content = app_py.read_text(encoding="utf-8")
    assert 'FEATURE = "agy-hardened"' in app_content
    assert "Hardened addition with type validation." in app_content

    test_py = integration_wt / "tests" / "test_app.py"
    assert test_py.exists()
    test_content = test_py.read_text(encoding="utf-8")
    assert "test_add_type_error" in test_content

    # E. Canonical Event Ledger Assertions
    events = await event_store.list_events("job_three_agent_pass")
    event_kinds = [e.event_type for e in events]

    assert "job.created" in event_kinds
    assert "task.created" in event_kinds
    assert "task.started" in event_kinds
    assert "agent.started" in event_kinds
    assert "agent.finished" in event_kinds
    assert "observation.created" in event_kinds
    assert "task.completed" in event_kinds
    assert "verification.passed" in event_kinds
    assert "job.completed" in event_kinds

    # Assert agent runs in ledger reflect real three-agent identities
    agent_started_events = [e for e in events if e.event_type == "agent.started"]
    actors_in_ledger = [e.actor_id or e.payload.get("actorId") or e.payload.get("actor_id") for e in agent_started_events]
    assert "antigravity" in actors_in_ledger
    assert "claude" in actors_in_ledger
    assert "codex" in actors_in_ledger

    # F. Deterministic State Reconstruction
    projector = RuntimeStateProjector()
    reconstructed = projector.project(events)

    assert reconstructed.job.state == JobState.COMPLETED
    assert reconstructed.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T2").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T3").status == TaskStatus.SUCCEEDED

    reconstructed_actor_ids = [r.actor_id for r in reconstructed.runs]
    assert "antigravity" in reconstructed_actor_ids
    assert "claude" in reconstructed_actor_ids
    assert "codex" in reconstructed_actor_ids


@pytest.mark.anyio
async def test_phase11_0_three_agent_fail_and_repair_path(tmp_path: Path):
    """
    Phase 11.0 Acceptance Gate - FAIL & REPAIR PATH:
    Proves that when Codex verifier detects a defect on its first execution,
    the failure telemetry is captured, preserved across retries, and upon resolution
    the workflow cleanly completes with durable event history.
    """
    repo_dir = _setup_disposable_git_repo(tmp_path / "repo_repair")
    worktree_root = tmp_path / "worktrees"
    run_dir = tmp_path / "runs"

    event_store = InMemoryRuntimeEventStore()
    event_bridge = RuntimeEventBridge(event_store=event_store)
    obs_reg = ObservationRegistry()
    cap_reg = CapabilityRegistry()
    capacity_reg = CapacityRegistry()

    cap_reg.register_actor({"id": "antigravity", "name": "Antigravity", "capabilities": ["python", "builder"]})
    cap_reg.register_actor({"id": "claude", "name": "Claude", "capabilities": ["python", "hardener"]})
    cap_reg.register_actor({"id": "codex", "name": "Codex", "capabilities": ["python", "verifier"]})

    capacity_reg.register_actor_provider("antigravity", "google")
    capacity_reg.register_actor_provider("claude", "anthropic")
    capacity_reg.register_actor_provider("codex", "openai")

    # Mock backend configured to fail Codex on invocation 1 and succeed on invocation 2
    backend_instance = DeterministicThreeAgentBackend(
        run_dir=run_dir,
        sprint_id="job_three_agent_repair",
        fail_codex_first=True,
    )
    backend_reg = BackendRegistry({DeterministicThreeAgentBackend.name: lambda **kw: backend_instance})

    agent_reg = AgentRegistry({
        AntigravityAdapter.name: AntigravityAdapter,
        ClaudeAdapter.name: ClaudeAdapter,
        CodexAdapter.name: CodexAdapter,
    })

    adapter = HermesActorAdapter(
        target_repo=repo_dir,
        worktree_root=worktree_root,
        run_dir=run_dir,
        dry_run=False,
        agent_registry=agent_reg,
        backend_registry=backend_reg,
        observation_registry=obs_reg,
        job_id="job_three_agent_repair",
    )

    exec_manager = ExecutionManager()
    exec_manager.register_adapter("antigravity", adapter)
    exec_manager.register_adapter("claude", adapter)
    exec_manager.register_adapter("codex", adapter)

    scheduler = ReactiveScheduler(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        event_bridge=event_bridge,
    )

    graph = TaskGraph()
    t1 = TaskNode(
        task_id="T1",
        job_id="job_three_agent_repair",
        description="Build initial module",
        assigned_actor="antigravity",
        metadata={"role": "builder", "execution_backend": DeterministicThreeAgentBackend.name},
    )
    t2 = TaskNode(
        task_id="T2",
        job_id="job_three_agent_repair",
        description="Harden module",
        assigned_actor="claude",
        dependencies=["T1"],
        metadata={"role": "hardener", "execution_backend": DeterministicThreeAgentBackend.name},
    )
    # T3 allows 2 attempts so it can recover from the first failed verification
    t3 = TaskNode(
        task_id="T3",
        job_id="job_three_agent_repair",
        description="Verify module",
        assigned_actor="codex",
        dependencies=["T2"],
        max_attempts=2,
        metadata={"role": "verifier", "execution_backend": DeterministicThreeAgentBackend.name},
    )

    engine = ReactiveJobEngine(
        job_id="job_three_agent_repair",
        goal="Repair path three-agent acceptance",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        execution_manager=exec_manager,
        event_bridge=event_bridge,
        observation_registry=obs_reg,
    )

    await engine.initialize_and_plan(initial_tasks=[t1, t2, t3])
    await engine.run_until_complete(max_steps=25)

    assert engine.state == JobState.COMPLETED
    assert t3.status == TaskStatus.SUCCEEDED
    assert backend_instance.codex_invocations == 2

    # Verify event ledger recorded failure followed by successful completion
    events = await event_store.list_events("job_three_agent_repair")
    t3_started_events = [
        e for e in events
        if e.event_type == "agent.started" and (e.task_id == "T3" or (e.payload or {}).get("taskId") == "T3")
    ]
    assert len(t3_started_events) == 2

    t3_failed_events = [
        e for e in events
        if e.event_type == "agent.failed" and (e.task_id == "T3" or (e.payload or {}).get("taskId") == "T3")
    ]
    assert len(t3_failed_events) >= 1

    t3_finished_events = [
        e for e in events
        if e.event_type == "agent.finished" and (e.task_id == "T3" or (e.payload or {}).get("taskId") == "T3")
    ]
    assert len(t3_finished_events) >= 1

    projector = RuntimeStateProjector()
    reconstructed = projector.project(events)
    assert reconstructed.job.state == JobState.COMPLETED
    assert reconstructed.graph.get_task("T3").status == TaskStatus.SUCCEEDED


@pytest.mark.live_agents
@pytest.mark.anyio
async def test_phase11_0_live_agents_acceptance(tmp_path: Path):
    """
    Opt-in live agent acceptance test invoking locally installed CLIs
    (agy/antigravity, claude, codex) against a tiny disposable repository.
    Skipped by default in CI unless HERMES_RUN_LIVE_AGENTS=1 is set.
    """
    if os.environ.get("HERMES_RUN_LIVE_AGENTS") != "1":
        pytest.skip("Live agent tests are opt-in. Set HERMES_RUN_LIVE_AGENTS=1 to execute with real local CLIs.")

    agy_bin = shutil.which("agy") or shutil.which("antigravity")
    claude_bin = shutil.which("claude")
    codex_bin = shutil.which("codex")

    missing = []
    if not agy_bin:
        missing.append("antigravity/agy")
    if not claude_bin:
        missing.append("claude")
    if not codex_bin:
        missing.append("codex")

    if missing:
        pytest.skip(f"Live agent execution requires installed CLIs: missing {', '.join(missing)}")

    repo_dir = _setup_disposable_git_repo(tmp_path / "live_repo")
    worktree_root = tmp_path / "live_worktrees"
    run_dir = tmp_path / "live_runs"

    event_store = InMemoryRuntimeEventStore()
    event_bridge = RuntimeEventBridge(event_store=event_store)
    obs_reg = ObservationRegistry()
    cap_reg = CapabilityRegistry()
    capacity_reg = CapacityRegistry()

    cap_reg.register_actor({"id": "antigravity", "name": "Antigravity", "capabilities": ["python", "builder"]})
    cap_reg.register_actor({"id": "claude", "name": "Claude", "capabilities": ["python", "hardener"]})
    cap_reg.register_actor({"id": "codex", "name": "Codex", "capabilities": ["python", "verifier"]})

    capacity_reg.register_actor_provider("antigravity", "google")
    capacity_reg.register_actor_provider("claude", "anthropic")
    capacity_reg.register_actor_provider("codex", "openai")

    from runner.backends.subprocess_backend import SubprocessBackend
    backend_reg = BackendRegistry({SubprocessBackend.name: SubprocessBackend})
    agent_reg = AgentRegistry({
        AntigravityAdapter.name: AntigravityAdapter,
        ClaudeAdapter.name: ClaudeAdapter,
        CodexAdapter.name: CodexAdapter,
    })

    adapter = HermesActorAdapter(
        target_repo=repo_dir,
        worktree_root=worktree_root,
        run_dir=run_dir,
        dry_run=False,
        agent_registry=agent_reg,
        backend_registry=backend_reg,
        observation_registry=obs_reg,
        job_id="job_live_agents",
    )

    exec_manager = ExecutionManager()
    exec_manager.register_adapter("antigravity", adapter)
    exec_manager.register_adapter("claude", adapter)
    exec_manager.register_adapter("codex", adapter)

    scheduler = ReactiveScheduler(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        event_bridge=event_bridge,
    )

    graph = TaskGraph()
    t1 = TaskNode(
        task_id="T1",
        job_id="job_live_agents",
        description="Write a Python add function in app.py",
        assigned_actor="antigravity",
        metadata={"role": "builder", "timeout_seconds": 60},
    )
    t2 = TaskNode(
        task_id="T2",
        job_id="job_live_agents",
        description="Add docstring and test for add function in tests/test_app.py",
        assigned_actor="claude",
        dependencies=["T1"],
        metadata={"role": "hardener", "timeout_seconds": 60},
    )
    t3 = TaskNode(
        task_id="T3",
        job_id="job_live_agents",
        description="Review app.py and tests/test_app.py for correctness",
        assigned_actor="codex",
        dependencies=["T2"],
        metadata={"role": "verifier", "timeout_seconds": 60},
    )

    engine = ReactiveJobEngine(
        job_id="job_live_agents",
        goal="Live agent validation",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        execution_manager=exec_manager,
        event_bridge=event_bridge,
        observation_registry=obs_reg,
    )

    await engine.initialize_and_plan(initial_tasks=[t1, t2, t3])
    await engine.run_until_complete(max_steps=20)

    assert engine.state == JobState.COMPLETED
