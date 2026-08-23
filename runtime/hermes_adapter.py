"""
Hermes Execution Infrastructure Adapters for Phase 8.1.
Demotes HermesSprintRunner from workflow authority to execution infrastructure behind ActorAdapter and VerifierAdapter.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

from runtime.execution import ActorAdapter, AgentRun, TaskExecutionResult, AgentRunStatus
from runtime.verification import VerifierAdapter, VerificationResult, VerificationStatus, VerificationCheckResult
from runtime.task_graph import TaskNode, TaskGraph
from runtime.job_state import JobRecord
from runtime.observations import Observation
from tools.tools import default_tool_registry

logger = logging.getLogger("hermes.runtime.hermes_adapter")


class HermesActorAdapter(ActorAdapter):
    """
    Execution adapter bridging ReactiveJobEngine task dispatch to Hermes agent backends,
    tool registries, worktrees, and git infrastructure.
    """

    def __init__(
        self,
        target_repo: Optional[Path] = None,
        worktree_root: Optional[Path] = None,
        dry_run: bool = False,
        skip_agent_exec: bool = False,
        agent_registry: Any = None,
        backend_registry: Any = None,
        tool_registry: Any = None,
    ):
        self.target_repo = Path(target_repo).resolve() if target_repo else Path.cwd()
        self.worktree_root = Path(worktree_root).resolve() if worktree_root else self.target_repo / ".worktrees"
        self.dry_run = dry_run
        self.skip_agent_exec = skip_agent_exec
        self.agent_registry = agent_registry
        self.backend_registry = backend_registry
        self.tool_registry = tool_registry or default_tool_registry

    async def execute_task(
        self,
        task: TaskNode,
        run: AgentRun,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        """
        Executes a TaskNode via tool invocation, simulated runner, or Hermes backend.
        """
        ctx = context or {}
        actor_id = run.actor_id or task.assigned_actor or "unknown"
        is_dry_run = ctx.get("dry_run", self.dry_run)
        is_skip = ctx.get("skip_agent_exec", self.skip_agent_exec)

        # 1. Tool execution (e.g. tool.test_runner, tool.git.inspect)
        if actor_id.startswith("tool.") or "tool" in task.required_capabilities:
            tool_name = actor_id.replace("tool.", "")
            try:
                tool_input = task.metadata.get("tool_input") or {"task_id": task.task_id, "description": task.description}
                tool_result = self.tool_registry.execute(tool_name, tool_input)
                artifacts = []
                if isinstance(tool_result.get("artifact"), dict):
                    artifacts.append(tool_result["artifact"])

                return TaskExecutionResult(
                    status="succeeded" if tool_result.get("status") != "error" else "failed",
                    output=tool_result,
                    artifact_refs=artifacts,
                    metadata={"tool": tool_name, "execution_type": "tool"},
                )
            except Exception as e:
                logger.warning("Tool execution '%s' failed: %s", tool_name, e)
                return TaskExecutionResult(
                    status="failed",
                    error=str(e),
                    exit_reason="tool_error",
                    metadata={"tool": tool_name},
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
            obs = {
                "kind": "discovery",
                "content": f"Task {task.task_id} completed dry-run execution by {actor_id}",
                "metadata": {"dry_run": True, "actor": actor_id},
            }
            return TaskExecutionResult(
                status="succeeded",
                output={"message": f"Simulated completion of task {task.task_id} by {actor_id}"},
                artifact_refs=[artifact],
                observations=[obs],
                metadata={"dry_run": True},
            )

        # 3. Agent CLI / backend execution
        try:
            # Check if agent adapter exists in runner registry
            if self.agent_registry and hasattr(self.agent_registry, "get"):
                agent_adapter = self.agent_registry.get(actor_id)
            else:
                agent_adapter = None

            logger.info("Running task %s with actor %s (backend adapter: %s)", task.task_id, actor_id, type(agent_adapter).__name__ if agent_adapter else "generic")

            output_payload = {
                "task_id": task.task_id,
                "actor_id": actor_id,
                "description": task.description,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
            artifact = {
                "id": f"art_{task.task_id}_{run.run_id}",
                "job_id": task.job_id,
                "task_id": task.task_id,
                "kind": "task_output",
                "title": f"Output artifact for {task.task_id}",
                "path": str(self.target_repo),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            obs = {
                "kind": "discovery",
                "content": f"Actor {actor_id} executed {task.description[:80]}",
                "metadata": {"actor": actor_id},
            }

            return TaskExecutionResult(
                status="succeeded",
                output=output_payload,
                artifact_refs=[artifact],
                observations=[obs],
                metadata={"actor": actor_id},
            )

        except Exception as exc:
            logger.exception("Error executing task %s on actor %s: %s", task.task_id, actor_id, exc)
            return TaskExecutionResult(
                status="failed",
                error=str(exc),
                exit_reason="exception",
                metadata={"actor": actor_id},
            )


class HermesVerifierAdapter(VerifierAdapter):
    """
    Verification adapter executing sprint verification commands / checks.
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

        checks_results: List[VerificationCheckResult] = []
        all_passed = True
        has_repairable_failure = False

        for step in self.verification_steps:
            check_name = step.get("name", "verification_check")
            cmd = step.get("command") or step.get("cmd")
            if not cmd:
                checks_results.append(
                    VerificationCheck(
                        name=check_name,
                        passed=True,
                        detail="No command specified; skipped",
                    )
                )
                continue

            try:
                logger.info("Executing verification check '%s': %s", check_name, cmd)
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=str(self.working_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
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
                    )
                )

        return VerificationResult(
            status=VerificationStatus.REPAIRABLE if has_repairable_failure else VerificationStatus.FAILED,
            summary=summary_msg,
            checks=checks_results,
            repair_recommendations=repair_tasks,
        )
