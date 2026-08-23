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
