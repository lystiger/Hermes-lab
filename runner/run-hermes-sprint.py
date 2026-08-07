#!/usr/bin/env python3
"""
Hermes Sprint Runner (Sprint 02)
Controller script for managing multi-agent sprint workflows, worktrees, git operations,
agent execution, fail-fast validations, and automated test validation.

Governance Boundaries:
- Canonical repo: ~/hermes-lab (must be clean)
- Worktrees: ~/hermes-worktrees/hermes-lab-s02/
- Runs/Logs: ~/hermes-runs/
- Git operations are strictly controller-owned. Agents edit files only.
- Does NOT push to remote, merge to main, or access production resources.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import py_compile
import logging
from pathlib import Path
from datetime import datetime


class SprintRunnerError(Exception):
    """Custom exception class for sprint runner fail-fast conditions."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class HermesSprintRunner:
    def __init__(self, spec_path, dry_run=False, skip_agent_exec=False, verbose=False):
        self.spec_path = Path(spec_path).resolve()
        self.dry_run = dry_run
        self.skip_agent_exec = skip_agent_exec
        self.verbose = verbose
        
        self.spec = self._load_spec()
        self.sprint_id = self.spec.get("sprint_id", "lab-s02")
        self.canonical_repo = Path(self.spec.get("canonical_repo", "/home/lystiger/hermes-lab")).resolve()
        self.worktree_root = Path(self.spec.get("worktree_root", f"/home/lystiger/hermes-worktrees/{self.sprint_id}")).resolve()
        self.runs_root = Path(self.spec.get("runs_root", "/home/lystiger/hermes-runs")).resolve()
        self.limits = self.spec.get("limits", {"max_changed_files": 15, "timeout_seconds": 300})
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = self.runs_root / f"{timestamp}_{self.sprint_id}"
        self.log_file = self.run_dir / "runner.log"
        self.summary_file = self.run_dir / "run_summary.json"
        
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

    def _setup_logging(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("HermesSprintRunner")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        file_handler = logging.FileHandler(self.log_file)
        console_handler = logging.StreamHandler(sys.stdout)
        
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger

    def run_cmd(self, cmd, cwd=None, timeout=None, check=True):
        cwd = cwd or self.canonical_repo
        timeout = timeout or self.limits.get("timeout_seconds", 300)
        self.logger.debug(f"Executing command: {' '.join(cmd) if isinstance(cmd, list) else cmd} (cwd: {cwd})")
        
        if self.dry_run and any(k in cmd for k in ["commit", "merge", "push", "add"]):
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
        if not self.canonical_repo.exists():
            raise SprintRunnerError("FAILED_CANONICAL_REPO_MISSING", f"Canonical repo does not exist at {self.canonical_repo}")

        # Canonical repo safety: MUST fail if dirty
        res = self.run_cmd(["git", "status", "--porcelain"], cwd=self.canonical_repo)
        if res.stdout.strip():
            raise SprintRunnerError(
                "FAILED_DIRTY_REPO",
                f"Canonical repo at {self.canonical_repo} has uncommitted changes:\n{res.stdout.strip()}"
            )

        self.worktree_root.mkdir(parents=True, exist_ok=True)
        base_branch = self.spec.get("base_branch", "main")
        target_branch = self.spec.get("target_branch", "s02/integration")

        # 1. Setup integration worktree
        integration_dir = self.worktree_root / "integration"
        self._ensure_worktree(integration_dir, target_branch, base_branch)

        # 2. Setup agent worktrees
        for phase in self.spec.get("phases", []):
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
            res = self.run_cmd(["git", "branch", "--list", branch], cwd=self.canonical_repo)
            if res.stdout.strip():
                self.run_cmd(["git", "worktree", "add", str(path), branch], cwd=self.canonical_repo)
            else:
                self.run_cmd(["git", "worktree", "add", "-b", branch, str(path), base_branch], cwd=self.canonical_repo)

    def sync_claude_worktree(self, claude_wt_dir, target_branch="s02/integration"):
        self.logger.info(f"Synchronizing Claude worktree ({claude_wt_dir.name}) to latest {target_branch}")
        self.run_cmd(["git", "fetch", ".", target_branch], cwd=claude_wt_dir)
        self.run_cmd(["git", "reset", "--hard", target_branch], cwd=claude_wt_dir)
        
        # Verify HANDOFF_AGY.md exists in claude worktree
        handoff_agy = claude_wt_dir / "HANDOFF_AGY.md"
        if not handoff_agy.exists():
            raise SprintRunnerError(
                "FAILED_PHASE_SYNC",
                f"Phase sync failed: HANDOFF_AGY.md not present in Claude worktree after reset to {target_branch}"
            )
        self.logger.info(f"Phase synchronization successful: Claude worktree updated to {target_branch} with HANDOFF_AGY.md")

    def parse_antigravity_stream_json(self, stdout_text, stderr_text=""):
        if "Permission denied" in stderr_text or "permission denied" in stderr_text:
            raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Antigravity permission denied in stderr:\n{stderr_text}")

        lines = stdout_text.strip().split("\n")
        for line_idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue

            try:
                event = json.loads(line_str)
            except json.JSONDecodeError:
                if "permission denied" in line_str.lower() or "eacces" in line_str.lower():
                    raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Antigravity permission error on line {line_idx+1}: {line_str}")
                continue

            if not isinstance(event, dict):
                continue

            # 1. Primary check: nested step_update.tool_info.error
            if event.get("event") == "step_update" or "step_update" in event:
                step_update = event.get("step_update")
                if isinstance(step_update, dict) and step_update.get("step_type") == "tool":
                    tool_info = step_update.get("tool_info")
                    if isinstance(tool_info, dict):
                        tool_err = tool_info.get("error")
                        if tool_err is not None and tool_err is not False and tool_err != "":
                            err_str = str(tool_err)
                            if "permission" in err_str.lower() or "denied" in err_str.lower() or "eacces" in err_str.lower():
                                raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Antigravity tool permission error: {err_str}")
                            raise SprintRunnerError("FAILED_ANTIGRAVITY_TOOL_ERROR", f"Antigravity tool error on line {line_idx+1}: {err_str}")

            # 2. Defensive top-level checks
            err = event.get("error")
            if err is not None and err is not False and err != "":
                err_msg = str(err)
                if "permission" in err_msg.lower() or "denied" in err_msg.lower():
                    raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Antigravity tool permission error: {err_msg}")
                raise SprintRunnerError("FAILED_ANTIGRAVITY_TOOL_ERROR", f"Antigravity tool error on line {line_idx+1}: {err_msg}")

            status = str(event.get("status", "")).upper()
            if status in ["ERROR", "FAILED"]:
                msg = event.get("message") or event.get("details") or line_str
                raise SprintRunnerError("FAILED_ANTIGRAVITY_TOOL_ERROR", f"Antigravity tool event status {status}: {msg}")

            if event.get("is_error") is True:
                msg = event.get("message") or line_str
                raise SprintRunnerError("FAILED_ANTIGRAVITY_TOOL_ERROR", f"Antigravity tool error event: {msg}")

            msg = str(event.get("message", ""))
            if "permission denied" in msg.lower() or "eacces" in msg.lower():
                raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Antigravity permission error in message: {msg}")

    def parse_claude_json(self, stdout_text, stderr_text=""):
        if "Permission denied" in stderr_text or "permission denied" in stderr_text:
            raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Claude permission denied in stderr:\n{stderr_text}")

        stdout_clean = stdout_text.strip()
        if not stdout_clean:
            raise SprintRunnerError("FAILED_CLAUDE_EMPTY_OUTPUT", "Claude emitted no output")

        data = None
        try:
            data = json.loads(stdout_clean)
        except json.JSONDecodeError:
            lines = [l.strip() for l in stdout_clean.split("\n") if l.strip()]
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if data is None or not isinstance(data, dict):
            raise SprintRunnerError("FAILED_CLAUDE_INVALID_JSON", f"Failed to parse JSON response from Claude: {stdout_clean[:200]}")

        # 1. Require type == "result"
        type_val = data.get("type")
        if type_val != "result":
            raise SprintRunnerError("FAILED_CLAUDE_ERROR", f"Claude output type is '{type_val}', expected 'result'")

        # 2. Require subtype == "success"
        subtype_val = data.get("subtype")
        if subtype_val == "max_turns_exceeded" or "max_turns" in str(subtype_val).lower():
            raise SprintRunnerError("FAILED_CLAUDE_MAX_TURNS", f"Claude reached maximum turn limit: {subtype_val}")
        if subtype_val != "success":
            raise SprintRunnerError("FAILED_CLAUDE_ERROR", f"Claude output subtype is '{subtype_val}', expected 'success'")

        # 3. Require is_error == False
        if data.get("is_error") is not False:
            err_msg = data.get("error") or data.get("message") or f"is_error is {data.get('is_error')}"
            raise SprintRunnerError("FAILED_CLAUDE_ERROR", f"Claude execution returned is_error={data.get('is_error')}: {err_msg}")

        # 4. Require permission_denials empty
        denials = data.get("permission_denials") or []
        if denials:
            raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Claude encountered permission denials: {denials}")

        # Note: Do NOT interpret data.get("result") as a status string. result is arbitrary model output.

    def execute_agent(self, phase, wt_dir):
        agent = phase["agent"]
        prompt_file = self.canonical_repo / phase["prompt_file"]
        cmd_opts = phase.get("cmd_options", {})
        timeout_sec = self.limits.get("timeout_seconds", 300)

        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_content = f.read().strip()

        stdout_file = self.run_dir / f"{phase['name']}_{agent}_stdout.log"
        stderr_file = self.run_dir / f"{phase['name']}_{agent}_stderr.log"

        if agent == "antigravity":
            cmd = ["agy", "-p", prompt_content, "--output-format", cmd_opts.get("output_format", "stream-json")]
            # Default for dangerously_skip_permissions is False
            if cmd_opts.get("dangerously_skip_permissions", False):
                cmd.append("--dangerously-skip-permissions")
        elif agent == "claude":
            cmd = [
                "claude", "-p", prompt_content,
                "--model", cmd_opts.get("model", "sonnet"),
                "--max-turns", str(cmd_opts.get("max_turns", 30)),
                "--permission-mode", cmd_opts.get("permission_mode", "dontAsk"),
                "--output-format", cmd_opts.get("output_format", "json")
            ]
        else:
            raise SprintRunnerError("FAILED_UNKNOWN_AGENT", f"Unknown agent type: {agent}")

        self.logger.info(f"Launching agent process: {cmd[0]} in worktree {wt_dir.name}")
        res = self.run_cmd(cmd, cwd=wt_dir, timeout=timeout_sec, check=False)

        with open(stdout_file, "w", encoding="utf-8") as f:
            f.write(res.stdout)
        with open(stderr_file, "w", encoding="utf-8") as f:
            f.write(res.stderr)

        self.logger.info(f"Agent {agent} process completed with exit code {res.returncode}")

        if res.returncode != 0:
            if "Permission denied" in res.stderr or "permission denied" in res.stderr:
                raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Agent {agent} permission denied:\n{res.stderr}")
            raise SprintRunnerError("FAILED_AGENT_EXECUTION", f"Agent {agent} exited with code {res.returncode}:\n{res.stderr}")

        # Fail-fast parsing
        if agent == "antigravity":
            self.parse_antigravity_stream_json(res.stdout, res.stderr)
        elif agent == "claude":
            self.parse_claude_json(res.stdout, res.stderr)

    def validate_changed_files(self, worktree_path):
        res = self.run_cmd(["git", "status", "--porcelain"], cwd=worktree_path)
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
        py_files = list(worktree_path.glob("*.py"))
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
        prompt_file = self.canonical_repo / phase["prompt_file"]
        expected_handoff = phase["expected_handoff"]
        commit_msg = phase["commit_message"]

        self.logger.info(f"\n=== Executing Phase: {phase_name} (Agent: {agent}) ===")

        if not prompt_file.exists():
            raise SprintRunnerError("FAILED_MISSING_PROMPT", f"Prompt file not found: {prompt_file}")

        # Phase Synchronization for Claude
        if agent == "claude":
            target_branch = self.spec.get("target_branch", "s02/integration")
            self.sync_claude_worktree(wt_dir, target_branch)

        # Agent execution
        if not self.skip_agent_exec and not self.dry_run:
            self.execute_agent(phase, wt_dir)
        else:
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
            "status": "SUCCESS",
            "commit_sha": commit_sha,
            "changed_files_count": len(changed_files)
        }
        self.run_summary["phases"].append(phase_result)

    def run_tests_in_venv(self):
        self.logger.info("\n=== Running Controller Verification & Pytest Suite ===")
        integration_dir = self.worktree_root / "integration"
        venv_dir = self.run_dir / "venv"

        self.logger.info(f"Creating isolated Python virtual environment at {venv_dir}")
        self.run_cmd([sys.executable, "-m", "venv", str(venv_dir)])

        pip_bin = venv_dir / "bin" / "pip"
        pytest_bin = venv_dir / "bin" / "pytest"

        req_file = integration_dir / "requirements.txt"
        if req_file.exists():
            self.logger.info(f"Installing dependencies from {req_file}")
            self.run_cmd([str(pip_bin), "install", "--no-cache-dir", "-r", str(req_file)], cwd=integration_dir)

        self.logger.info("Executing pytest suite...")
        try:
            test_res = self.run_cmd([str(pytest_bin), "-v"], cwd=integration_dir)
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
            with open(self.summary_file, "w", encoding="utf-8") as f:
                json.dump(self.run_summary, f, indent=2)
            self.logger.info(f"Run summary written to {self.summary_file}")

        return self.run_summary["status"] == "READY_FOR_REVIEW"


def main():
    parser = argparse.ArgumentParser(description="Hermes Sprint Workflow Runner (Sprint 02)")
    parser.add_argument("--spec", default="sprints/lab-s02.json", help="Path to sprint JSON specification")
    parser.add_argument("--dry-run", action="store_true", help="Simulate run without modifying git state")
    parser.add_argument("--skip-agent-execution", action="store_true", help="Skip invoking external agent CLI")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()
    
    runner = HermesSprintRunner(
        spec_path=args.spec,
        dry_run=args.dry_run,
        skip_agent_exec=args.skip_agent_execution,
        verbose=args.verbose
    )
    
    success = runner.execute()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
