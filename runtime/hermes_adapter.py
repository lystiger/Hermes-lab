"""
Hermes Execution Infrastructure Adapters for Phase 8.1.
Demotes HermesSprintRunner from workflow authority to execution infrastructure behind ActorAdapter and VerifierAdapter.
Provides:
1. Real Gemini/Claude/Codex/Antigravity execution via AgentRegistry and BackendRegistry.
2. Real worktree and Git branch management, committing, and integration merging.
3. Real multi-command verification test runner against target repository / worktrees.
4. Safe, validated tool execution bridge via ToolRegistry and ToolInvocationRequest.
5. Production planner and replanner adapter (HermesPlannerAdapter).
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Union

from runtime.execution import ActorAdapter, AgentRun, TaskExecutionResult, AgentRunStatus
from runtime.verification import VerifierAdapter, VerificationResult, VerificationStatus, VerificationCheck
from runtime.task_graph import TaskNode, TaskGraph
from runtime.job_state import JobRecord
from runtime.observations import Observation
from runtime.replanning import ProductionPlannerAdapter, PlannerAdapter, ReplanRequest, ReplanResult, GraphMutation, GraphMutationType
from tools.tools import (
    ToolRegistry,
    ToolInvocationRequest,
    ToolInvocationResult,
    default_tool_registry,
    parse_tool_requests,
)

logger = logging.getLogger("hermes.runtime.hermes_adapter")


class HermesActorAdapter(ActorAdapter):
    """
    Execution adapter bridging ReactiveJobEngine task dispatch to real Hermes agent backends,
    tool registries, worktrees, and Git infrastructure.
    """

    def __init__(
        self,
        target_repo: Optional[Path] = None,
        worktree_root: Optional[Path] = None,
        dry_run: bool = False,
        skip_agent_exec: bool = False,
        agent_registry: Any = None,
        backend_registry: Any = None,
        tool_registry: Optional[ToolRegistry] = None,
        run_dir: Optional[Path] = None,
    ):
        self.target_repo = Path(target_repo).resolve() if target_repo else Path.cwd()
        self.worktree_root = Path(worktree_root).resolve() if worktree_root else self.target_repo / ".worktrees"
        self.dry_run = dry_run
        self.skip_agent_exec = skip_agent_exec
        self.agent_registry = agent_registry
        self.backend_registry = backend_registry
        self.tool_registry = tool_registry or default_tool_registry
        self.run_dir = Path(run_dir).resolve() if run_dir else Path.home() / "hermes-runs" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _ensure_worktree(self, worktree_path: Path, branch: str, base_branch: str = "main") -> Path:
        """
        Creates or validates a Git worktree for an isolated task execution.
        """
        if not self._is_git_repo(self.target_repo):
            worktree_path.mkdir(parents=True, exist_ok=True)
            return worktree_path

        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if worktree_path.exists():
            # Check if valid worktree
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
            )
            if res.returncode == 0 and res.stdout.strip() == "true":
                # Reset cleanly to base branch
                subprocess.run(
                    ["git", "reset", "--hard", base_branch],
                    cwd=str(worktree_path),
                    capture_output=True,
                )
                return worktree_path

        # Add new worktree
        res_branch = subprocess.run(
            ["git", "branch", "--list", branch],
            cwd=str(self.target_repo),
            capture_output=True,
            text=True,
        )
        if res_branch.stdout.strip():
            cmd = ["git", "worktree", "add", str(worktree_path), branch]
        else:
            cmd = ["git", "worktree", "add", "-b", branch, str(worktree_path), base_branch]

        proc = subprocess.run(cmd, cwd=str(self.target_repo), capture_output=True, text=True)
        if proc.returncode != 0:
            logger.warning("Git worktree creation failed (%s); falling back to direct dir", proc.stderr)
            worktree_path.mkdir(parents=True, exist_ok=True)

        return worktree_path

    @staticmethod
    def _is_git_repo(path: Path) -> bool:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(path),
                capture_output=True,
                text=True,
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    def _commit_worktree_changes(self, worktree_path: Path, task: TaskNode) -> List[str]:
        """
        Commits any uncommitted file changes in the task worktree.
        """
        if not self._is_git_repo(worktree_path):
            return []

        status_res = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
        )
        changed_lines = [l.strip() for l in status_res.stdout.splitlines() if l.strip()]
        if not changed_lines:
            return []

        # Add and commit
        subprocess.run(["git", "add", "-A"], cwd=str(worktree_path), capture_output=True)
        commit_msg = task.metadata.get("commit_message") or f"feat({task.task_id}): {task.description[:72]}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(worktree_path), capture_output=True)
        return changed_lines

    async def execute_task(
        self,
        task: TaskNode,
        run: AgentRun,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        """
        Executes a TaskNode via real tool invocation, simulated runner, or real agent backends.
        """
        ctx = context or {}
        actor_id = run.actor_id or task.assigned_actor or "unknown"
        is_dry_run = ctx.get("dry_run", self.dry_run)
        is_skip = ctx.get("skip_agent_exec", self.skip_agent_exec)

        # 1. Tool execution (e.g. tool.test_runner, tool.git.inspect, tool.read_file)
        if actor_id.startswith("tool.") or "tool" in task.required_capabilities:
            tool_id = actor_id if actor_id.startswith("tool.") else f"tool.{actor_id}"
            req_args = task.metadata.get("tool_args") or task.metadata.get("args") or {
                "task_id": task.task_id,
                "query": task.description,
            }
            req = ToolInvocationRequest(
                toolId=tool_id,
                args=req_args,
                jobId=task.job_id,
                timeoutSeconds=task.metadata.get("timeout_seconds", 60),
            )
            job_cfg = {
                "allow_tools": True,
                "allowed_tools": [tool_id, "tool.test_runner", "tool.git.inspect", "tool.read_file", "tool.write_file"],
                "require_actor_capability": False,
                "read_only_only": False,
            }

            try:
                tool_res: ToolInvocationResult = self.tool_registry.execute(
                    request=req,
                    worktree_dir=self.target_repo,
                    job_config=job_cfg,
                )
                artifacts = list(tool_res.artifactRefs or [])
                status_str = "succeeded" if tool_res.status == "success" else "failed"
                return TaskExecutionResult(
                    status=status_str,
                    output=tool_res.output,
                    error=tool_res.error,
                    artifact_refs=artifacts,
                    metadata={"tool": tool_id, "execution_type": "tool_actor"},
                )
            except Exception as e:
                logger.warning("Tool execution '%s' raised exception: %s", tool_id, e)
                return TaskExecutionResult(
                    status="failed",
                    error=str(e),
                    exit_reason="tool_error",
                    metadata={"tool": tool_id},
                )

        # 2. Dry run / Mock execution mode
        if is_dry_run or is_skip:
            logger.info("Executing task %s in dry-run/skip mode on actor %s", task.task_id, actor_id)
            artifact = {
                "id": f"art_{task.task_id}_{run.run_id}",
                "job_id": task.job_id,
                "task_id": task.task_id,
                "kind": "code_patch",
                "title": f"Simulated artifact for {task.task_id}",
                "path": str(self.target_repo),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            obs = Observation(
                job_id=task.job_id,
                task_id=task.task_id,
                source=actor_id,
                kind="discovery",
                content=f"Task {task.task_id} completed dry-run execution by {actor_id}",
                metadata={"dry_run": True, "actor": actor_id},
            )
            return TaskExecutionResult(
                status="succeeded",
                output={"message": f"Simulated completion of task {task.task_id} by {actor_id}"},
                artifact_refs=[artifact],
                observations=[obs],
                metadata={"dry_run": True},
            )

        # 3. Real Agent CLI / Backend Execution
        try:
            from runner.agents.registry import default_registry
            from runner.backends.registry import default_backend_registry
            from runner.agents.base import AgentContext

            reg = self.agent_registry or default_registry
            backend_reg = self.backend_registry or default_backend_registry

            agent_adapter = reg.get(actor_id)
            backend_name = task.metadata.get("backend") or "subprocess"
            backend = backend_reg.get(
                backend_name,
                run_dir=self.run_dir,
                sprint_id=task.job_id,
                logger=logger,
            )

            # Setup worktree
            wt_name = task.metadata.get("worktree_dir") or task.task_id
            branch_name = task.metadata.get("branch") or f"task/{task.task_id}"
            base_branch = task.metadata.get("base_branch") or "main"
            worktree_path = self._ensure_worktree(self.worktree_root / wt_name, branch_name, base_branch)

            # Prepare prompt
            prompt_content = task.description
            prompt_file = task.metadata.get("prompt_file")
            if prompt_file:
                p_path = Path(prompt_file)
                if not p_path.is_absolute():
                    p_path = self.target_repo / p_path
                if p_path.exists():
                    prompt_content = p_path.read_text(encoding="utf-8")

            # Logs
            self.run_dir.mkdir(parents=True, exist_ok=True)
            stdout_file = self.run_dir / f"{task.task_id}_{actor_id}_stdout.log"
            stderr_file = self.run_dir / f"{task.task_id}_{actor_id}_stderr.log"

            agent_ctx = AgentContext(
                runner=self,
                phase={
                    "name": task.task_id,
                    "agent": actor_id,
                    "role": task.metadata.get("role", "builder"),
                    "cmd_options": task.metadata.get("options", {}),
                },
                worktree=worktree_path,
                prompt=prompt_content,
                options=task.metadata.get("options", {}),
                stdout_file=stdout_file,
                stderr_file=stderr_file,
                timeout_seconds=task.metadata.get("timeout_seconds", 300),
                backend=backend,
            )

            logger.info("Executing real agent %s for task %s in %s", actor_id, task.task_id, worktree_path)
            raw_res = agent_adapter.execute(agent_ctx)
            exit_code = getattr(raw_res, "exit_code", 0)
            stdout_text = getattr(raw_res, "stdout", "") or ""
            stderr_text = getattr(raw_res, "stderr", "") or ""

            # Check for embedded tool requests in stdout
            parsed_tool_reqs = parse_tool_requests(stdout_text) if parse_tool_requests else []
            for tr in parsed_tool_reqs:
                try:
                    self.tool_registry.execute(tr, worktree_dir=worktree_path)
                except Exception as te:
                    logger.warning("Embedded tool request failed: %s", te)

            # Commit changes and collect artifacts
            changed_files = self._commit_worktree_changes(worktree_path, task)

            artifacts = []
            if changed_files:
                artifacts.append({
                    "id": f"art_{task.task_id}_{run.run_id}",
                    "job_id": task.job_id,
                    "task_id": task.task_id,
                    "kind": "git_commit",
                    "title": f"Git commit for {task.task_id} ({len(changed_files)} files)",
                    "path": str(worktree_path),
                    "files": changed_files,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

            obs = Observation(
                job_id=task.job_id,
                task_id=task.task_id,
                source=actor_id,
                kind="execution_output",
                content=f"Agent {actor_id} completed task {task.task_id} with exit code {exit_code}",
                metadata={"changed_files_count": len(changed_files), "exit_code": exit_code},
            )

            status_str = "succeeded" if exit_code == 0 else "failed"
            return TaskExecutionResult(
                status=status_str,
                output={"stdout": stdout_text[:5000], "exit_code": exit_code},
                error=stderr_text if exit_code != 0 else None,
                artifact_refs=artifacts,
                observations=[obs],
                metadata={"actor": actor_id, "worktree": str(worktree_path)},
            )

        except Exception as exc:
            logger.exception("Error executing real task %s on actor %s: %s", task.task_id, actor_id, exc)
            return TaskExecutionResult(
                status="failed",
                error=str(exc),
                exit_reason="exception",
                metadata={"actor": actor_id},
            )


class HermesVerifierAdapter(VerifierAdapter):
    """
    Verification adapter executing sprint verification commands / checks
    directly against the real target repository or integration worktree.
    """

    def __init__(
        self,
        verifier_id: str = "hermes.verifier",
        verification_steps: Optional[List[Dict[str, Any]]] = None,
        working_dir: Optional[Path] = None,
    ):
        self.verifier_id = verifier_id
        self.verification_steps = verification_steps or []
        self.working_dir = Path(working_dir).resolve() if working_dir else Path.cwd()

    async def verify(
        self,
        job: JobRecord,
        graph: TaskGraph,
        artifacts: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Executes verification checks and returns structured VerificationResult.
        """
        if not self.verification_steps:
            return VerificationResult(
                status=VerificationStatus.PASSED,
                summary="No verification checks configured; verified by default",
                checks=[],
            )

        checks_results: List[VerificationCheck] = []
        all_passed = True
        has_repairable_failure = False

        for step in self.verification_steps:
            check_name = step.get("name", "verification_check")
            raw_cmd = step.get("command") or step.get("cmd")
            if not raw_cmd:
                checks_results.append(
                    VerificationCheck(
                        name=check_name,
                        passed=True,
                        detail="No command specified; skipped",
                    )
                )
                continue

            step_cwd = self.working_dir
            if step.get("cwd"):
                rel_cwd = Path(step["cwd"])
                if not rel_cwd.is_absolute():
                    step_cwd = (self.working_dir / rel_cwd).resolve()

            timeout_sec = step.get("timeout_seconds", 300)

            try:
                logger.info("Executing verification check '%s': %s (cwd=%s)", check_name, raw_cmd, step_cwd)
                if isinstance(raw_cmd, list):
                    proc = await asyncio.create_subprocess_exec(
                        *raw_cmd,
                        cwd=str(step_cwd),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                else:
                    proc = await asyncio.create_subprocess_shell(
                        raw_cmd,
                        cwd=str(step_cwd),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
                passed = proc.returncode == 0
                stdout_str = stdout.decode("utf-8", errors="replace").strip()
                stderr_str = stderr.decode("utf-8", errors="replace").strip()

                msg = f"Exit {proc.returncode}"
                if stderr_str:
                    msg += f": {stderr_str[:200]}"
                elif stdout_str:
                    msg += f": {stdout_str[:200]}"

                checks_results.append(
                    VerificationCheck(
                        name=check_name,
                        passed=passed,
                        detail=msg,
                        error=stderr_str if not passed else None,
                        repairable=not passed,
                        metadata={"stdout": stdout_str, "stderr": stderr_str, "returncode": proc.returncode},
                    )
                )

                if not passed:
                    all_passed = False
                    has_repairable_failure = True

            except asyncio.TimeoutError:
                logger.warning("Verification check '%s' timed out after %s seconds", check_name, timeout_sec)
                checks_results.append(
                    VerificationCheck(
                        name=check_name,
                        passed=False,
                        detail=f"Check timed out after {timeout_sec}s",
                        error=f"Timeout of {timeout_sec}s exceeded",
                        repairable=True,
                    )
                )
                all_passed = False
                has_repairable_failure = True

            except Exception as e:
                logger.warning("Verification check '%s' raised exception: %s", check_name, e)
                checks_results.append(
                    VerificationCheck(
                        name=check_name,
                        passed=False,
                        detail=str(e),
                        error=str(e),
                        repairable=True,
                    )
                )
                all_passed = False
                has_repairable_failure = True

        if all_passed:
            return VerificationResult(
                status=VerificationStatus.PASSED,
                summary=f"All {len(checks_results)} verification checks passed successfully",
                checks=checks_results,
            )

        failed_names = [c.name for c in checks_results if not c.passed]
        summary_msg = f"Verification failed on check(s): {', '.join(failed_names)}"

        repair_tasks = []
        for c in checks_results:
            if not c.passed:
                repair_tasks.append(
                    TaskNode(
                        task_id=f"repair_{c.name.replace(' ', '_').lower()}",
                        job_id=job.job_id,
                        description=f"Fix verification failure in '{c.name}': {c.detail or c.error}",
                        required_capabilities=["implementation", "testing"],
                        metadata={"failed_check": c.name, "check_error": c.error},
                    )
                )

        return VerificationResult(
            status=VerificationStatus.REPAIRABLE if has_repairable_failure else VerificationStatus.FAILED,
            summary=summary_msg,
            checks=checks_results,
            repair_recommendations=repair_tasks,
        )


# Planner adapter alias
HermesPlannerAdapter = ProductionPlannerAdapter
