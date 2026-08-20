#!/usr/bin/env python3
"""
Hermes Sprint Runner
Controller script for managing multi-agent sprint workflows, worktrees, git operations,
agent execution, fail-fast validations, and automated test validation.

Governance Boundaries:
- Control root: Hermes repository containing runner, prompts, and reports.
- Target repo: configured Git repository being changed (must be clean).
- Worktrees: configured target-repository worktree root.
- Runs/Logs: configured Hermes runtime storage.
- Git operations are strictly controller-owned. Agents edit files only.
- Does NOT push to remote, merge to main, or access production resources.
"""

import sys
import json
import argparse
import subprocess
import py_compile
import logging
import os
from pathlib import Path, PureWindowsPath
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from agents.base import AgentContext
from agents.errors import SprintRunnerError
from agents.permissions import scoped_antigravity_permissions
from agents.registry import default_registry
from backends.registry import default_backend_registry


class HermesSprintRunner:
    PHASE_ROLES = {"builder", "hardener", "verifier"}
    DEFAULT_CONTEXT_MAX_BYTES = 256 * 1024

    def __init__(
        self,
        spec_path,
        dry_run=False,
        skip_agent_exec=False,
        verbose=False,
        agent_registry=None,
        backend_registry=None,
        backend_override=None,
        export_report=False,
    ):
        self.spec_path = Path(spec_path).resolve()
        self.dry_run = dry_run
        self.skip_agent_exec = skip_agent_exec
        self.verbose = verbose
        self.agent_registry = agent_registry or default_registry
        self.backend_registry = backend_registry or default_backend_registry
        self.backend_override = backend_override
        
        self.spec = self._load_spec()
        self.sprint_id = self.spec.get("sprint_id", "lab-s02")
        self.control_root = self._resolve_config_path(
            self.spec.get("control_root"),
            default=SCRIPT_DIR.parent,
        )
        self.target_repo = self._resolve_config_path(
            self.spec.get("target_repo") or self.spec.get("canonical_repo"),
            default=self.control_root,
        )
        default_storage_root = self.control_root.parent
        self.worktree_root = self._resolve_config_path(
            self.spec.get("worktree_root"),
            default=default_storage_root / "hermes-worktrees" / self.sprint_id,
        )
        self.runs_root = self._resolve_config_path(
            self.spec.get("runs_root"),
            default=default_storage_root / "hermes-runs",
        )
        self.limits = self.spec.get("limits", {"max_changed_files": 15, "timeout_seconds": 300})
        self.context_root = None
        self.context_files = []
        self.context_bundle = ""
        self.context_bytes = 0
        self._load_context_bundle()
        self.verification_steps = self._load_verification_spec()
        self._validate_phase_roles()
        if export_report is True:
            self.report_path = (
                self.control_root / "reports" / self.sprint_id / "run-summary.json"
            )
        elif export_report:
            self.report_path = Path(export_report).resolve()
        else:
            self.report_path = None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = self.runs_root / f"{timestamp}_{self.sprint_id}"
        self.log_file = self.run_dir / "runner.log"
        self.summary_file = self.run_dir / "run_summary.json"
        self._backend_cache = {}
        
        self.logger = self._setup_logging()
        self.run_summary = {
            "sprint_id": self.sprint_id,
            "start_time": datetime.now().isoformat(),
            "status": "INITIALIZING",
            "phases": [],
            "test_results": None,
            "verification_status": None,
            "verification_results": [],
            "integration_commit": None,
            "errors": []
        }
        if self.context_files:
            self.run_summary["context"] = {
                "files_count": len(self.context_files),
                "bytes": self.context_bytes,
            }

    def _load_spec(self):
        if not self.spec_path.exists():
            raise FileNotFoundError(f"Sprint specification file not found: {self.spec_path}")
        with open(self.spec_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _resolve_config_path(self, value, *, default):
        """Resolve configured paths relative to the sprint specification directory."""
        path = Path(value) if value is not None else Path(default)
        if not path.is_absolute():
            path = self.spec_path.parent / path
        return path.resolve()

    def resolve_prompt_file(self, phase):
        prompt_file = Path(phase["prompt_file"])
        if not prompt_file.is_absolute():
            prompt_file = self.control_root / prompt_file
        return prompt_file.resolve()

    def _load_context_bundle(self):
        if "context" not in self.spec:
            return
        context = self.spec["context"]
        if not isinstance(context, dict):
            self._invalid_context("'context' must be a JSON object")

        root_value = context.get("root")
        if not isinstance(root_value, str) or not root_value.strip():
            self._invalid_context("context.root must be a non-empty path string")
        root_path = Path(root_value)
        if not root_path.is_absolute():
            if PureWindowsPath(root_value).anchor:
                self._invalid_context(
                    "context.root must use a path native to the current platform"
                )
            root_path = self.spec_path.parent / root_path
        root_path = root_path.resolve()
        if not root_path.is_dir():
            self._invalid_context(
                f"context.root does not exist or is not a directory: {root_value}"
            )

        files = context.get("files")
        if (
            not isinstance(files, list)
            or not files
            or any(not isinstance(item, str) or not item.strip() for item in files)
        ):
            self._invalid_context(
                "context.files must be a non-empty array of non-empty strings"
            )

        max_bytes = context.get("max_bytes", self.DEFAULT_CONTEXT_MAX_BYTES)
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes <= 0
        ):
            self._invalid_context("context.max_bytes must be a positive integer")

        loaded_files = []
        seen_paths = set()
        total_bytes = 0
        for file_value in files:
            native_path = Path(file_value)
            windows_path = PureWindowsPath(file_value)
            if (
                native_path.is_absolute()
                or windows_path.anchor
                or ".." in windows_path.parts
            ):
                self._invalid_context(
                    f"context file must be relative and contained: {file_value}"
                )

            resolved_path = (root_path / native_path).resolve()
            try:
                resolved_path.relative_to(root_path)
            except ValueError as error:
                raise SprintRunnerError(
                    "FAILED_INVALID_CONTEXT_SPEC",
                    f"Context file escapes context.root: {file_value}",
                ) from error
            if resolved_path in seen_paths:
                self._invalid_context(
                    f"duplicate normalized context file: {file_value}"
                )
            seen_paths.add(resolved_path)

            if not resolved_path.exists():
                raise SprintRunnerError(
                    "FAILED_CONTEXT_FILE_MISSING",
                    f"Context file does not exist: {file_value}",
                )
            if not resolved_path.is_file():
                raise SprintRunnerError(
                    "FAILED_CONTEXT_FILE_INVALID",
                    f"Context entry is not a regular file: {file_value}",
                )
            try:
                content = resolved_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise SprintRunnerError(
                    "FAILED_CONTEXT_READ",
                    f"Unable to read UTF-8 context file: {file_value}",
                ) from error

            total_bytes += len(content.encode("utf-8"))
            if total_bytes > max_bytes:
                raise SprintRunnerError(
                    "FAILED_CONTEXT_TOO_LARGE",
                    f"Context bundle exceeds max_bytes while loading: {file_value}",
                )
            logical_name = resolved_path.relative_to(root_path).as_posix()
            loaded_files.append((logical_name, content))

        sections = ["--- HERMES CONTEXT BUNDLE ---"]
        for logical_name, content in loaded_files:
            sections.append(f"[context: {logical_name}]\n{content}")
        sections.append("--- END HERMES CONTEXT BUNDLE ---")

        self.context_root = root_path
        self.context_files = loaded_files
        self.context_bytes = total_bytes
        self.context_bundle = "\n\n".join(sections)

    @staticmethod
    def _invalid_context(message):
        raise SprintRunnerError("FAILED_INVALID_CONTEXT_SPEC", message)

    def build_effective_prompt(self, base_prompt):
        if not self.context_bundle:
            return base_prompt
        return f"{base_prompt}\n\n{self.context_bundle}"

    def _load_verification_spec(self):
        verification = self.spec.get("verification", [])
        if not isinstance(verification, list):
            self._invalid_verification("'verification' must be a JSON array")

        names = set()
        normalized = []
        integration_dir = self.worktree_root / "integration"
        for index, raw_step in enumerate(verification, start=1):
            if not isinstance(raw_step, dict):
                self._invalid_verification(
                    f"verification step {index} must be a JSON object"
                )

            name = raw_step.get("name")
            if not isinstance(name, str) or not name.strip():
                self._invalid_verification(
                    f"verification step {index} requires a non-empty name"
                )
            if name in names:
                self._invalid_verification(
                    f"duplicate verification step name: {name}"
                )
            names.add(name)

            command = raw_step.get("command")
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(argument, str) for argument in command)
            ):
                self._invalid_verification(
                    f"verification step '{name}' command must be a non-empty array of strings"
                )

            cwd = raw_step.get("cwd", ".")
            if not isinstance(cwd, str) or not cwd.strip():
                self._invalid_verification(
                    f"verification step '{name}' cwd must be a non-empty relative path"
                )
            if Path(cwd).is_absolute() or PureWindowsPath(cwd).anchor:
                self._invalid_verification(
                    f"verification step '{name}' cwd must be relative to the integration worktree"
                )

            timeout = raw_step.get(
                "timeout_seconds",
                self.limits.get("timeout_seconds", 300),
            )
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or timeout <= 0
            ):
                self._invalid_verification(
                    f"verification step '{name}' timeout_seconds must be positive"
                )

            step = {
                "name": name,
                "command": list(command),
                "cwd": cwd,
                "timeout_seconds": timeout,
            }
            self._resolve_verification_cwd(step, integration_dir)
            normalized.append(step)
        return normalized

    def _validate_phase_roles(self):
        for phase in self.spec.get("phases", []):
            self.resolve_phase_role(phase)

    def resolve_phase_role(self, phase):
        if "role" not in phase:
            return "legacy"
        role = phase["role"]
        if not isinstance(role, str) or role not in self.PHASE_ROLES:
            raise SprintRunnerError(
                "FAILED_UNKNOWN_ROLE",
                f"Unknown phase role: {role}",
            )
        return role

    @staticmethod
    def _invalid_verification(message):
        raise SprintRunnerError("FAILED_INVALID_VERIFICATION_SPEC", message)

    def _resolve_verification_cwd(self, step, integration_dir):
        integration_dir = integration_dir.resolve()
        candidate = (integration_dir / step["cwd"]).resolve()
        try:
            candidate.relative_to(integration_dir)
        except ValueError:
            self._invalid_verification(
                f"verification step '{step['name']}' cwd escapes the integration worktree"
            )
        return candidate

    def _setup_logging(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"HermesSprintRunner.{id(self)}")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        logger.propagate = False
        
        file_handler = logging.FileHandler(self.log_file)
        console_handler = logging.StreamHandler(sys.stdout)
        
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger

    def run_cmd(self, cmd, cwd=None, timeout=None, check=True):
        cwd = cwd or self.target_repo
        timeout = timeout or self.limits.get("timeout_seconds", 300)
        self.logger.debug(f"Executing command: {' '.join(cmd) if isinstance(cmd, list) else cmd} (cwd: {cwd})")
        
        if self.dry_run and any(k in cmd for k in ["commit", "merge", "push", "add", "reset"]):
            self.logger.info(f"[DRY-RUN] Would run: {cmd}")
            return subprocess.CompletedProcess(cmd, 0, stdout="[dry-run]", stderr="")

        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if check and res.returncode != 0:
                if "Permission denied" in res.stderr or "permission denied" in res.stderr:
                    raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Permission denied during command: {cmd}\n{res.stderr}")
                raise SprintRunnerError("FAILED_COMMAND_EXECUTION", f"Command failed: {cmd}\nExit Code: {res.returncode}\nStderr: {res.stderr}")
            return res
        except subprocess.TimeoutExpired:
            raise SprintRunnerError("FAILED_TIMEOUT", f"Command timed out after {timeout} seconds: {cmd}")

    def prepare_environment(self):
        self.logger.info("=== Preparing Sprint Worktree Environment ===")
        if not self.target_repo.exists():
            raise SprintRunnerError(
                "FAILED_TARGET_REPO_MISSING",
                f"Target repo does not exist at {self.target_repo}",
            )
        if not self.target_repo.is_dir():
            raise SprintRunnerError(
                "FAILED_TARGET_REPO_NOT_GIT",
                f"Target repo is not a Git working tree: {self.target_repo}",
            )

        repository_check = self.run_cmd(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.target_repo,
            check=False,
        )
        if (
            repository_check.returncode != 0
            or repository_check.stdout.strip() != "true"
        ):
            raise SprintRunnerError(
                "FAILED_TARGET_REPO_NOT_GIT",
                f"Target repo is not a Git working tree: {self.target_repo}",
            )

        # Target repository safety: MUST fail if dirty.
        res = self.run_cmd(["git", "status", "--porcelain"], cwd=self.target_repo)
        if res.stdout.strip():
            raise SprintRunnerError(
                "FAILED_DIRTY_REPO",
                f"Target repo at {self.target_repo} has uncommitted changes:\n{res.stdout.strip()}"
            )

        self.worktree_root.mkdir(parents=True, exist_ok=True)
        base_ref = self.spec.get("base_ref") or self.spec.get("base_branch", "main")
        target_branch = self.spec.get("target_branch", "s02/integration")

        # 1. Setup integration worktree
        integration_dir = self.worktree_root / "integration"
        self._ensure_worktree(integration_dir, target_branch, base_ref)

        # 2. Setup agent worktrees
        for phase in self.spec.get("phases", []):
            self.agent_registry.get(phase["agent"])
            self._get_backend(self.resolve_backend_name(phase))
            wt_dir = self.worktree_root / phase["worktree_dir"]
            branch = phase["branch"]
            self._ensure_worktree(wt_dir, branch, target_branch)

    def _ensure_worktree(self, path, branch, base_branch):
        if path.exists():
            self.logger.info(f"Validating existing worktree at {path} (expected branch: {branch})")
            # 1. Check if inside worktree
            res_wt = self.run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
            if res_wt.returncode != 0 or res_wt.stdout.strip() != "true":
                raise SprintRunnerError("FAILED_INVALID_WORKTREE", f"Directory {path} exists but is not a valid Git worktree.")
            
            # 2. Check current branch
            res_branch = self.run_cmd(["git", "branch", "--show-current"], cwd=path, check=False)
            curr_branch = res_branch.stdout.strip()
            if curr_branch != branch:
                raise SprintRunnerError("FAILED_WRONG_BRANCH", f"Worktree at {path} is on branch '{curr_branch}', expected '{branch}'.")

            # 3. Check clean status
            res_status = self.run_cmd(["git", "status", "--porcelain"], cwd=path, check=False)
            if res_status.stdout.strip():
                raise SprintRunnerError("FAILED_DIRTY_WORKTREE", f"Worktree at {path} has uncommitted changes:\n{res_status.stdout.strip()}")
        else:
            self.logger.info(f"Creating worktree at {path} for branch {branch} (from {base_branch})")
            res = self.run_cmd(["git", "branch", "--list", branch], cwd=self.target_repo)
            if res.stdout.strip():
                self.run_cmd(["git", "worktree", "add", str(path), branch], cwd=self.target_repo)
            else:
                self.run_cmd(["git", "worktree", "add", "-b", branch, str(path), base_branch], cwd=self.target_repo)

        # Clean, correctly assigned sprint branches are controller-owned and may
        # contain commits from an earlier run. Resetting them makes reruns start
        # from the configured state while dirty worktrees still fail above.
        self.logger.info(
            "Resetting worktree %s (%s) to configured start %s",
            path.name,
            branch,
            base_branch,
        )
        self.run_cmd(["git", "reset", "--hard", base_branch], cwd=path)

    def sync_phase_worktree(self, worktree, target_branch):
        self.logger.info(
            "Synchronizing phase worktree (%s) to latest %s",
            worktree.name,
            target_branch,
        )
        self.run_cmd(["git", "fetch", ".", target_branch], cwd=worktree)
        self.run_cmd(["git", "reset", "--hard", target_branch], cwd=worktree)

    # Compatibility helpers retained for callers that validated output through the runner.
    def parse_antigravity_stream_json(self, stdout_text, stderr_text=""):
        from agents.antigravity import AntigravityAdapter

        return AntigravityAdapter.parse_stream_json(stdout_text, stderr_text)

    def parse_claude_json(self, stdout_text, stderr_text=""):
        from agents.claude import ClaudeAdapter

        return ClaudeAdapter.parse_json(stdout_text, stderr_text)

    def resolve_backend_name(self, phase):
        return (
            phase.get("execution_backend")
            or self.backend_override
            or self.spec.get("execution_backend")
            or "subprocess"
        )

    def _get_backend(self, backend_name):
        if backend_name not in self._backend_cache:
            self._backend_cache[backend_name] = self.backend_registry.get(
                backend_name,
                run_dir=self.run_dir,
                sprint_id=self.sprint_id,
                logger=self.logger,
                keep_workspace=self.spec.get("keep_herdr_workspace", True),
            )
        return self._backend_cache[backend_name]

    def execute_agent(self, phase, wt_dir):
        agent_name = phase["agent"]
        adapter = self.agent_registry.get(agent_name)
        backend = self._get_backend(self.resolve_backend_name(phase))
        prompt_file = self.resolve_prompt_file(phase)
        context = AgentContext(
            runner=self,
            phase=phase,
            worktree=wt_dir,
            prompt=self.build_effective_prompt(
                prompt_file.read_text(encoding="utf-8").strip()
            ),
            options=phase.get("cmd_options", {}),
            stdout_file=self.run_dir / f"{phase['name']}_{agent_name}_stdout.log",
            stderr_file=self.run_dir / f"{phase['name']}_{agent_name}_stderr.log",
            timeout_seconds=self.limits.get("timeout_seconds", 300),
            backend=backend,
        )
        return adapter.execute(context)

    def inspect_changed_files(self, worktree_path):
        """Return target source changes without imposing role semantics."""
        res = self.run_cmd(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=worktree_path,
        )
        lines = [line for line in res.stdout.strip().split("\n") if line.strip()]
        self.logger.info("Changed target files count in %s: %s", worktree_path.name, len(lines))
        return lines

    def validate_changed_files(self, worktree_path):
        """Legacy required-change validation retained for compatibility callers."""
        lines = self.inspect_changed_files(worktree_path)
        max_limit = self.limits.get("max_changed_files", 15)
        if len(lines) == 0:
            raise SprintRunnerError(
                "FAILED_NO_CHANGES",
                f"Worktree {worktree_path.name} produced NO file changes."
            )
        if len(lines) > max_limit:
            raise SprintRunnerError(
                "FAILED_EXCESSIVE_FILES",
                f"Worktree {worktree_path.name} changed {len(lines)} files, exceeding limit of {max_limit}."
            )
        return lines

    def validate_handoff_file(self, worktree_path, expected_handoff):
        worktree_path = worktree_path.resolve()
        handoff_path = (worktree_path / expected_handoff).resolve()
        try:
            handoff_path.relative_to(worktree_path)
        except ValueError as error:
            raise SprintRunnerError(
                "FAILED_INVALID_HANDOFF",
                f"Handoff path escapes worktree: {expected_handoff}",
            ) from error
        self.logger.info(f"Checking expected handoff file: {handoff_path}")
        if not handoff_path.is_file() or handoff_path.stat().st_size == 0:
            raise SprintRunnerError(
                "FAILED_MISSING_HANDOFF",
                f"Required handoff file '{expected_handoff}' is missing or empty in {worktree_path}."
            )
        return handoff_path

    @staticmethod
    def _safe_filename_component(value):
        return "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in value
        ) or "unknown"

    def capture_handoff(
        self,
        phase_index,
        role,
        agent,
        worktree_path,
        expected_handoff,
    ):
        handoff_path = self.validate_handoff_file(worktree_path, expected_handoff)
        destination = self.run_dir / "handoffs" / (
            f"{phase_index:02d}_{self._safe_filename_component(role)}_"
            f"{self._safe_filename_component(agent)}.md"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            handoff_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return handoff_path

    def _prepare_handoff_path(self, worktree_path, expected_handoff):
        worktree_path = worktree_path.resolve()
        handoff_path = (worktree_path / expected_handoff).resolve()
        try:
            handoff_path.relative_to(worktree_path)
        except ValueError as error:
            raise SprintRunnerError(
                "FAILED_INVALID_HANDOFF",
                f"Handoff path escapes worktree: {expected_handoff}",
            ) from error
        original_content = handoff_path.read_bytes() if handoff_path.is_file() else None
        if handoff_path.exists() and not handoff_path.is_file():
            raise SprintRunnerError(
                "FAILED_INVALID_HANDOFF",
                f"Handoff path is not a file: {expected_handoff}",
            )
        if handoff_path.is_file():
            handoff_path.unlink()
        return handoff_path, original_content

    @staticmethod
    def _restore_handoff_path(handoff_path, original_content):
        if original_content is None:
            if handoff_path.exists():
                handoff_path.unlink()
            return
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_bytes(original_content)

    def validate_python_syntax(self, worktree_path):
        self.logger.info(f"Validating Python syntax in {worktree_path}")
        py_files = list(worktree_path.rglob("*.py"))
        for py_file in py_files:
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                raise SprintRunnerError(
                    "FAILED_SYNTAX_ERROR",
                    f"Python syntax error in {py_file.name}: {e}"
                )

    def execute_phase(self, phase, phase_index=1):
        phase_name = phase["name"]
        agent = phase["agent"]
        role = self.resolve_phase_role(phase)
        wt_dir = self.worktree_root / phase["worktree_dir"]
        prompt_file = self.resolve_prompt_file(phase)
        expected_handoff = phase["expected_handoff"]
        commit_msg = phase["commit_message"]

        self.logger.info(f"\n=== Executing Phase: {phase_name} (Agent: {agent}) ===")
        backend_name = self.resolve_backend_name(phase)
        self._get_backend(backend_name)

        if not prompt_file.exists():
            raise SprintRunnerError("FAILED_MISSING_PROMPT", f"Prompt file not found: {prompt_file}")

        # Every phase after the first starts from the latest integration state.
        if self.run_summary["phases"]:
            target_branch = self.spec.get("target_branch", "s02/integration")
            self.sync_phase_worktree(wt_dir, target_branch)

        handoff_path, original_handoff = self._prepare_handoff_path(
            wt_dir,
            expected_handoff,
        )
        try:
            if not self.skip_agent_exec and not self.dry_run:
                execution_result = self.execute_agent(phase, wt_dir)
            else:
                execution_result = None
                self.logger.info(f"Skipping agent execution CLI (skip_agent_exec={self.skip_agent_exec}, dry_run={self.dry_run})")

            self.capture_handoff(
                phase_index,
                role,
                agent,
                wt_dir,
                expected_handoff,
            )
        finally:
            self._restore_handoff_path(handoff_path, original_handoff)

        changed_files = self.inspect_changed_files(wt_dir)
        max_limit = self.limits.get("max_changed_files", 15)
        if role == "verifier" and changed_files:
            raise SprintRunnerError(
                "FAILED_FORBIDDEN_CHANGES",
                f"Verifier phase '{phase_name}' modified {len(changed_files)} target files.",
            )
        if role != "verifier" and len(changed_files) > max_limit:
            raise SprintRunnerError(
                "FAILED_EXCESSIVE_FILES",
                f"Worktree {wt_dir.name} changed {len(changed_files)} files, exceeding limit of {max_limit}.",
            )
        if role in {"builder", "legacy"} and not changed_files:
            raise SprintRunnerError(
                "FAILED_NO_CHANGES",
                f"Worktree {wt_dir.name} produced NO file changes.",
            )

        self.validate_python_syntax(wt_dir)

        should_integrate = bool(changed_files) and role != "verifier"
        commit_sha = None
        if should_integrate:
            self.logger.info(f"Controller staging changes in {wt_dir.name}")
            self.run_cmd(["git", "add", "."], cwd=wt_dir)
            self.run_cmd(["git", "commit", "-m", commit_msg], cwd=wt_dir)

            sha_res = self.run_cmd(["git", "rev-parse", "HEAD"], cwd=wt_dir)
            commit_sha = sha_res.stdout.strip()
            self.logger.info(f"Committed phase changes: {commit_sha[:7]} - {commit_msg}")

            integration_dir = self.worktree_root / "integration"
            self.logger.info(f"Controller merging commit {commit_sha[:7]} into integration worktree")
            self.run_cmd(["git", "merge", "--no-ff", "-m", f"merge({self.sprint_id}): merge {agent} phase ({commit_sha[:7]})", commit_sha], cwd=integration_dir)

        phase_result = {
            "phase": phase_name,
            "role": role,
            "agent": agent,
            "backend": backend_name,
            "status": "SUCCESS",
            "commit_sha": commit_sha,
            "changed_files_count": len(changed_files),
            "integrated": should_integrate,
            "handoff": "captured",
            "runtime_metadata": (
                dict(execution_result.runtime_metadata) if execution_result else {}
            ),
        }
        self.run_summary["phases"].append(phase_result)

    def run_tests_in_venv(self):
        self.logger.info("\n=== Running Controller Verification & Pytest Suite ===")
        integration_dir = self.worktree_root / "integration"
        venv_dir = self.run_dir / "venv"

        self.logger.info(f"Creating isolated Python virtual environment at {venv_dir}")
        self.run_cmd([sys.executable, "-m", "venv", str(venv_dir)])

        venv_python = self._venv_python(venv_dir)

        req_file = integration_dir / "requirements.txt"
        if req_file.exists():
            self.logger.info(f"Installing dependencies from {req_file}")
            self.run_cmd(
                [str(venv_python), "-m", "pip", "install", "--no-cache-dir", "-r", str(req_file)],
                cwd=integration_dir,
            )

        self.logger.info("Executing pytest suite...")
        try:
            test_res = self.run_cmd([str(venv_python), "-m", "pytest", "-v"], cwd=integration_dir)
            self.logger.info("Pytest suite passed successfully!")
            self.run_summary["test_results"] = {
                "status": "PASSED",
                "output": test_res.stdout
            }
        except SprintRunnerError as e:
            self.logger.error("Pytest suite execution failed!")
            self.run_summary["test_results"] = {
                "status": "FAILED",
                "error": str(e)
            }
            raise SprintRunnerError("FAILED_TESTS", f"Pytest suite failed in integration worktree: {e}")

    def run_verification(self):
        """Run spec-defined final verification sequentially without a shell."""
        self.logger.info("\n=== Running Generic Verification Pipeline ===")
        integration_dir = self.worktree_root / "integration"
        self.run_summary["verification_status"] = "RUNNING"

        for index, step in enumerate(self.verification_steps, start=1):
            name = step["name"]
            cwd = self._resolve_verification_cwd(step, integration_dir)
            result_record = {"name": name, "status": "FAILED"}
            safe_name = "".join(
                character if character.isalnum() or character in "-_" else "_"
                for character in name
            ) or "step"
            stdout_file = self.run_dir / (
                f"verification_{index:02d}_{safe_name}_stdout.log"
            )
            stderr_file = self.run_dir / (
                f"verification_{index:02d}_{safe_name}_stderr.log"
            )

            if not cwd.is_dir():
                self.run_summary["verification_results"].append(result_record)
                self.run_summary["verification_status"] = "FAILED"
                self._invalid_verification(
                    f"verification step '{name}' cwd does not exist or is not a directory"
                )

            self.logger.info("Running verification step %s: %s", index, name)
            try:
                result = self.run_cmd(
                    step["command"],
                    cwd=cwd,
                    timeout=step["timeout_seconds"],
                    check=False,
                )
            except (OSError, SprintRunnerError) as error:
                stdout_file.write_text("", encoding="utf-8")
                stderr_file.write_text(str(error), encoding="utf-8")
                self.run_summary["verification_results"].append(result_record)
                self.run_summary["verification_status"] = "FAILED"
                raise SprintRunnerError(
                    "FAILED_VERIFICATION",
                    f"Verification step '{name}' could not complete: {error}",
                ) from error

            stdout_file.write_text(result.stdout or "", encoding="utf-8")
            stderr_file.write_text(result.stderr or "", encoding="utf-8")
            if result.returncode != 0:
                self.run_summary["verification_results"].append(result_record)
                self.run_summary["verification_status"] = "FAILED"
                raise SprintRunnerError(
                    "FAILED_VERIFICATION",
                    f"Verification step '{name}' failed with exit code {result.returncode}",
                )

            result_record["status"] = "PASSED"
            self.run_summary["verification_results"].append(result_record)

        self.run_summary["verification_status"] = "PASSED"

    @staticmethod
    def _venv_python(venv_dir, platform_name=None):
        platform_name = platform_name or os.name
        if platform_name == "nt":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def finalize(self):
        # Validate that all phases succeeded and pytest passed before granting READY_FOR_REVIEW
        for p in self.run_summary["phases"]:
            if p["status"] != "SUCCESS":
                raise SprintRunnerError(
                    "FAILED_INCOMPLETE_PHASE",
                    f"Phase '{p['phase']}' did not reach SUCCESS status (was {p['status']})."
                )

        if self.verification_steps:
            if self.run_summary.get("verification_status") != "PASSED":
                raise SprintRunnerError(
                    "FAILED_VERIFICATION",
                    "Generic verification failed or did not run.",
                )
        elif not self.run_summary.get("test_results") or self.run_summary["test_results"].get("status") != "PASSED":
            raise SprintRunnerError(
                "FAILED_TESTS",
                "Pytest validation failed or did not run."
            )

        integration_dir = self.worktree_root / "integration"
        sha_res = self.run_cmd(["git", "rev-parse", "HEAD"], cwd=integration_dir)
        self.run_summary["integration_commit"] = sha_res.stdout.strip()
        self.run_summary["status"] = "READY_FOR_REVIEW"
        self.run_summary["end_time"] = datetime.now().isoformat()
        
        self.logger.info("\n==========================================")
        self.logger.info(f"Sprint {self.sprint_id} Workflow Complete!")
        self.logger.info(f"Final Status: READY_FOR_REVIEW")
        self.logger.info(f"Integration Commit: {self.run_summary['integration_commit']}")
        self.logger.info("==========================================\n")

    def export_sanitized_report(self, report_path=None):
        """Write deterministic run evidence without prompts, logs, or errors."""
        destination_value = report_path or self.report_path
        if destination_value is None:
            raise ValueError("A report path is required for sanitized export")
        destination = Path(destination_value).resolve()
        test_results = self.run_summary.get("test_results") or {}
        sanitized = {
            "sprint_id": self.sprint_id,
            "status": self.run_summary.get("status"),
            "phases": [
                {
                    "phase": phase.get("phase"),
                    "agent": phase.get("agent"),
                    "status": phase.get("status"),
                    "changed_files_count": phase.get("changed_files_count"),
                    **(
                        {"role": phase.get("role")}
                        if phase.get("role")
                        else {}
                    ),
                    **(
                        {"integrated": phase.get("integrated")}
                        if "integrated" in phase
                        else {}
                    ),
                    **(
                        {"handoff": phase.get("handoff")}
                        if phase.get("handoff")
                        else {}
                    ),
                    **(
                        {"backend": phase.get("backend")}
                        if phase.get("backend")
                        else {}
                    ),
                }
                for phase in self.run_summary.get("phases", [])
            ],
            "test_status": test_results.get("status"),
            "integration_commit": self.run_summary.get("integration_commit"),
        }
        if self.verification_steps:
            sanitized["verification_status"] = self.run_summary.get(
                "verification_status"
            )
            sanitized["verification"] = [
                {
                    "name": result.get("name"),
                    "status": result.get("status"),
                }
                for result in self.run_summary.get("verification_results", [])
            ]
        if self.context_files:
            sanitized["context"] = {
                "files_count": len(self.context_files),
                "bytes": self.context_bytes,
            }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(sanitized, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.logger.info("Sanitized run report written to %s", destination)
        return destination

    def execute(self):
        try:
            self.prepare_environment()
            for phase_index, phase in enumerate(self.spec.get("phases", []), start=1):
                self.execute_phase(phase, phase_index=phase_index)
            if self.verification_steps:
                self.run_verification()
            else:
                self.run_tests_in_venv()
            self.finalize()
        except SprintRunnerError as e:
            self.run_summary["status"] = e.code
            self.run_summary["end_time"] = datetime.now().isoformat()
            self.run_summary["errors"].append({"code": e.code, "message": e.message})
            self.logger.error(f"FAIL-FAST TRIGGERED: [{e.code}] {e.message}")
        finally:
            sprint_succeeded = self.run_summary["status"] == "READY_FOR_REVIEW"
            for backend in self._backend_cache.values():
                try:
                    backend.cleanup(success=sprint_succeeded)
                except SprintRunnerError as cleanup_error:
                    self.logger.error(
                        "Backend cleanup failed: [%s] %s",
                        cleanup_error.code,
                        cleanup_error.message,
                    )
            with open(self.summary_file, "w", encoding="utf-8") as f:
                json.dump(self.run_summary, f, indent=2)
            self.logger.info(f"Run summary written to {self.summary_file}")
            if self.report_path is not None:
                self.export_sanitized_report()

        return self.run_summary["status"] == "READY_FOR_REVIEW"


def main():
    parser = argparse.ArgumentParser(description="Hermes Sprint Workflow Runner")
    parser.add_argument("--spec", default="sprints/lab-s04.json", help="Path to sprint JSON specification")
    parser.add_argument("--dry-run", action="store_true", help="Simulate run without modifying git state")
    parser.add_argument("--skip-agent-execution", action="store_true", help="Skip invoking external agent CLI")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")
    parser.add_argument(
        "--backend",
        help="Globally override the sprint execution backend unless a phase overrides it",
    )
    parser.add_argument(
        "--export-report",
        nargs="?",
        const=True,
        default=False,
        metavar="PATH",
        help=(
            "Export sanitized evidence; defaults to "
            "reports/<sprint-id>/run-summary.json"
        ),
    )

    args = parser.parse_args()
    
    runner = HermesSprintRunner(
        spec_path=args.spec,
        dry_run=args.dry_run,
        skip_agent_exec=args.skip_agent_execution,
        verbose=args.verbose,
        backend_override=args.backend,
        export_report=args.export_report,
    )
    
    success = runner.execute()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
