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
from pathlib import Path
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
            "integration_commit": None,
            "errors": []
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
            prompt=prompt_file.read_text(encoding="utf-8").strip(),
            options=phase.get("cmd_options", {}),
            stdout_file=self.run_dir / f"{phase['name']}_{agent_name}_stdout.log",
            stderr_file=self.run_dir / f"{phase['name']}_{agent_name}_stderr.log",
            timeout_seconds=self.limits.get("timeout_seconds", 300),
            backend=backend,
        )
        return adapter.execute(context)

    def validate_changed_files(self, worktree_path):
        # Expand untracked directories so the limit counts files, not directory entries.
        res = self.run_cmd(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=worktree_path,
        )
        lines = [line for line in res.stdout.strip().split("\n") if line.strip()]
        max_limit = self.limits.get("max_changed_files", 15)
        
        self.logger.info(f"Changed files count in {worktree_path.name}: {len(lines)} (Limit: {max_limit})")
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
        handoff_path = worktree_path / expected_handoff
        self.logger.info(f"Checking expected handoff file: {handoff_path}")
        if not handoff_path.exists() or handoff_path.stat().st_size == 0:
            raise SprintRunnerError(
                "FAILED_MISSING_HANDOFF",
                f"Required handoff file '{expected_handoff}' is missing or empty in {worktree_path}."
            )

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

    def execute_phase(self, phase):
        phase_name = phase["name"]
        agent = phase["agent"]
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

        # Agent execution
        if not self.skip_agent_exec and not self.dry_run:
            execution_result = self.execute_agent(phase, wt_dir)
        else:
            execution_result = None
            self.logger.info(f"Skipping agent execution CLI (skip_agent_exec={self.skip_agent_exec}, dry_run={self.dry_run})")

        # Controller validation checks
        self.validate_python_syntax(wt_dir)
        changed_files = self.validate_changed_files(wt_dir)  # Fails fast on NO_CHANGES or EXCESSIVE_FILES
        self.validate_handoff_file(wt_dir, expected_handoff)

        # Controller stages and commits
        self.logger.info(f"Controller staging changes in {wt_dir.name}")
        self.run_cmd(["git", "add", "."], cwd=wt_dir)
        self.run_cmd(["git", "commit", "-m", commit_msg], cwd=wt_dir)
        
        sha_res = self.run_cmd(["git", "rev-parse", "HEAD"], cwd=wt_dir)
        commit_sha = sha_res.stdout.strip()
        self.logger.info(f"Committed phase changes: {commit_sha[:7]} - {commit_msg}")

        # Merge commit into integration worktree
        integration_dir = self.worktree_root / "integration"
        self.logger.info(f"Controller merging commit {commit_sha[:7]} into integration worktree")
        self.run_cmd(["git", "merge", "--no-ff", "-m", f"merge({self.sprint_id}): merge {agent} phase ({commit_sha[:7]})", commit_sha], cwd=integration_dir)

        phase_result = {
            "phase": phase_name,
            "agent": agent,
            "backend": backend_name,
            "status": "SUCCESS",
            "commit_sha": commit_sha,
            "changed_files_count": len(changed_files),
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

        if not self.run_summary.get("test_results") or self.run_summary["test_results"].get("status") != "PASSED":
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
            for phase in self.spec.get("phases", []):
                self.execute_phase(phase)
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
