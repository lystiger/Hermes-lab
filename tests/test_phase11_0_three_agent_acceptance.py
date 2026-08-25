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
from runtime.replanning import (
    PlannerAdapter,
    ReplanRequest,
    ReplanResult,
    GraphMutation,
    GraphMutationType,
    CallablePlannerAdapter,
)
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
        self.repair_executed: bool = False

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

        self.captured_prompts[f"{agent_name}_{len(self.executed_agents)}"] = prompt
        self.captured_prompts[agent_name] = prompt
        self.executed_agents.append(agent_name)

        if agent_name in ("antigravity", "agy", "gemini"):
            # 1. Antigravity (Builder): writes initial feature code
            app_file = cwd / "app.py"
            app_file.write_text(
                'FEATURE = "agy"\n\n'
                'def add(a, b):\n'
                '    return a + b\n\n'
                'def divide(a, b):\n'
                '    # Buggy initial division without zero guard\n'
                '    return a / b\n',
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
                    "content": f"Antigravity core setup with marker {AGY_MARKER}: built add and divide primitives.",
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
            # Check if this is a repair execution or initial hardening
            is_repair = "repair" in prompt.lower() or "fix" in prompt.lower() or "zerodivisionerror" in prompt.lower()

            app_file = cwd / "app.py"
            test_dir = cwd / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_dir / "test_app.py"

            if is_repair:
                self.repair_executed = True
                # 4. Claude (Repair): fixes the divide-by-zero bug found by Codex
                app_file.write_text(
                    'FEATURE = "agy-hardened-repaired"\n\n'
                    'def add(a, b):\n'
                    '    """Hardened addition with type validation."""\n'
                    '    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):\n'
                    '        raise TypeError("Arguments must be numeric")\n'
                    '    return a + b\n\n'
                    'def divide(a, b):\n'
                    '    """Repaired division with zero-division validation."""\n'
                    '    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):\n'
                    '        raise TypeError("Arguments must be numeric")\n'
                    '    if b == 0:\n'
                    '        raise ValueError("Division by zero is not allowed")\n'
                    '    return a / b\n',
                    encoding="utf-8",
                )
                test_file.write_text(
                    'from app import add, divide, FEATURE\n'
                    'import pytest\n\n'
                    'def test_add():\n'
                    '    assert add(1, 2) == 3\n\n'
                    'def test_divide():\n'
                    '    assert divide(6, 2) == 3.0\n\n'
                    'def test_divide_zero():\n'
                    '    with pytest.raises(ValueError, match="Division by zero"):\n'
                    '        divide(10, 0)\n',
                    encoding="utf-8",
                )
                content_text = "Repaired division zero-check and added regression unit tests"
                obs_content = "Claude repair complete: handled zero division in divide()."
            else:
                # 2. Claude (Hardener): hardens add function
                app_file.write_text(
                    'FEATURE = "agy-hardened"\n\n'
                    'def add(a, b):\n'
                    '    """Hardened addition with type validation."""\n'
                    '    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):\n'
                    '        raise TypeError("Arguments must be numeric")\n'
                    '    return a + b\n\n'
                    'def divide(a, b):\n'
                    '    return a / b\n',
                    encoding="utf-8",
                )
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
                content_text = f"Hardened codebase with marker {CLAUDE_MARKER}"
                obs_content = f"Claude hardening complete with marker {CLAUDE_MARKER}: added type guards."

            claude_data = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "model": "claude-3-5-sonnet-20241022",
                "usage": {
                    "input_tokens": 2500,
                    "output_tokens": 420,
                },
                "content": [{"type": "text", "text": content_text}],
            }
            stdout = json.dumps(claude_data)
            runtime_metadata = {
                "usage": {"input_tokens": 2500, "output_tokens": 420},
                "observations": [{
                    "kind": "discovery",
                    "content": obs_content,
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
            # 3. Codex (Verifier): parses code and emits structured JSON verification contract
            self.codex_invocations += 1

            if self.fail_codex_first and self.codex_invocations == 1:
                # Structured JSON verification failure
                verdict_payload = {
                    "verdict": "failed",
                    "summary": "API contract regression: divide function raises unhandled ZeroDivisionError",
                    "repairable": True,
                    "findings": [
                        "ZeroDivisionError raised when calling divide(a, 0)",
                        "Missing unit test for division edge cases in tests/test_app.py",
                    ],
                }
                stdout = json.dumps(verdict_payload, indent=2)
                return ExecutionResult(
                    command=request.command,
                    returncode=0,  # Process succeeded, semantic verdict is failed
                    stdout=stdout,
                    stderr="",
                    backend=self.name,
                )
            else:
                # Structured JSON verification pass
                verdict_payload = {
                    "verdict": "passed",
                    "summary": f"All arithmetic modules verified without regressions against {AGY_MARKER} and {CLAUDE_MARKER}",
                    "repairable": False,
                    "findings": [],
                }
                stdout = json.dumps(verdict_payload, indent=2)
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


def test_codex_adapter_structured_contract_parsing():
    """
    Tests that CodexAdapter parses various structured verifier contracts
    and fails closed on missing, ambiguous, or unparseable verdicts:
    - Pure JSON pass & fail
    - Markdown code fence JSON pass & fail
    - Structured text blocks (VERDICT: PASS / FAIL)
    - Missing verdict: {"summary": "looks fine"} -> INVALID (None / SprintRunnerError)
    - Unstructured text: "I found a critical regression" -> INVALID (None / SprintRunnerError)
    - Ambiguous flags: {"success": true} -> INVALID (None / SprintRunnerError)
    """
    from runner.agents.errors import SprintRunnerError
    from runner.agents.base import AgentContext
    from types import SimpleNamespace

    adapter = CodexAdapter()

    # 1. Pure JSON - Failure
    raw_json_fail = json.dumps({
        "verdict": "failed",
        "summary": "Regression detected in auth token validation",
        "repairable": True,
        "findings": ["Expired tokens accepted", "Signature not checked"],
    })
    res_fail = adapter.parse_verification_output(raw_json_fail)
    assert res_fail is not None
    assert res_fail["verdict"] == "failed"
    assert res_fail["summary"] == "Regression detected in auth token validation"
    assert res_fail["repairable"] is True
    assert len(res_fail["findings"]) == 2
    assert res_fail["trigger_replan"] is True
    assert len(res_fail["observations"]) == 1
    assert res_fail["observations"][0]["kind"] == "verification_failure"
    assert res_fail["observations"][0]["metadata"]["requires_follow_up"] is True

    # 2. Markdown fenced JSON - Pass
    raw_fenced_pass = (
        "Here is the verification result:\n"
        "```json\n"
        "{\n"
        '  "verdict": "passed",\n'
        '  "summary": "All 42 tests passed, no mutations",\n'
        '  "repairable": false,\n'
        '  "findings": []\n'
        "}\n"
        "```\n"
    )
    res_pass = adapter.parse_verification_output(raw_fenced_pass)
    assert res_pass is not None
    assert res_pass["verdict"] == "passed"
    assert res_pass["repairable"] is False
    assert res_pass["trigger_replan"] is False
    assert res_pass["observations"][0]["kind"] == "verification_success"

    # 3. Structured Text Blocks - Pass & Fail
    text_fail = (
        "VERDICT: FAIL\n"
        "SUMMARY: Null pointer in parser module\n"
        "REPAIRABLE: TRUE\n"
        "FINDINGS:\n"
        "- Unchecked None passed to split()\n"
        "- Missing fallback handler\n"
    )
    res_text_fail = adapter.parse_verification_output(text_fail)
    assert res_text_fail is not None
    assert res_text_fail["verdict"] == "failed"
    assert res_text_fail["summary"] == "Null pointer in parser module"
    assert res_text_fail["repairable"] is True
    assert len(res_text_fail["findings"]) == 2
    assert res_text_fail["trigger_replan"] is True

    text_pass = (
        "VERDICT: PASS\n"
        "SUMMARY: Integration suite clean\n"
        "REPAIRABLE: FALSE\n"
        "FINDINGS:\n"
    )
    res_text_pass = adapter.parse_verification_output(text_pass)
    assert res_text_pass is not None
    assert res_text_pass["verdict"] == "passed"
    assert res_text_pass["trigger_replan"] is False

    # 4. Regression Case: {"summary": "looks fine"} -> INVALID, NOT PASS
    missing_verdict_json = json.dumps({"summary": "looks fine"})
    assert adapter.parse_verification_output(missing_verdict_json) is None

    # 5. Regression Case: "I found a critical regression" without VERDICT: header -> INVALID, NOT PASS
    unstructured_text = "I found a critical regression in the payment processor"
    assert adapter.parse_verification_output(unstructured_text) is None

    # 6. Regression Case: {"success": true} without explicit verdict -> INVALID, NOT PASS
    generic_success_json = json.dumps({"success": True, "output": "Done"})
    assert adapter.parse_verification_output(generic_success_json) is None

    # 7. Validation in verifier role context raises SprintRunnerError on invalid contracts
    dummy_ctx = SimpleNamespace(phase={"role": "verifier", "name": "verification_step"})
    
    mock_res_missing = ExecutionResult(command=["codex"], returncode=0, stdout=missing_verdict_json, stderr="", backend="test")
    with pytest.raises(SprintRunnerError) as exc_info:
        adapter.validate_result(mock_res_missing, dummy_ctx)
    assert exc_info.value.code == "FAILED_CODEX_INVALID_VERDICT"

    mock_res_unstructured = ExecutionResult(command=["codex"], returncode=0, stdout=unstructured_text, stderr="", backend="test")
    with pytest.raises(SprintRunnerError) as exc_info:
        adapter.validate_result(mock_res_unstructured, dummy_ctx)
    assert exc_info.value.code == "FAILED_CODEX_INVALID_VERDICT"

    mock_res_valid_fail = ExecutionResult(command=["codex"], returncode=0, stdout=raw_json_fail, stderr="", backend="test")
    adapter.validate_result(mock_res_valid_fail, dummy_ctx)
    assert mock_res_valid_fail.runtime_metadata["verdict"] == "failed"
    assert mock_res_valid_fail.runtime_metadata["trigger_replan"] is True

    mock_res_valid_pass = ExecutionResult(command=["codex"], returncode=0, stdout=raw_fenced_pass, stderr="", backend="test")
    adapter.validate_result(mock_res_valid_pass, dummy_ctx)
    assert mock_res_valid_pass.runtime_metadata["verdict"] == "passed"
    assert mock_res_valid_pass.runtime_metadata["trigger_replan"] is False


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

    event_store = InMemoryRuntimeEventStore()
    event_bridge = RuntimeEventBridge(event_store=event_store)
    obs_reg = ObservationRegistry()
    cap_reg = CapabilityRegistry()
    capacity_reg = CapacityRegistry()

    cap_reg.register_actor({"id": "antigravity", "name": "Antigravity", "capabilities": ["python", "builder"]})
    cap_reg.register_actor({"id": "claude", "name": "Claude", "capabilities": ["python", "hardener", "testing"]})
    cap_reg.register_actor({"id": "codex", "name": "Codex", "capabilities": ["python", "verifier", "review"]})

    capacity_reg.register_actor_provider("antigravity", "google")
    capacity_reg.register_actor_provider("claude", "anthropic")
    capacity_reg.register_actor_provider("codex", "openai")

    backend_instance = DeterministicThreeAgentBackend(run_dir=run_dir, sprint_id="job_three_agent_pass")
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
        job_id="job_three_agent_pass",
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

    engine = ReactiveJobEngine(
        job_id="job_three_agent_pass",
        goal="Deliver hardened and verified arithmetic module",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        execution_manager=exec_manager,
        event_bridge=event_bridge,
        observation_registry=obs_reg,
    )

    await engine.initialize_and_plan(initial_tasks=[t1, t2, t3])
    await engine.run_until_complete(max_steps=20)

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

    # C. Handoff & Continuity Assertions
    agy_obs = [o for o in obs_reg.list_for_task("T1") if AGY_MARKER in o.content]
    assert len(agy_obs) >= 1

    claude_prompt = backend_instance.captured_prompts.get("claude", "")
    assert AGY_MARKER in claude_prompt

    claude_obs = [o for o in obs_reg.list_for_task("T2") if CLAUDE_MARKER in o.content]
    assert len(claude_obs) >= 1

    codex_prompt = backend_instance.captured_prompts.get("codex", "")
    assert CLAUDE_MARKER in codex_prompt
    assert "--- HERMES VERIFICATION CONTRACT ---" in codex_prompt
    assert '"verdict": "passed" | "failed"' in codex_prompt

    # Structured verification success observation recorded
    codex_success_obs = [o for o in obs_reg.list_for_task("T3") if o.kind == "verification_success"]
    assert len(codex_success_obs) >= 1

    # D. Real Git / Worktree Assertions
    integration_wt = worktree_root / "integration"
    assert integration_wt.exists()
    app_py = integration_wt / "app.py"
    assert app_py.exists()
    app_content = app_py.read_text(encoding="utf-8")
    assert 'FEATURE = "agy-hardened"' in app_content

    # E. Canonical Event Ledger Assertions
    events = await event_store.list_events("job_three_agent_pass")
    event_kinds = [e.event_type for e in events]
    assert "job.created" in event_kinds
    assert "task.created" in event_kinds
    assert "agent.started" in event_kinds
    assert "agent.finished" in event_kinds
    assert "observation.created" in event_kinds
    assert "task.completed" in event_kinds
    assert "verification.passed" in event_kinds
    assert "job.completed" in event_kinds

    # F. Deterministic State Reconstruction
    projector = RuntimeStateProjector()
    reconstructed = projector.project(events)
    assert reconstructed.job.state == JobState.COMPLETED
    assert reconstructed.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T2").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T3").status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_phase11_0_three_agent_fail_and_repair_workflow_e2e(tmp_path: Path):
    """
    Phase 11.0.1 True Multi-Step Repair Workflow:
    Antigravity builds -> Claude hardens -> Codex finds defect via structured JSON contract
    -> Claude/Agy repairs defect -> Codex rechecks & passes -> COMPLETED.
    """
    repo_dir = _setup_disposable_git_repo(tmp_path / "repo_repair_e2e")
    worktree_root = tmp_path / "worktrees"
    run_dir = tmp_path / "runs"

    event_store = InMemoryRuntimeEventStore()
    event_bridge = RuntimeEventBridge(event_store=event_store)
    obs_reg = ObservationRegistry()
    cap_reg = CapabilityRegistry()
    capacity_reg = CapacityRegistry()

    cap_reg.register_actor({"id": "antigravity", "name": "Antigravity", "capabilities": ["python", "builder"]})
    cap_reg.register_actor({"id": "claude", "name": "Claude", "capabilities": ["python", "hardener", "repair"]})
    cap_reg.register_actor({"id": "codex", "name": "Codex", "capabilities": ["python", "verifier"]})

    capacity_reg.register_actor_provider("antigravity", "google")
    capacity_reg.register_actor_provider("claude", "anthropic")
    capacity_reg.register_actor_provider("codex", "openai")

    backend_instance = DeterministicThreeAgentBackend(
        run_dir=run_dir,
        sprint_id="job_repair_workflow",
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
        job_id="job_repair_workflow",
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
        job_id="job_repair_workflow",
        description="Build initial arithmetic module with add and divide",
        assigned_actor="antigravity",
        metadata={"role": "builder", "execution_backend": DeterministicThreeAgentBackend.name},
    )
    t2 = TaskNode(
        task_id="T2",
        job_id="job_repair_workflow",
        description="Harden arithmetic module with type checks",
        assigned_actor="claude",
        dependencies=["T1"],
        metadata={"role": "hardener", "execution_backend": DeterministicThreeAgentBackend.name},
    )
    t3 = TaskNode(
        task_id="T3",
        job_id="job_repair_workflow",
        description="Verify arithmetic module contract and edge cases",
        assigned_actor="codex",
        dependencies=["T2"],
        metadata={"role": "verifier", "execution_backend": DeterministicThreeAgentBackend.name},
    )

    # Dynamic replanner to generate repair task (T4: Claude) and re-verify task (T5: Codex)
    async def dynamic_repair_planner(request: ReplanRequest) -> ReplanResult:
        if str(request.reason.value if hasattr(request.reason, "value") else request.reason) == "initial_plan":
            return ReplanResult(mutations=[], explanation="Initial plan tasks preserved")

        mutations = []
        failure_obs = [o for o in request.new_observations if o.kind == "verification_failure"]
        error_detail = failure_obs[0].content if failure_obs else "Fix verification regression"

        # T4: Repair task executed by Claude (depends on T2)
        repair_task = TaskNode(
            task_id="T4_repair",
            job_id=request.job_id,
            description=f"Repair API regression identified by Codex: {error_detail}",
            assigned_actor="claude",
            dependencies=["T2"],
            metadata={"role": "hardener", "execution_backend": DeterministicThreeAgentBackend.name},
        )
        mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=repair_task, reason="Repair verification defect"))

        # T5: Re-verification task executed by Codex (depends on T4_repair)
        reverify_task = TaskNode(
            task_id="T5_reverify",
            job_id=request.job_id,
            description="Re-verify arithmetic module after repair",
            assigned_actor="codex",
            dependencies=["T4_repair"],
            metadata={"role": "verifier", "execution_backend": DeterministicThreeAgentBackend.name},
        )
        mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=reverify_task, reason="Re-verify repaired module"))

        # Mark the failed verification task T3 as superseded by re-verification task T5_reverify
        mutations.append(GraphMutation(mutation_type=GraphMutationType.SUPERSEDE_TASK, task_id="T3", depends_on_task_id="T5_reverify", reason="Superseded by repair and re-verification"))

        return ReplanResult(mutations=mutations, explanation="Planned repair task T4 and re-verification T5")

    engine = ReactiveJobEngine(
        job_id="job_repair_workflow",
        goal="Deliver robust arithmetic module through three-agent verification & repair",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        execution_manager=exec_manager,
        event_bridge=event_bridge,
        observation_registry=obs_reg,
        planner=CallablePlannerAdapter(dynamic_repair_planner),
    )

    await engine.initialize_and_plan(initial_tasks=[t1, t2, t3])
    await engine.run_until_complete(max_steps=30)

    # A. Workflow reached COMPLETED
    assert engine.state == JobState.COMPLETED
    assert engine.is_terminal is True

    # B. Task Graph Statuses:
    # T1 succeeded, T2 succeeded, T3 superseded, T4_repair succeeded, T5_reverify succeeded
    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert engine.graph.get_task("T2").status == TaskStatus.SUCCEEDED
    assert engine.graph.get_task("T3").status == TaskStatus.SUPERSEDED
    assert engine.graph.get_task("T4_repair").status == TaskStatus.SUCCEEDED
    assert engine.graph.get_task("T5_reverify").status == TaskStatus.SUCCEEDED

    # C. Verification Observation Flow:
    # 1. T3 produced structured verification_failure observation with findings
    fail_obs = [o for o in obs_reg.list_for_task("T3") if o.kind == "verification_failure"]
    assert len(fail_obs) >= 1
    assert "ZeroDivisionError" in fail_obs[0].content

    # 2. T4 (Claude repair) prompt contained Codex's defect observation via continuity plumbing
    repair_prompt = backend_instance.captured_prompts.get("claude", "")
    assert "ZeroDivisionError" in repair_prompt or "divide" in repair_prompt

    # Codex prompt contained explicit verifier contract
    codex_prompt = backend_instance.captured_prompts.get("codex", "")
    assert "--- HERMES VERIFICATION CONTRACT ---" in codex_prompt
    assert '"verdict": "passed" | "failed"' in codex_prompt

    # 3. T5 produced verification_success observation
    success_obs = [o for o in obs_reg.list_for_task("T5_reverify") if o.kind == "verification_success"]
    assert len(success_obs) >= 1

    # D. Real Git Integration: Repaired code is in authoritative branch
    integration_wt = worktree_root / "integration"
    app_content = (integration_wt / "app.py").read_text(encoding="utf-8")
    assert 'FEATURE = "agy-hardened-repaired"' in app_content
    assert "Division by zero is not allowed" in app_content

    test_content = (integration_wt / "tests" / "test_app.py").read_text(encoding="utf-8")
    assert "test_divide_zero" in test_content

    # E. Reconstructed State matches full five-task repair history
    events = await event_store.list_events("job_repair_workflow")
    projector = RuntimeStateProjector()
    reconstructed = projector.project(events)
    assert reconstructed.job.state == JobState.COMPLETED
    assert reconstructed.graph.get_task("T4_repair").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T5_reverify").status == TaskStatus.SUCCEEDED


@pytest.mark.live_agents
@pytest.mark.anyio
async def test_phase11_0_live_agents_acceptance(tmp_path: Path):
    """
    Opt-in live agent acceptance test invoking locally installed CLIs
    (agy, claude, codex) against a tiny disposable repository.
    Skipped by default in CI unless HERMES_RUN_LIVE_AGENTS=1 is set.
    """
    if os.environ.get("HERMES_RUN_LIVE_AGENTS") != "1":
        pytest.skip("Live agent tests are opt-in. Set HERMES_RUN_LIVE_AGENTS=1 to execute with real local CLIs.")

    agy_bin = shutil.which("agy")
    claude_bin = shutil.which("claude")
    codex_bin = shutil.which("codex")

    missing = []
    if not agy_bin:
        missing.append("agy")
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
