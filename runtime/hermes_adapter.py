"""
Hermes Execution Infrastructure Adapters for Phase 8.1.3.
Provides:
1. Spec path resolution relative to specification directory and control root.
2. Normalized TaskNode metadata mapping (role, worktree_dir, branch, handoff, backend).
3. Compatible runtime controller for AgentContext (prompt rendering, persona, mailbox).
4. Authoritative integration worktree on target_branch from base_ref.
5. Merge of successful task commits into integration worktree.
6. Dependent task synchronization from integration HEAD.
7. Verification against the authoritative integration worktree.
8. Fail-closed error handling on worktree, sync, syntax, and Git merge errors.
9. Full preservation and enforcement of job ToolPolicy with no permissive default.
10. Production planner adapter (HermesPlannerAdapter / ProductionPlannerAdapter).
11. Blocking agent/Git work executed off the event loop under a per-repository lock.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path, PureWindowsPath
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from runtime.execution import ActorAdapter, AgentRun, TaskExecutionResult, AgentRunStatus
from runtime.verification import VerifierAdapter, VerificationResult, VerificationStatus, VerificationCheck
from runtime.task_graph import TaskNode, TaskGraph, TaskStatus
from runtime.job_state import JobRecord
from runtime.observations import Observation
from runtime.replanning import ProductionPlannerAdapter, PlannerAdapter, ReplanRequest, ReplanResult, GraphMutation, GraphMutationType
from runtime.capacity import UsageSnapshotNormalizer, default_capacity_registry
from tools.tools import (
    ToolProfile,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolPolicy,
    default_tool_registry,
    parse_tool_requests,
    LYSSTACK_TOOL_REQUEST_START,
    LYSSTACK_TOOL_REQUEST_END,
)

logger = logging.getLogger("hermes.runtime.hermes_adapter")

DEFAULT_CONTEXT_MAX_BYTES = 131072


class WorktreeError(RuntimeError):
    """Raised when a Git worktree cannot be created, validated, or synchronized."""


class ContextSpecError(ValueError):
    """Raised when a sprint specification declares an unusable context bundle."""


# Git mutations against one repository (worktree add, commit, integration merge,
# fetch/reset) are serialized per repository. Task worktrees are separate directories
# but share a single object store and `.git/worktrees` metadata, and the integration
# worktree is written by every task, so concurrent mutation corrupts shared state.
_REPO_GIT_LOCKS: Dict[str, threading.RLock] = {}
_REPO_GIT_LOCKS_GUARD = threading.Lock()


def repo_git_lock(repo_path: Union[str, Path]) -> threading.RLock:
    """Returns the process-wide reentrant Git mutation lock for a repository path."""
    key = str(Path(repo_path).resolve())
    with _REPO_GIT_LOCKS_GUARD:
        lock = _REPO_GIT_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _REPO_GIT_LOCKS[key] = lock
        return lock


def resolve_context_spec(context: Any, spec_dir: Path) -> Dict[str, Any]:
    """
    Normalizes a spec `context` block at launcher/spec-normalization time.

    `context.root` is resolved relative to the sprint specification directory (never
    the process working directory or the target repository), validated to be an
    existing directory, and returned as an absolute path. Files are validated to be
    relative and contained within the resolved root.

    Raises ContextSpecError when the declared bundle cannot be resolved.
    """
    if not isinstance(context, dict):
        raise ContextSpecError("'context' must be a JSON object")

    root_value = context.get("root")
    if not isinstance(root_value, str) or not root_value.strip():
        raise ContextSpecError("context.root must be a non-empty path string")

    root_path = Path(root_value)
    if not root_path.is_absolute():
        if PureWindowsPath(root_value).anchor:
            raise ContextSpecError("context.root must use a path native to the current platform")
        root_path = Path(spec_dir) / root_path
    root_path = root_path.resolve()
    if not root_path.is_dir():
        raise ContextSpecError(f"context.root does not exist or is not a directory: {root_value}")

    files = context.get("files")
    if (
        not isinstance(files, list)
        or not files
        or any(not isinstance(item, str) or not item.strip() for item in files)
    ):
        raise ContextSpecError("context.files must be a non-empty array of non-empty strings")

    max_bytes = context.get("max_bytes", DEFAULT_CONTEXT_MAX_BYTES)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ContextSpecError("context.max_bytes must be a positive integer")

    normalized_files: List[str] = []
    seen: set = set()
    for file_value in files:
        native_path = Path(file_value)
        windows_path = PureWindowsPath(file_value)
        if native_path.is_absolute() or windows_path.anchor or ".." in windows_path.parts:
            raise ContextSpecError(f"context file must be relative and contained: {file_value}")
        resolved = (root_path / native_path).resolve()
        try:
            resolved.relative_to(root_path)
        except ValueError as error:
            raise ContextSpecError(f"Context file escapes context.root: {file_value}") from error
        logical = resolved.relative_to(root_path).as_posix()
        if logical in seen:
            raise ContextSpecError(f"duplicate normalized context file: {file_value}")
        seen.add(logical)
        normalized_files.append(logical)

    normalized = dict(context)
    normalized["root"] = str(root_path)
    normalized["files"] = normalized_files
    normalized["max_bytes"] = max_bytes
    normalized["root_resolved"] = True
    return normalized


class HermesActorAdapter(ActorAdapter):
    """
    Execution adapter bridging ReactiveJobEngine task dispatch to real Hermes agent backends,
    tool registries, worktrees, and Git infrastructure.
    Acts as a compatible runtime controller for AgentContext.
    """

    def __init__(
        self,
        target_repo: Optional[Path] = None,
        worktree_root: Optional[Path] = None,
        run_dir: Optional[Path] = None,
        dry_run: bool = False,
        skip_agent_exec: bool = False,
        agent_registry: Any = None,
        backend_registry: Any = None,
        tool_registry: Any = None,
        spec: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
        base_ref: str = "main",
        target_branch: str = "sprint/integration",
    ):
        self.control_root = Path.cwd().resolve()
        self.target_repo = Path(target_repo).resolve() if target_repo else self.control_root
        self.worktree_root = Path(worktree_root).resolve() if worktree_root else self.target_repo / ".worktrees"
        self.run_dir = Path(run_dir).resolve() if run_dir else Path.home() / "hermes-runs" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.dry_run = dry_run
        self.skip_agent_exec = skip_agent_exec
        self.agent_registry = agent_registry
        self.backend_registry = backend_registry
        self.tool_registry = tool_registry or default_tool_registry
        self.spec = spec or {}
        self.job_id = job_id or f"job_{int(time.time())}"
        self.thread_id = self.job_id
        self.base_ref = base_ref
        self.target_branch = target_branch
        self.logger = logger
        self.persona_enabled = True
        self.controller_id = f"hermes.runtime:{self.job_id}"
        self._git_lock = repo_git_lock(self.target_repo)
        self.context_bundle = self._load_context_bundle()
        self._integration_ready = False
        self.is_fenced = False
        self.fencing_checker: Optional[Callable[[], bool]] = None
        self._active_subprocesses: Dict[str, Any] = {}

    def fence(self, reason: str = "Execution fenced") -> None:
        self.is_fenced = True
        logger.warning("Fencing HermesActorAdapter for job %s: %s", self.job_id, reason)
        self.terminate_all_subprocesses()

    def set_fencing_checker(self, checker: Callable[[], bool]) -> None:
        self.fencing_checker = checker

    def register_subprocess(self, key: str, proc: Any) -> None:
        self._active_subprocesses[key] = proc

    def unregister_subprocess(self, key: str) -> None:
        self._active_subprocesses.pop(key, None)

    def terminate_all_subprocesses(self) -> None:
        for key, proc in list(self._active_subprocesses.items()):
            if hasattr(proc, "poll") and proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception:
                    pass
        self._active_subprocesses.clear()

    def _verify_execution_fence(self, task: TaskNode, context: Optional[Dict[str, Any]] = None) -> None:
        if getattr(self, "is_fenced", False):
            raise RuntimeError(f"Authoritative Git mutation aborted: executor is fenced for job {self.job_id}")

        if self.fencing_checker and not self.fencing_checker():
            self.is_fenced = True
            raise RuntimeError(f"Authoritative Git mutation aborted: fencing check failed for job {self.job_id}")

        if context:
            engine = context.get("engine")
            if engine and (getattr(engine, "_fenced", False) or getattr(engine, "is_terminal", False)):
                self.is_fenced = True
                raise RuntimeError(f"Authoritative Git mutation aborted: engine is fenced/terminal for job {self.job_id}")

        if task.status == TaskStatus.CANCELLED:
            raise RuntimeError(f"Authoritative Git mutation aborted: task {task.task_id} is cancelled")

    def _load_context_bundle(self) -> str:
        """
        Loads and formats the context bundle declared in the spec.

        `context.root` must already be an absolute, resolved path: normalization is the
        launcher's responsibility (see resolve_context_spec). An unresolved relative root
        is a specification error and fails closed rather than being silently re-resolved
        against the target repository or the process working directory.
        """
        if not self.spec or "context" not in self.spec:
            return ""
        ctx = self.spec["context"]
        if not isinstance(ctx, dict):
            raise ContextSpecError("'context' must be a JSON object")

        root_val = ctx.get("root")
        files = ctx.get("files") or []
        if not root_val or not files:
            raise ContextSpecError("context requires both a 'root' and a non-empty 'files' list")

        root_path = Path(root_val)
        if not root_path.is_absolute():
            raise ContextSpecError(
                f"context.root must be resolved to an absolute path before execution: {root_val}"
            )
        if not root_path.is_dir():
            raise ContextSpecError(f"context.root does not exist or is not a directory: {root_val}")

        sections = ["--- LYSSTACK CONTEXT BUNDLE ---"]
        for f_name in files:
            f_path = (root_path / f_name).resolve()
            try:
                f_path.relative_to(root_path)
            except ValueError as error:
                raise ContextSpecError(f"Context file escapes context.root: {f_name}") from error
            if not f_path.is_file():
                raise ContextSpecError(f"Context file does not exist: {f_name}")
            try:
                content = f_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise ContextSpecError(f"Unable to read UTF-8 context file: {f_name}") from error
            sections.append(f"[{f_name}]\n{content}")
        sections.append("--- END CONTEXT BUNDLE ---")
        return "\n\n".join(sections)

    def run_cmd(self, cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Executes a command synchronously within the target repository or worktree."""
        run_cwd = cwd or self.target_repo
        proc = subprocess.run(
            cmd,
            cwd=str(run_cwd),
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            err_msg = proc.stderr.strip() or proc.stdout.strip() or f"Command '{' '.join(cmd)}' failed with exit code {proc.returncode}"
            raise RuntimeError(f"Git command failed in {run_cwd.name}: {err_msg}")
        return proc

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

    @staticmethod
    def _is_worktree_root(path: Path) -> bool:
        """
        True only when path is the top level of its own Git worktree.

        `--is-inside-work-tree` is true for any directory nested inside a repository, so it
        cannot distinguish a real worktree from a plain subdirectory of the target repo
        (worktree_root commonly lives inside it). Treating such a subdirectory as a worktree
        would point `git reset --hard` at the target repository itself.
        """
        if not path.exists() or not path.is_dir():
            return False
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(path),
                capture_output=True,
                text=True,
            )
        except Exception:
            return False
        if res.returncode != 0:
            return False
        try:
            return Path(res.stdout.strip()).resolve() == path.resolve()
        except OSError:
            return False

    def ensure_integration_worktree(self) -> Path:
        """
        Creates or validates the authoritative integration worktree on target_branch.

        Fails closed: when the target repository is a Git repository, a missing or
        non-Git integration directory is an error rather than a plain directory fallback.
        """
        integration_dir = self.worktree_root / "integration"
        if not self._is_git_repo(self.target_repo):
            integration_dir.mkdir(parents=True, exist_ok=True)
            return integration_dir

        with self._git_lock:
            if self._integration_ready and self._is_worktree_root(integration_dir):
                return integration_dir

            self.worktree_root.mkdir(parents=True, exist_ok=True)
            if not self._is_worktree_root(integration_dir):
                self._ensure_worktree(integration_dir, branch=self.target_branch, base_branch=self.base_ref)

            if not self._is_worktree_root(integration_dir):
                raise WorktreeError(
                    f"Integration worktree at {integration_dir} is not a valid Git worktree; "
                    "refusing to run against an unversioned integration directory"
                )
            self._integration_ready = True
            return integration_dir

    def _ensure_worktree(self, path: Path, branch: str, base_branch: str) -> Path:
        """
        Ensures a clean Git worktree exists at path checked out on branch.

        Fails closed: if the target repository is a Git repository, any failure to create
        or validate the worktree raises WorktreeError. Falling back to a plain directory
        would run an agent against unversioned files whose output can never be committed,
        integrated, or verified.
        """
        if not self._is_git_repo(self.target_repo):
            path.mkdir(parents=True, exist_ok=True)
            return path

        with self._git_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if self._is_worktree_root(path):
                    # Check for dirty uncommitted changes and clean them
                    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=str(path), capture_output=True, text=True)
                    if dirty.stdout.strip():
                        logger.warning("Resetting dirty uncommitted changes in worktree at %s", path.name)
                        self.run_cmd(["git", "reset", "--hard", "HEAD"], cwd=path)
                    return path
                if any(path.iterdir()):
                    raise WorktreeError(
                        f"Worktree path {path} already exists and is not a Git worktree root; refusing to reuse it"
                    )

            # Check if branch exists
            res_branch = self.run_cmd(["git", "branch", "--list", branch], cwd=self.target_repo, check=False)
            if res_branch.stdout.strip():
                cmd = ["git", "worktree", "add", str(path), branch]
            else:
                cmd = ["git", "worktree", "add", "-b", branch, str(path), base_branch]

            proc = subprocess.run(cmd, cwd=str(self.target_repo), capture_output=True, text=True)
            if proc.returncode != 0:
                detail = (proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}")
                raise WorktreeError(
                    f"Git worktree creation failed for branch '{branch}' at {path}: {detail}"
                )

            if not self._is_worktree_root(path):
                raise WorktreeError(f"Git reported success but {path} is not a valid worktree root")

            return path

    def sync_task_worktree_from_integration(self, worktree_path: Path) -> None:
        """
        Synchronizes a task worktree from the latest integration branch HEAD.

        Fails closed: a failed fetch or reset leaves the task on a stale base, so the agent
        would build against the wrong tree and produce a commit that silently reverts
        already-integrated work. Both commands raise on failure.
        """
        if not self._is_git_repo(self.target_repo):
            return
        if not self._is_worktree_root(worktree_path):
            raise WorktreeError(
                f"Cannot synchronize {worktree_path}: not a Git worktree root of {self.target_repo}"
            )

        logger.info("Synchronizing task worktree %s from %s", worktree_path.name, self.target_branch)
        with self._git_lock:
            try:
                self.run_cmd(["git", "fetch", ".", self.target_branch], cwd=worktree_path)
                self.run_cmd(["git", "reset", "--hard", "FETCH_HEAD"], cwd=worktree_path)
            except RuntimeError as exc:
                raise WorktreeError(
                    f"Failed to synchronize {worktree_path.name} from '{self.target_branch}': {exc}"
                ) from exc
            log_res = self.run_cmd(["git", "log", "-n", "3", "--oneline"], cwd=worktree_path, check=False)
        logger.info("Synced %s from %s:\n%s", worktree_path.name, self.target_branch, log_res.stdout)

    def inspect_changed_files(self, worktree_path: Path) -> List[str]:
        """Returns list of changed files in worktree."""
        if not self._is_worktree_root(worktree_path):
            return []
        res = self.run_cmd(["git", "status", "--porcelain", "--untracked-files=all"], cwd=worktree_path, check=False)
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    def validate_python_syntax(self, worktree_path: Path) -> None:
        """
        Validates syntax of all Python files in the worktree.

        Compiles in-memory rather than via py_compile so that no __pycache__ artifacts are
        written into the worktree, which would otherwise be staged into the task commit and
        trip the verifier-role mutation check.
        """
        for py_file in worktree_path.rglob("*.py"):
            if any(part in (".git", "__pycache__") for part in py_file.parts):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as e:
                raise RuntimeError(f"Unable to read Python file {py_file.name}: {e}")
            try:
                compile(source, str(py_file), "exec")
            except SyntaxError as e:
                raise RuntimeError(f"Python syntax error in {py_file.name}: {e}")

    def _commit_and_integrate_changes(
        self,
        worktree_path: Path,
        task: TaskNode,
        role: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Stages changes, commits them on the task branch, and merges into the integration worktree.

        The commit and the integration merge are held under the repository Git lock as one
        unit: concurrent tasks share a single object store and a single integration worktree,
        so interleaved commits and merges would race on `.git` state and on the integration
        working directory.
        """
        if not self._is_worktree_root(worktree_path):
            return None

        with self._git_lock:
            # 1. Verify execution fence before staging or inspecting files
            self._verify_execution_fence(task, context)

            changed_files = self.inspect_changed_files(worktree_path)
            if not changed_files or role == "verifier":
                return None

            commit_msg = task.metadata.get("commit_message") or f"feat({task.task_id}): {task.description[:72]}"
            logger.info("Staging and committing %d files in %s: %s", len(changed_files), worktree_path.name, commit_msg)
            self.run_cmd(["git", "add", "."], cwd=worktree_path)

            # 2. Verify execution fence before creating commit
            self._verify_execution_fence(task, context)
            self.run_cmd(["git", "commit", "-m", commit_msg], cwd=worktree_path)

            commit_sha_res = self.run_cmd(["git", "rev-parse", "HEAD"], cwd=worktree_path)
            commit_sha = commit_sha_res.stdout.strip()

            # Merge into integration worktree
            integration_dir = self.worktree_root / "integration"
            if self._is_worktree_root(integration_dir):
                # 3. Verify execution fence before mutating authoritative integration branch
                self._verify_execution_fence(task, context)
                logger.info("Merging task commit %s into integration worktree", commit_sha[:7])
                merge_msg = f"merge({self.job_id}): merge {task.task_id} ({commit_sha[:7]})"
                self.run_cmd(["git", "merge", "--no-ff", "-m", merge_msg, commit_sha], cwd=integration_dir)

            return commit_sha

    def _commit_worktree_changes(self, worktree_path: Path, task: TaskNode) -> List[str]:
        """Compatibility helper returning changed files committed."""
        changed = self.inspect_changed_files(worktree_path)
        self._commit_and_integrate_changes(worktree_path, task, role="builder")
        return changed

    def fetch_pending_mailbox_messages(self, agent_id: str) -> List[Dict[str, Any]]:
        """Mock/stub mailbox message fetching for runtime compatibility."""
        return []

    def build_mailbox_messages_section(self, current_agent: str, mailbox_messages: List[Dict[str, Any]]) -> str:
        if not mailbox_messages:
            return ""
        sections = [f"--- LYSSTACK OPERATIONAL MESSAGES FOR {str(current_agent).upper()} ---"]
        for msg in mailbox_messages:
            sender = msg.get("from", {}).get("id", "unknown") if isinstance(msg.get("from"), dict) else str(msg.get("from"))
            sections.append(f"[from: {sender}]\n{msg.get('text', '')}")
        sections.append("--- END OPERATIONAL MESSAGES ---")
        return "\n\n".join(sections)

    def build_continuity_section(
        self,
        task: TaskNode,
        observations: Optional[List[Any]] = None,
        failure_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Renders execution continuity context across retries, reroutes, and recoveries.
        Ensures model progress, discoveries, and failure lessons are preserved.
        """
        lines = []
        is_retry = task.attempt > 0
        has_reroute = bool(task.metadata and (task.metadata.get("previous_actor") or task.metadata.get("last_reroute_reason")))
        if is_retry or has_reroute or observations or failure_history:
            lines.append("--- LYSSTACK CONTINUITY CONTEXT ---")
            if has_reroute:
                prev = task.metadata.get("previous_actor", "previous agent")
                reason = task.metadata.get("last_reroute_reason", "capacity reroute")
                lines.append(f"[Reroute Notice] Execution rerouted from '{prev}'. Reason: {reason}")
            if is_retry and task.error:
                lines.append(f"[Previous Failure (Attempt {task.attempt})]\n{task.error}")
            if observations:
                lines.append("[Previous Attempt Discoveries & Observations]")
                for obs in observations:
                    content = obs.content if hasattr(obs, "content") else str(obs.get("content", obs) if isinstance(obs, dict) else obs)
                    kind = getattr(obs, "kind", obs.get("kind", "discovery") if isinstance(obs, dict) else "discovery")
                    lines.append(f"- [{kind}] {content}")
            if failure_history:
                lines.append("[Prior Run Telemetry]")
                for f in failure_history:
                    lines.append(f"- Run {f.get('run_id')}: status={f.get('status')}, exit_reason={f.get('exit_reason')}")
            lines.append("--- END CONTINUITY CONTEXT ---")
        return "\n\n".join(lines) if lines else ""

    def build_effective_prompt(
        self,
        base_prompt: str,
        current_agent: Optional[str] = None,
        mailbox_messages: Optional[List[Dict[str, Any]]] = None,
        role: Optional[str] = None,
        active_a2a_turn: Optional[Dict[str, Any]] = None,
        task: Optional[TaskNode] = None,
        observations: Optional[List[Any]] = None,
        failure_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Constructs the full effective prompt with persona, continuity, context, and operational instructions."""
        parts = []
        if current_agent and self.persona_enabled:
            try:
                from personas.persona import resolve_agent_profile
                profile = resolve_agent_profile(current_agent)
                if profile and profile.persona:
                    parts.append(profile.persona.render_prompt_section(agent_id=profile.id, role=role or "operative"))
            except Exception as e:
                logger.debug("Could not resolve persona for %s: %s", current_agent, e)

        if task:
            cont_sec = self.build_continuity_section(task, observations=observations, failure_history=failure_history)
            if cont_sec:
                parts.append(cont_sec)

        parts.append(base_prompt)
        if self.context_bundle:
            parts.append(self.context_bundle)

        if current_agent and mailbox_messages:
            mb_sec = self.build_mailbox_messages_section(current_agent, mailbox_messages)
            if mb_sec:
                parts.append(mb_sec)

        return "\n\n".join(parts)

    def build_tool_job_config(self, task: TaskNode) -> Dict[str, Any]:
        """
        Builds the job configuration handed to the ToolRegistry for policy derivation.

        There is no permissive default: when neither the task nor the spec declares a
        ToolPolicy, the config carries none and ToolPolicy.from_config leaves allowed_tools
        unset, which the registry rejects. Tool access is granted only by explicit policy.
        """
        job_cfg: Dict[str, Any] = dict(self.spec) if isinstance(self.spec, dict) else {}
        task_policy = task.metadata.get("tool_policy")
        if isinstance(task_policy, dict):
            job_cfg["tool_policy"] = task_policy
        return job_cfg

    def build_requester(
        self,
        task: TaskNode,
        run: AgentRun,
        actor_id: str,
        kind: str,
    ) -> Dict[str, Any]:
        """
        Stamps the authoritative requester identity onto a tool invocation.

        The identity is assigned by the runtime, never taken from agent output: an agent
        that emits an embedded tool request cannot choose who it claims to be, so capability
        and policy checks always run against the actor that actually made the request.
        """
        return {
            "id": actor_id,
            "kind": kind,
            "jobId": task.job_id,
            "taskId": task.task_id,
            "runId": run.run_id,
        }

    def _execute_tool_task(
        self,
        task: TaskNode,
        run: AgentRun,
        actor_id: str,
    ) -> TaskExecutionResult:
        """Blocking tool-actor dispatch; invoked off the event loop."""
        tool_id = actor_id if actor_id.startswith("tool.") else f"tool.{actor_id}"
        req_args = task.metadata.get("tool_args") or task.metadata.get("args") or {
            "task_id": task.task_id,
            "query": task.description,
        }
        # A tool-actor task is dispatched by the runtime itself on behalf of the job,
        # unless the spec records the agent that delegated it.
        requester_id = task.metadata.get("requested_by") or self.controller_id
        requester_kind = "agent" if task.metadata.get("requested_by") else "runtime"

        req = ToolInvocationRequest(
            toolId=tool_id,
            args=req_args,
            jobId=task.job_id,
            requester=self.build_requester(task, run, requester_id, requester_kind),
            timeoutSeconds=task.metadata.get("timeout_seconds", 60),
        )

        try:
            tool_res: ToolInvocationResult = self.tool_registry.execute(
                request=req,
                worktree_dir=self.target_repo,
                job_config=self.build_tool_job_config(task),
                job_id=task.job_id,
            )
            artifacts = list(tool_res.artifactRefs or [])
            status_str = "succeeded" if tool_res.status == "success" else "failed"
            return TaskExecutionResult(
                status=status_str,
                output=tool_res.output,
                error=tool_res.error,
                artifact_refs=artifacts,
                metadata={"tool": tool_id, "execution_type": "tool_actor", "requester": requester_id},
            )
        except Exception as e:
            logger.warning("Tool execution '%s' raised exception: %s", tool_id, e)
            return TaskExecutionResult(
                status="failed",
                error=str(e),
                exit_reason="tool_error",
                metadata={"tool": tool_id},
            )

    async def execute_task(
        self,
        task: TaskNode,
        run: AgentRun,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        """
        Executes a TaskNode via real tool invocation, simulated runner, or real agent backends.

        All blocking work (agent CLI processes, Git mutation, tool subprocesses) is dispatched
        to a worker thread so a running agent never stalls the reactive engine's event loop.
        """
        ctx = context or {}
        actor_id = run.actor_id or task.assigned_actor or "unknown"
        is_dry_run = ctx.get("dry_run", self.dry_run)
        is_skip = ctx.get("skip_agent_exec", self.skip_agent_exec)
        role = task.metadata.get("role") or "builder"

        # 1. Tool execution (e.g. tool.test_runner, tool.git.inspect, tool.read_file)
        if actor_id.startswith("tool.") or "tool" in task.required_capabilities:
            return await asyncio.to_thread(self._execute_tool_task, task, run, actor_id)

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

        # 3. Real Agent CLI / Backend Execution (blocking; dispatched off the event loop)
        try:
            return await asyncio.to_thread(self._execute_real_agent, task, run, actor_id, role, ctx)
        except Exception as exc:
            logger.exception("Error executing real task %s on actor %s: %s", task.task_id, actor_id, exc)
            return TaskExecutionResult(
                status="failed",
                error=str(exc),
                exit_reason="exception",
                metadata={"actor": actor_id},
            )

    def _execute_real_agent(
        self,
        task: TaskNode,
        run: AgentRun,
        actor_id: str,
        role: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        """
        Blocking real-agent execution path: worktree preparation, agent CLI invocation,
        syntax and role validation, commit, and integration merge.

        Runs on a worker thread. Git mutations inside are serialized by the per-repository
        lock; the agent process itself runs unlocked so concurrent tasks make real progress.
        """
        try:
            # Ensure authoritative integration worktree
            self.ensure_integration_worktree()

            from runner.agents.registry import default_registry
            from runner.backends.registry import default_backend_registry
            from runner.agents.base import AgentContext

            reg = self.agent_registry or default_registry
            backend_reg = self.backend_registry or default_backend_registry

            agent_adapter = reg.get(actor_id)
            backend_name = task.metadata.get("execution_backend") or task.metadata.get("backend") or "subprocess"
            backend = backend_reg.get(
                backend_name,
                run_dir=self.run_dir,
                sprint_id=task.job_id,
                logger=logger,
            )

            # Setup task worktree
            wt_name = task.metadata.get("worktree_dir") or task.task_id
            branch_name = task.metadata.get("branch") or f"task/{task.task_id}"
            worktree_path = self._ensure_worktree(self.worktree_root / wt_name, branch=branch_name, base_branch=self.target_branch)

            # Make dependent task start from latest integration HEAD
            self.sync_task_worktree_from_integration(worktree_path)

            # Prepare prompt
            base_prompt = task.description
            prompt_file = task.metadata.get("prompt_file")
            if prompt_file:
                p_path = Path(prompt_file)
                if not p_path.is_absolute():
                    p_path = (self.target_repo / p_path).resolve()
                if p_path.exists():
                    base_prompt = p_path.read_text(encoding="utf-8")

            # Gather task observations and prior failure telemetry for continuity
            prior_obs = []
            try:
                from runtime.observations import default_observation_registry
                prior_obs = default_observation_registry.list_for_task(task.task_id)
            except Exception:
                pass
            if not prior_obs and isinstance(task.metadata, dict) and task.metadata.get("observations"):
                prior_obs = task.metadata["observations"]

            prior_runs = (task.metadata or {}).get("prior_runs", [])

            effective_prompt = self.build_effective_prompt(
                base_prompt=base_prompt,
                current_agent=actor_id,
                role=role,
                task=task,
                observations=prior_obs,
                failure_history=prior_runs,
            )

            # Logs
            self.run_dir.mkdir(parents=True, exist_ok=True)
            stdout_file = self.run_dir / f"{task.task_id}_{actor_id}_stdout.log"
            stderr_file = self.run_dir / f"{task.task_id}_{actor_id}_stderr.log"

            agent_ctx = AgentContext(
                runner=self,
                phase={
                    "name": task.task_id,
                    "agent": actor_id,
                    "role": role,
                    "cmd_options": task.metadata.get("options", {}),
                },
                worktree=worktree_path,
                prompt=effective_prompt,
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

            # Check for embedded tool requests in stdout. The requester identity is
            # overwritten with the executing actor: an agent may ask for a tool, it may not
            # declare who is asking, and the job ToolPolicy applies to every such request.
            parsed_tool_reqs = parse_tool_requests(stdout_text) if parse_tool_requests else []
            tool_job_config = self.build_tool_job_config(task)
            for tr in parsed_tool_reqs:
                tr.requester = self.build_requester(task, run, actor_id, "agent")
                tr.jobId = task.job_id
                try:
                    self.tool_registry.execute(
                        tr,
                        worktree_dir=worktree_path,
                        job_config=tool_job_config,
                        job_id=task.job_id,
                    )
                except Exception as te:
                    logger.warning("Embedded tool request failed: %s", te)

            # Ingest usage and check context pressure
            runtime_meta = getattr(raw_res, "runtime_metadata", {}) or {}
            usage_snapshot = UsageSnapshotNormalizer.normalize(
                raw_data=runtime_meta,
                provider_id=default_capacity_registry.get_provider_for_actor(actor_id),
                actor_id=actor_id,
            )
            if usage_snapshot.tokens_used > 0 or usage_snapshot.source == "provider_reported":
                default_capacity_registry.record_snapshot(
                    usage_snapshot,
                    job_id=task.job_id,
                )

            # Check context pressure
            handoff_obs = None
            is_pressured, p_ratio = default_capacity_registry.check_context_pressure(actor_id)
            if not is_pressured and runtime_meta.get("context_pressure"):
                is_pressured = True
                p_ratio = runtime_meta.get("context_ratio", 0.9)

            if is_pressured:
                logger.warning("Context pressure detected for actor %s on task %s (ratio: %s); creating continuity handoff summary", actor_id, task.task_id, p_ratio)
                handoff_obs = Observation(
                    job_id=task.job_id,
                    task_id=task.task_id,
                    source=actor_id,
                    kind="continuity_handoff",
                    content=f"Context pressure handoff at {float(p_ratio or 0.9):.1%} context window. Key discoveries preserved. Fresh session required.",
                    metadata={"context_pressure": True, "fresh_session": True, "context_ratio": p_ratio},
                )
                try:
                    from runtime.observations import default_observation_registry
                    default_observation_registry.register(handoff_obs)
                except Exception:
                    pass

            # Validate python syntax
            self.validate_python_syntax(worktree_path)

            # Validate role constraints
            changed_files = self.inspect_changed_files(worktree_path)
            if role == "verifier" and changed_files:
                raise RuntimeError(f"Verifier task '{task.task_id}' modified {len(changed_files)} files; verifier role forbids mutations.")

            # Commit changes and merge into integration worktree with fence checks
            commit_sha = self._commit_and_integrate_changes(worktree_path, task, role, context)

            artifacts = []
            if commit_sha:
                artifacts.append({
                    "id": f"art_{task.task_id}_{run.run_id}",
                    "job_id": task.job_id,
                    "task_id": task.task_id,
                    "kind": "git_commit",
                    "title": f"Git commit for {task.task_id} ({commit_sha[:7]})",
                    "path": str(worktree_path),
                    "ref": commit_sha,
                    "files": changed_files,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

            obs = Observation(
                job_id=task.job_id,
                task_id=task.task_id,
                source=actor_id,
                kind="execution_output",
                content=f"Agent {actor_id} completed task {task.task_id} with exit code {exit_code}",
                metadata={"changed_files_count": len(changed_files), "commit_sha": commit_sha, "exit_code": exit_code},
            )

            obs_list = [obs]
            if handoff_obs is not None:
                obs_list.append(handoff_obs)

            status_str = "succeeded" if exit_code == 0 else "failed"
            return TaskExecutionResult(
                status=status_str,
                output={"stdout": stdout_text[:5000], "exit_code": exit_code, "commit_sha": commit_sha},
                error=stderr_text if exit_code != 0 else None,
                artifact_refs=artifacts,
                observations=obs_list,
                metadata={
                    "actor": actor_id,
                    "worktree": str(worktree_path),
                    "commit_sha": commit_sha,
                    "fresh_session_recommended": handoff_obs is not None,
                    "usage_snapshot": usage_snapshot.to_dict(),
                },
            )

        except WorktreeError as exc:
            # Fail closed: the task never ran against a valid, current tree.
            logger.error("Worktree failure for task %s on actor %s: %s", task.task_id, actor_id, exc)
            return TaskExecutionResult(
                status="failed",
                error=str(exc),
                exit_reason="worktree_error",
                metadata={"actor": actor_id, "fail_closed": True},
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
    directly against the real integration worktree (or target repository).
    """

    def __init__(
        self,
        verifier_id: str = "hermes.verifier",
        verification_steps: Optional[List[Dict[str, Any]]] = None,
        working_dir: Optional[Path] = None,
        worktree_root: Optional[Path] = None,
    ):
        self.verifier_id = verifier_id
        self.verification_steps = verification_steps or []
        self.working_dir = Path(working_dir).resolve() if working_dir else Path.cwd()
        self.worktree_root = Path(worktree_root).resolve() if worktree_root else (self.working_dir / ".worktrees")

    def _resolve_target_dir(self) -> Path:
        """Directs verification to the integration worktree if it exists."""
        candidates = [
            self.worktree_root / "integration",
            self.working_dir / "integration",
            self.working_dir / ".worktrees" / "integration",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return self.working_dir

    async def verify(
        self,
        job: JobRecord,
        graph: TaskGraph,
        artifacts: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Executes verification checks against the authoritative integration worktree.
        """
        target_dir = self._resolve_target_dir()
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

            step_cwd = target_dir
            if step.get("cwd"):
                rel_cwd = Path(step["cwd"])
                if not rel_cwd.is_absolute():
                    step_cwd = (target_dir / rel_cwd).resolve()

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
                logger.info("Verification check '%s' finished with rc=%s:\nSTDOUT:\n%s\nSTDERR:\n%s", check_name, proc.returncode, stdout_str, stderr_str)

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
                summary=f"All {len(checks_results)} verification checks passed successfully on {target_dir.name}",
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
