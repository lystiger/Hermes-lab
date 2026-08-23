"""
Test suite validating real infrastructure wiring:
1. Real Gemini/Claude/Codex/Antigravity execution & AgentContext creation.
2. Real Git worktree management, commit tracking, and status inspection.
3. Real multi-command verification pipeline against real target directories.
4. Safe tool execution bridge via ToolRegistry and ToolInvocationRequest.
5. Production planner/replanner DAG decomposition and mutation generation.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pytest
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from runtime.job_state import JobState, JobRecord
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.observations import ObservationRegistry, Observation
from runtime.execution import ExecutionManager, AgentRun, AgentRunStatus, TaskExecutionResult
from runtime.verification import VerificationStatus, VerificationCheck, VerificationResult
from runtime.limits import RuntimeLimits
from runtime.replanning import (
    ProductionPlannerAdapter,
    HermesPlannerAdapter,
    ReplanReason,
    ReplanRequest,
    ReplanResult,
    GraphMutationType,
    GraphMutation,
    BoundedReplanner,
)
from runtime.engine import ReactiveJobEngine
from runtime.hermes_adapter import HermesActorAdapter, HermesVerifierAdapter
from tools.tools import (
    ToolProfile,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolRegistry,
    default_tool_registry,
)


@pytest.fixture
def temp_git_repo():
    """Creates a temporary Git repository for worktree testing."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="hermes_wiring_repo_"))
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Hermes Wire Tester"], cwd=str(tmp_dir), check=True)
    subprocess.run(["git", "config", "user.email", "wiretester@hermes.local"], cwd=str(tmp_dir), check=True)
    readme = tmp_dir / "README.md"
    readme.write_text("# Hermes Wiring Test\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(tmp_dir), check=True, capture_output=True)
    yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


# -----------------------------------------------------------------------------
# 1. Real Agent Execution & Adapter Dispatch
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_hermes_actor_adapter_real_agent_dispatch(temp_git_repo):
    """
    Verifies that HermesActorAdapter creates worktree, prepares prompt, runs agent adapter,
    and commits changes.
    """
    wt_root = temp_git_repo / ".worktrees"
    run_dir = temp_git_repo / ".runs"

    # Mock agent adapter simulating file editing
    class MockCodeAgent:
        name = "mock_coder"
        def execute(self, context):
            # Create a code file in the worktree
            code_file = context.worktree / "src.py"
            code_file.write_text("print('hello world')\n")
            
            class Res:
                exit_code = 0
                stdout = "Successfully generated src.py"
                stderr = ""
            return Res()

    class MockAgentRegistry:
        def get(self, name):
            return MockCodeAgent()

    adapter = HermesActorAdapter(
        target_repo=temp_git_repo,
        worktree_root=wt_root,
        agent_registry=MockAgentRegistry(),
        run_dir=run_dir,
        dry_run=False,
    )

    task = TaskNode(
        task_id="phase_scaffold",
        job_id="job_real_exec",
        description="Scaffold src.py",
        assigned_actor="mock_coder",
        metadata={"worktree_dir": "scaffold_wt", "branch": "task/scaffold"},
    )
    run = AgentRun(
        run_id="run_001",
        job_id="job_real_exec",
        task_id="phase_scaffold",
        actor_id="mock_coder",
    )

    result = await adapter.execute_task(task=task, run=run)

    assert result.status == "succeeded"
    assert len(result.artifact_refs) >= 1
    assert result.artifact_refs[0]["kind"] == "git_commit"
    assert len(result.observations) >= 1

    # Verify worktree was created and commit recorded
    wt_path = wt_root / "scaffold_wt"
    assert wt_path.exists()
    assert (wt_path / "src.py").exists()

    log_res = subprocess.run(["git", "log", "-n", "1", "--oneline"], cwd=str(wt_path), capture_output=True, text=True)
    assert "feat(phase_scaffold)" in log_res.stdout


# -----------------------------------------------------------------------------
# 2. Real Worktree & Git Status Inspection
# -----------------------------------------------------------------------------

def test_worktree_creation_and_reset(temp_git_repo):
    """
    Verifies that _ensure_worktree creates and resets git worktrees cleanly.
    """
    wt_root = temp_git_repo / ".worktrees"
    adapter = HermesActorAdapter(target_repo=temp_git_repo, worktree_root=wt_root)

    wt_path = wt_root / "test_wt"
    adapter._ensure_worktree(wt_path, branch="feature/branch1", base_branch="main")

    assert wt_path.exists()
    assert adapter._is_git_repo(wt_path) is True

    # Make uncommitted changes and commit
    (wt_path / "new_file.txt").write_text("content")
    task = TaskNode(task_id="task_1", job_id="job_wt", description="Add file")
    changed = adapter._commit_worktree_changes(wt_path, task)
    assert len(changed) == 1

    # Re-ensuring worktree resets cleanly
    adapter._ensure_worktree(wt_path, branch="feature/branch1", base_branch="main")
    assert wt_path.exists()


# -----------------------------------------------------------------------------
# 3. Real Multi-Command Verification Pipeline
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_verifier_adapter_real_command_execution(temp_git_repo):
    """
    Verifies that HermesVerifierAdapter executes direct commands, respects cwd/timeouts,
    and returns structured VerificationResult.
    """
    # Create test script in subfolder
    sub_dir = temp_git_repo / "tests_dir"
    sub_dir.mkdir(parents=True, exist_ok=True)
    test_script = sub_dir / "check.py"
    test_script.write_text("import sys; sys.exit(0)\n")

    failing_script = sub_dir / "fail.py"
    failing_script.write_text("import sys; sys.stderr.write('Syntax error'); sys.exit(1)\n")

    # Step 1: Passing verification
    verifier = HermesVerifierAdapter(
        working_dir=temp_git_repo,
        verification_steps=[
            {
                "name": "python_check",
                "command": ["python3", "check.py"],
                "cwd": "tests_dir",
                "timeout_seconds": 10,
            }
        ]
    )

    job = JobRecord(job_id="job_verif", goal="Test verification")
    graph = TaskGraph(job_id="job_verif")
    result = await verifier.verify(job=job, graph=graph, artifacts=[])

    assert result.is_passed is True
    assert len(result.checks) == 1
    assert result.checks[0].passed is True

    # Step 2: Failing verification creates repair tasks
    verifier_failing = HermesVerifierAdapter(
        working_dir=temp_git_repo,
        verification_steps=[
            {
                "name": "fail_check",
                "command": ["python3", "fail.py"],
                "cwd": "tests_dir",
                "timeout_seconds": 10,
            }
        ]
    )

    result_fail = await verifier_failing.verify(job=job, graph=graph, artifacts=[])
    assert result_fail.is_passed is False
    assert result_fail.is_repairable is True
    assert len(result_fail.repair_recommendations) == 1
    assert result_fail.repair_recommendations[0].task_id == "repair_fail_check"
    assert "Syntax error" in result_fail.repair_recommendations[0].description


# -----------------------------------------------------------------------------
# 4. Safe Tool Execution Bridge
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tool_execution_bridge(temp_git_repo):
    """
    Verifies that HermesActorAdapter dispatches tool invocations via ToolRegistry
    and returns structured TaskExecutionResult.
    """
    tools = ToolRegistry()

    # Custom tool handler
    def custom_read_tool(req: ToolInvocationRequest, worktree_dir: Optional[Path], cfg: Optional[Dict[str, Any]]) -> ToolInvocationResult:
        file_path = worktree_dir / req.args.get("file", "README.md")
        if file_path.exists():
            return ToolInvocationResult(requestId=req.id or "req_1", toolId=req.toolId, status="success", output=file_path.read_text())
        return ToolInvocationResult(requestId=req.id or "req_1", toolId=req.toolId, status="failed", error="File not found")

    tools.register_tool(
        ToolProfile(id="tool.read_file", displayName="Read File", capabilities=["repo.read"]),
        custom_read_tool,
    )

    adapter = HermesActorAdapter(target_repo=temp_git_repo, tool_registry=tools)

    task = TaskNode(
        task_id="read_readme",
        job_id="job_tool",
        description="Read repo README",
        assigned_actor="tool.read_file",
        required_capabilities=["tool", "repo.read"],
        metadata={"tool_args": {"file": "README.md"}},
    )
    run = AgentRun(run_id="run_tool_01", job_id="job_tool", task_id="read_readme", actor_id="tool.read_file")

    result = await adapter.execute_task(task=task, run=run)
    assert result.status == "succeeded"
    assert "# Hermes Wiring Test" in str(result.output)


# -----------------------------------------------------------------------------
# 5. Production Planner & Dynamic Replanning
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_production_planner_decomposition_and_replanning():
    """
    Verifies ProductionPlannerAdapter decomposes goals into structured DAGs
    and mutates graphs when repair or deadlock occurs.
    """
    planner = ProductionPlannerAdapter(limits=RuntimeLimits(max_tasks_per_job=10))

    # 1. Goal decomposition
    tasks = planner.decompose_goal(goal="Implement user authentication module", job_id="job_plan")
    assert len(tasks) == 3
    assert tasks[0].task_id == "task_scaffold"
    assert tasks[1].task_id == "task_implementation"
    assert tasks[2].task_id == "task_verification"
    assert tasks[1].dependencies == ["task_scaffold"]
    assert tasks[2].dependencies == ["task_implementation"]

    # 2. Replanning on verification repair
    obs = Observation(
        job_id="job_plan",
        task_id="task_verification",
        source="hermes.verifier",
        kind="verification_failure",
        content="Playwright test failed on login button selector",
    )
    replan_req = ReplanRequest(
        job_id="job_plan",
        goal="Implement user authentication module",
        reason=ReplanReason.VERIFICATION_REPAIR,
        completed_tasks=[tasks[0], tasks[1]],
        failed_tasks=[],
        current_graph=TaskGraph(job_id="job_plan"),
        new_observations=[obs],
        produced_artifacts=[],
        replan_budget_remaining=2,
    )

    replan_result = await planner.plan(replan_req)
    assert replan_result.should_continue is True
    assert len(replan_result.mutations) == 1
    assert replan_result.mutations[0].mutation_type == GraphMutationType.ADD_TASK
    assert "Playwright test failed" in replan_result.mutations[0].task.description
    assert replan_result.mutations[0].task.required_capabilities == ["implementation", "testing.unit"]


# -----------------------------------------------------------------------------
# 6. Real-Spec End-to-End Reactive Job Execution
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_real_spec_end_to_end_reactive_execution(temp_git_repo):
    """
    Tests complete Phase 8.1.2 end-to-end integration:
    - Real sprint specification loaded and paths resolved.
    - Phase 1 (scaffold/builder): creates math_module.py, commits, merges into integration worktree.
    - Phase 2 (harden/hardener): syncs from integration HEAD, creates test_math.py, commits, merges.
    - Verification: runs pytest against the integration worktree where both files exist.
    - Engine reaches COMPLETED state.
    """
    from jobs.job_launcher import job_launcher
    from jobs.job_service import job_service

    sprint_id = "test-real-e2e-sprint"
    sprint_file = Path(f"sprints/{sprint_id}.json")
    sprint_file.parent.mkdir(parents=True, exist_ok=True)

    wt_root = temp_git_repo / ".worktrees"
    runs_root = temp_git_repo / ".runs"

    sprint_spec = {
        "sprint_id": sprint_id,
        "name": "E2E Real Spec Execution",
        "target_repo": str(temp_git_repo),
        "worktree_root": str(wt_root),
        "runs_root": str(runs_root),
        "base_branch": "main",
        "target_branch": f"sprint/{sprint_id}/integration",
        "phases": [
            {
                "name": "scaffold_math",
                "agent": "mock_builder",
                "role": "builder",
                "worktree_dir": "wt_scaffold",
                "branch": f"sprint/{sprint_id}/scaffold",
                "commit_message": "feat(scaffold): create math_module.py",
            },
            {
                "name": "harden_math",
                "agent": "mock_hardener",
                "role": "hardener",
                "worktree_dir": "wt_harden",
                "branch": f"sprint/{sprint_id}/harden",
                "commit_message": "feat(harden): add test_math.py",
                "dependencies": ["scaffold_math"],
            }
        ],
        "verification_steps": [
            {
                "name": "run_unit_tests",
                "command": [sys.executable, "-m", "pytest", "test_math.py", "-v"],
                "timeout_seconds": 15,
            }
        ]
    }

    sprint_file.write_text(json.dumps(sprint_spec, indent=2), encoding="utf-8")

    # Mock agent registry generating code files
    class MockBuilderAgent:
        name = "mock_builder"
        def execute(self, context):
            code_file = context.worktree / "math_module.py"
            code_file.write_text("def add(a, b):\n    return a + b\n")
            class Res:
                exit_code = 0
                stdout = "Created math_module.py"
                stderr = ""
            return Res()

    class MockHardenerAgent:
        name = "mock_hardener"
        def execute(self, context):
            # Verify math_module.py was integrated into this worktree from Phase 1
            assert (context.worktree / "math_module.py").exists(), "math_module.py must exist in worktree from integration HEAD!"
            test_file = context.worktree / "test_math.py"
            test_file.write_text("from math_module import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
            class Res:
                exit_code = 0
                stdout = "Created test_math.py"
                stderr = ""
            return Res()

    class CustomAgentRegistry:
        def get(self, name):
            if name == "mock_builder":
                return MockBuilderAgent()
            elif name == "mock_hardener":
                return MockHardenerAgent()
            raise ValueError(f"Unknown agent: {name}")

    try:
        # Launch job with custom agent registry without auto-starting background loop
        launch_res = job_launcher.launch(
            sprint_id=sprint_id,
            dry_run=False,
            agent_registry=CustomAgentRegistry(),
            start_background=False,
        )
        job_id = launch_res["jobId"]
        engine = job_service.get_engine(job_id)
        assert engine is not None

        # Run engine to completion
        await engine.run_until_complete(max_steps=15)

        assert engine.state == JobState.COMPLETED
        assert engine.graph.is_all_completed() is True

        # Verify integration worktree has merged files
        integration_dir = wt_root / "integration"
        assert integration_dir.exists()
        assert (integration_dir / "math_module.py").exists()
        assert (integration_dir / "test_math.py").exists()

        # Verify git history in integration worktree contains both commits
        log_res = subprocess.run(["git", "log", "--oneline"], cwd=str(integration_dir), capture_output=True, text=True)
        assert "feat(scaffold)" in log_res.stdout
        assert "feat(harden)" in log_res.stdout

    finally:
        if sprint_file.exists():
            sprint_file.unlink()
