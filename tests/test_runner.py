import json
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Dynamically import runner/run-hermes-sprint.py
runner_path = Path(__file__).resolve().parent.parent / "runner" / "run-hermes-sprint.py"
spec = importlib.util.spec_from_file_location("run_hermes_sprint", runner_path)
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)

HermesSprintRunner = runner_module.HermesSprintRunner
SprintRunnerError = runner_module.SprintRunnerError
scoped_antigravity_permissions = runner_module.scoped_antigravity_permissions
AgentContext = runner_module.AgentContext

from agents.antigravity import AntigravityAdapter
from agents.claude import ClaudeAdapter
from agents.codex import CodexAdapter
from agents.registry import AgentRegistry, default_registry
from backends.subprocess_backend import SubprocessBackend


class TestHermesSprintRunnerValidation(unittest.TestCase):
    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)
        self.spec_path = runner_path.parent.parent / "sprints" / "lab-s02.json"
        self.runner = HermesSprintRunner(spec_path=self.spec_path, dry_run=True, skip_agent_exec=True)

    # 1. Nested Antigravity Tool Error Detection
    def test_antigravity_nested_tool_error(self):
        sample_event = {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "tool_info": {
                    "name": "edit_file",
                    "error": "SyntaxError: invalid syntax at line 12"
                }
            }
        }
        stdout_text = json.dumps(sample_event)
        with self.assertRaises(SprintRunnerError) as ctx:
            self.runner.parse_antigravity_stream_json(stdout_text)
        self.assertEqual(ctx.exception.code, "FAILED_ANTIGRAVITY_TOOL_ERROR")

    def test_antigravity_nested_tool_permission_error(self):
        sample_event = {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "tool_info": {
                    "name": "edit_file",
                    "error": "Permission denied: unable to modify /etc/hosts"
                }
            }
        }
        stdout_text = json.dumps(sample_event)
        with self.assertRaises(SprintRunnerError) as ctx:
            self.runner.parse_antigravity_stream_json(stdout_text)
        self.assertEqual(ctx.exception.code, "FAILED_PERMISSION_DENIED")

    # 2. Antigravity Successful Tool Event
    def test_antigravity_success_tool_event(self):
        sample_event = {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "tool_info": {
                    "name": "edit_file",
                    "error": None
                }
            }
        }
        stdout_text = json.dumps(sample_event)
        try:
            self.runner.parse_antigravity_stream_json(stdout_text)
        except SprintRunnerError as e:
            self.fail(f"parse_antigravity_stream_json raised SprintRunnerError unexpectedly: {e}")

    # 3. Real Claude Success JSON where result contains arbitrary text
    def test_claude_success_with_arbitrary_result(self):
        claude_output = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "permission_denials": [],
            "result": "Completed phase successfully. Added /metrics endpoint and updated test_main.py. Error status: None."
        }
        stdout_text = json.dumps(claude_output)
        try:
            self.runner.parse_claude_json(stdout_text)
        except SprintRunnerError as e:
            self.fail(f"parse_claude_json raised SprintRunnerError unexpectedly: {e}")

    # 4. Claude Max-Turn Error
    def test_claude_max_turn_error(self):
        claude_output = {
            "type": "result",
            "subtype": "max_turns_exceeded",
            "is_error": False,
            "permission_denials": [],
            "result": "Reached max turns limit of 30."
        }
        stdout_text = json.dumps(claude_output)
        with self.assertRaises(SprintRunnerError) as ctx:
            self.runner.parse_claude_json(stdout_text)
        self.assertEqual(ctx.exception.code, "FAILED_CLAUDE_MAX_TURNS")

    # 5. Claude Permission Denials
    def test_claude_permission_denials(self):
        claude_output = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "permission_denials": ["Tool call Bash denied"],
            "result": "Permission prompt refused."
        }
        stdout_text = json.dumps(claude_output)
        with self.assertRaises(SprintRunnerError) as ctx:
            self.runner.parse_claude_json(stdout_text)
        self.assertEqual(ctx.exception.code, "FAILED_PERMISSION_DENIED")

    # 6. Worktree Validation Unit Tests
    def test_worktree_validation_invalid_worktree(self):
        with patch.object(self.runner, "run_cmd") as mock_cmd:
            mock_res = MagicMock()
            mock_res.returncode = 1
            mock_res.stdout = ""
            mock_cmd.return_value = mock_res
            
            with self.assertRaises(SprintRunnerError) as ctx:
                self.runner._ensure_worktree(Path("/home/lystiger/hermes-worktrees/hermes-lab-s02/antigravity"), "s02/antigravity", "s02/integration")
            self.assertEqual(ctx.exception.code, "FAILED_INVALID_WORKTREE")

    def test_worktree_validation_wrong_branch(self):
        with patch.object(self.runner, "run_cmd") as mock_cmd:
            res1 = MagicMock()
            res1.returncode = 0
            res1.stdout = "true\n"
            
            res2 = MagicMock()
            res2.returncode = 0
            res2.stdout = "main\n"
            
            mock_cmd.side_effect = [res1, res2]
            
            with self.assertRaises(SprintRunnerError) as ctx:
                self.runner._ensure_worktree(Path("/home/lystiger/hermes-worktrees/hermes-lab-s02/antigravity"), "s02/antigravity", "s02/integration")
            self.assertEqual(ctx.exception.code, "FAILED_WRONG_BRANCH")

    def test_worktree_validation_dirty_worktree(self):
        with patch.object(self.runner, "run_cmd") as mock_cmd:
            res1 = MagicMock()
            res1.returncode = 0
            res1.stdout = "true\n"
            
            res2 = MagicMock()
            res2.returncode = 0
            res2.stdout = "s02/antigravity\n"
            
            res3 = MagicMock()
            res3.returncode = 0
            res3.stdout = " M main.py\n"
            
            mock_cmd.side_effect = [res1, res2, res3]
            
            with self.assertRaises(SprintRunnerError) as ctx:
                self.runner._ensure_worktree(Path("/home/lystiger/hermes-worktrees/hermes-lab-s02/antigravity"), "s02/antigravity", "s02/integration")
            self.assertEqual(ctx.exception.code, "FAILED_DIRTY_WORKTREE")

    # 7. Scoped Antigravity Permissions Tests
    def test_scoped_permissions_installed_and_restored_on_success(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            wt_dir = root / "worktree"
            canonical_repo = root / "repo"
            settings_path = root / "config" / "settings.json"
            initial_content = '{"theme": "dark"}\n'
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(initial_content, encoding="utf-8")

            with scoped_antigravity_permissions(
                wt_dir, canonical_repo, settings_path=settings_path
            ):
                current_settings = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertIn(str(wt_dir.resolve()), current_settings.get("trustedWorkspaces", []))
                allow_rules = current_settings.get("permissions", {}).get("allow", [])
                self.assertIn(f"read_file({wt_dir.resolve()})", allow_rules)
                self.assertIn(f"write_file({wt_dir.resolve()})", allow_rules)
                self.assertIn(f"read_file({canonical_repo.resolve()}/.git)", allow_rules)
                self.assertIn("command(pwd)", allow_rules)
                self.assertIn("command(ls -la)", allow_rules)
                self.assertIn("command(pwd && ls -la)", allow_rules)
                self.assertIn("command(python3 -m pytest -q)", allow_rules)
                deny_rules = current_settings.get("permissions", {}).get("deny", [])
                self.assertIn(f"write_file({wt_dir.resolve()}/.git)", deny_rules)
                self.assertIn(f"write_file({canonical_repo.resolve()}/.git)", deny_rules)

            self.assertEqual(settings_path.read_text(encoding="utf-8"), initial_content)

    def test_scoped_permissions_restored_on_exception(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            settings_path = root / "config" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                with scoped_antigravity_permissions(
                    root / "worktree", root / "repo", settings_path=settings_path
                ):
                    raise RuntimeError("Simulated failure inside AGY context")
            self.assertEqual(settings_path.read_text(encoding="utf-8"), "not-json")

    def test_scoped_permissions_removes_initially_missing_file(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            settings_path = root / "config" / "settings.json"
            with scoped_antigravity_permissions(
                root / "worktree", root / "repo", settings_path=settings_path
            ):
                self.assertTrue(settings_path.exists())
            self.assertFalse(settings_path.exists())

    def test_scoped_permissions_default_uses_home_directory(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            settings_path = root / ".gemini" / "antigravity-cli" / "settings.json"
            with patch("agents.permissions.Path.home", return_value=root):
                with scoped_antigravity_permissions(root / "worktree", root / "repo"):
                    self.assertTrue(settings_path.exists())
            self.assertFalse(settings_path.exists())


class TestAgentRegistryAndCommands(unittest.TestCase):
    def test_known_agents_resolve(self):
        self.assertIsInstance(default_registry.get("antigravity"), AntigravityAdapter)
        self.assertIsInstance(default_registry.get("claude"), ClaudeAdapter)
        self.assertIsInstance(default_registry.get("codex"), CodexAdapter)

    def test_unknown_agent_fails_without_instantiation(self):
        unsupported = MagicMock()
        registry = AgentRegistry({"known": unsupported})
        with self.assertRaises(SprintRunnerError) as ctx:
            registry.get("missing")
        self.assertEqual(ctx.exception.code, "FAILED_UNKNOWN_AGENT")
        unsupported.assert_not_called()

    def test_antigravity_command(self):
        command = AntigravityAdapter().build_command(
            "do work", {"output_format": "stream-json", "dangerously_skip_permissions": False}
        )
        self.assertEqual(
            command,
            ["agy", "--new-project", "-p", "do work", "--output-format", "stream-json"],
        )

    def test_claude_command(self):
        command = ClaudeAdapter().build_command(
            "do work",
            {"model": "sonnet", "max_turns": 12, "permission_mode": "dontAsk", "output_format": "json"},
        )
        self.assertEqual(command[:14], [
            "claude", "-p", "do work", "--model", "sonnet", "--max-turns", "12",
            "--permission-mode", "dontAsk", "--output-format", "json",
            "--allowedTools", "Bash,Edit,Write", "--disallowedTools",
        ])
        denials = command[14].split(",")
        self.assertIn("Bash(git commit)", denials)
        self.assertIn("Bash(git commit:*)", denials)
        self.assertIn("Bash(git push:*)", denials)
        self.assertIn("Bash(git reset:*)", denials)
        self.assertIn("Bash(git merge:*)", denials)
        self.assertIn("Bash(git rebase:*)", denials)
        self.assertNotIn("Bash(git status:*)", denials)
        self.assertNotIn("Bash(git diff:*)", denials)
        self.assertNotIn("Bash(git log:*)", denials)
        self.assertNotIn("Bash(git branch --show-current)", denials)
        self.assertNotIn("Bash(git rev-parse:*)", denials)

    @unittest.skipUnless(shutil.which("claude"), "Claude Code CLI is not installed")
    def test_installed_claude_supports_disallowed_tools_flag(self):
        result = subprocess.run(
            ["claude", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--disallowedTools", result.stdout)

    def test_codex_command_is_non_interactive_and_scoped(self):
        worktree = Path("/tmp/worker")
        command = CodexAdapter().build_command("do work", {"sandbox": "danger-full-access"}, worktree)
        self.assertEqual(
            command,
            [
                "codex", "exec", "--color", "never", "--cd", str(worktree),
                "--sandbox", "workspace-write", "--ephemeral", "do work",
            ],
        )


class TestAgentExecution(unittest.TestCase):
    def make_context(self, temporary_dir, result=None, error=None, name="codex"):
        root = Path(temporary_dir)
        runner = SimpleNamespace(
            logger=MagicMock(),
            target_repo=root,
        )
        run_process = MagicMock(side_effect=error) if error else MagicMock(return_value=result)
        return AgentContext(
            runner=runner,
            phase={"name": "verification", "agent": name},
            worktree=root,
            prompt="verify",
            options={},
            stdout_file=root / "stdout.log",
            stderr_file=root / "stderr.log",
            timeout_seconds=10,
            backend=SubprocessBackend(run_process=run_process),
        )

    def test_codex_success_persists_output(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = subprocess.CompletedProcess(["codex"], 0, "completed", "warning")
            context = self.make_context(temporary_dir, result=result)
            CodexAdapter().execute(context)
            self.assertEqual(context.stdout_file.read_text(encoding="utf-8"), "completed")
            self.assertEqual(context.stderr_file.read_text(encoding="utf-8"), "warning")

    def test_codex_nonzero_exit_is_rejected_and_logged(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = subprocess.CompletedProcess(["codex"], 7, "partial", "failure")
            context = self.make_context(temporary_dir, result=result)
            with self.assertRaises(SprintRunnerError) as ctx:
                CodexAdapter().execute(context)
            self.assertEqual(ctx.exception.code, "FAILED_AGENT_EXECUTION")
            self.assertEqual(context.stderr_file.read_text(encoding="utf-8"), "failure")

    def test_subprocess_permission_error_is_rejected_by_adapter(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = subprocess.CompletedProcess(
                ["codex"], 1, "", "Permission denied by policy"
            )
            context = self.make_context(temporary_dir, result=result)
            with self.assertRaises(SprintRunnerError) as ctx:
                CodexAdapter().execute(context)
            self.assertEqual(ctx.exception.code, "FAILED_PERMISSION_DENIED")

    def test_codex_empty_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = subprocess.CompletedProcess(["codex"], 0, "", "")
            context = self.make_context(temporary_dir, result=result)
            with self.assertRaises(SprintRunnerError) as ctx:
                CodexAdapter().execute(context)
            self.assertEqual(ctx.exception.code, "FAILED_CODEX_EMPTY_OUTPUT")

    def test_codex_timeout_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            timeout = SprintRunnerError("FAILED_TIMEOUT", "timed out")
            context = self.make_context(temporary_dir, error=timeout)
            with self.assertRaises(SprintRunnerError) as ctx:
                CodexAdapter().execute(context)
            self.assertEqual(ctx.exception.code, "FAILED_TIMEOUT")

    def test_codex_missing_executable_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            context = self.make_context(temporary_dir, error=FileNotFoundError("codex"))
            with self.assertRaises(SprintRunnerError) as ctx:
                CodexAdapter().execute(context)
            self.assertEqual(ctx.exception.code, "FAILED_AGENT_EXECUTABLE_MISSING")

    def test_claude_nonzero_exit_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = subprocess.CompletedProcess(["claude"], 2, "", "bad")
            context = self.make_context(temporary_dir, result=result, name="claude")
            with self.assertRaises(SprintRunnerError) as ctx:
                ClaudeAdapter().execute(context)
            self.assertEqual(ctx.exception.code, "FAILED_AGENT_EXECUTION")

    def test_claude_is_error_is_rejected(self):
        output = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "permission_denials": [],
                "result": "failed",
            }
        )
        with self.assertRaises(SprintRunnerError) as ctx:
            ClaudeAdapter.parse_json(output)
        self.assertEqual(ctx.exception.code, "FAILED_CLAUDE_ERROR")

    def test_antigravity_permissions_restore_after_timeout(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            settings_path = Path(temporary_dir) / "config" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text('{"existing": true}', encoding="utf-8")
            timeout = SprintRunnerError("FAILED_TIMEOUT", "timed out")
            context = self.make_context(temporary_dir, error=timeout, name="antigravity")
            with self.assertRaises(SprintRunnerError):
                AntigravityAdapter(settings_path=settings_path).execute(context)
            self.assertEqual(
                settings_path.read_text(encoding="utf-8"), '{"existing": true}'
            )

    def test_malformed_agent_outputs_are_rejected(self):
        with self.assertRaises(SprintRunnerError) as claude_ctx:
            ClaudeAdapter.parse_json("not json")
        self.assertEqual(claude_ctx.exception.code, "FAILED_CLAUDE_INVALID_JSON")
        with self.assertRaises(SprintRunnerError) as agy_ctx:
            AntigravityAdapter.parse_stream_json("not json")
        self.assertEqual(agy_ctx.exception.code, "FAILED_ANTIGRAVITY_INVALID_OUTPUT")


class TestControllerDispatch(unittest.TestCase):
    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def test_existing_worktree_is_reset_on_every_initialization(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s02.json",
            dry_run=False,
            skip_agent_exec=True,
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            worktree = Path(temporary_dir)

            def command_result(command, **kwargs):
                if command == ["git", "rev-parse", "--is-inside-work-tree"]:
                    return subprocess.CompletedProcess(command, 0, "true\n", "")
                if command == ["git", "branch", "--show-current"]:
                    return subprocess.CompletedProcess(command, 0, "s03/worker\n", "")
                if command == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            runner.run_cmd = MagicMock(side_effect=command_result)
            runner._ensure_worktree(worktree, "s03/worker", "s03/integration")
            runner._ensure_worktree(worktree, "s03/worker", "s03/integration")
            resets = [
                call
                for call in runner.run_cmd.call_args_list
                if call.args[0] == ["git", "reset", "--hard", "s03/integration"]
            ]
            self.assertEqual(len(resets), 2)

    def test_prepare_environment_assigns_deterministic_start_refs(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
            dry_run=False,
            skip_agent_exec=True,
        )
        def command_result(command, **kwargs):
            stdout = "true\n" if command == ["git", "rev-parse", "--is-inside-work-tree"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        runner.run_cmd = MagicMock(side_effect=command_result)
        runner._ensure_worktree = MagicMock()
        with tempfile.TemporaryDirectory() as temporary_dir:
            runner.target_repo = Path(temporary_dir) / "target"
            runner.target_repo.mkdir()
            runner.worktree_root = Path(temporary_dir) / "worktrees"
            runner.prepare_environment()
            calls = runner._ensure_worktree.call_args_list
            self.assertEqual(
                calls[0].args,
                (runner.worktree_root / "integration", "s03/integration", "main"),
            )
            self.assertEqual(
                calls[1].args,
                (runner.worktree_root / "claude", "s03/claude", "s03/integration"),
            )
            self.assertEqual(
                calls[2].args,
                (runner.worktree_root / "codex", "s03/codex", "s03/integration"),
            )

    def test_prepare_environment_prefers_pinned_base_ref(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s04.json",
            dry_run=False,
            skip_agent_exec=True,
        )
        runner.spec["base_ref"] = "pinned-s03-baseline"
        def command_result(command, **kwargs):
            stdout = "true\n" if command == ["git", "rev-parse", "--is-inside-work-tree"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        runner.run_cmd = MagicMock(side_effect=command_result)
        runner._ensure_worktree = MagicMock()
        with tempfile.TemporaryDirectory() as temporary_dir:
            runner.target_repo = Path(temporary_dir) / "target"
            runner.target_repo.mkdir()
            runner.worktree_root = Path(temporary_dir) / "worktrees"
            runner.prepare_environment()

        self.assertEqual(
            runner._ensure_worktree.call_args_list[0].args,
            (
                runner.worktree_root / "integration",
                "s04/integration",
                "pinned-s03-baseline",
            ),
        )

    def test_sprint05_configures_three_agent_pipeline(self):
        repository = Path(__file__).resolve().parent.parent
        sprint = json.loads(
            (repository / "sprints" / "lab-s05.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            sprint["base_ref"], "ae984e1a8cda766143a8c3e01dfeeef549d59ac2"
        )
        self.assertEqual(
            [(phase["agent"], phase["execution_backend"]) for phase in sprint["phases"]],
            [
                ("antigravity", "herdr"),
                ("claude", "subprocess"),
                ("codex", "herdr"),
            ],
        )
        self.assertEqual(
            len({phase["branch"] for phase in sprint["phases"]}),
            len(sprint["phases"]),
        )
        for phase in sprint["phases"]:
            self.assertTrue((repository / phase["prompt_file"]).is_file())

    def test_sprint06_configures_session_backend_delivery(self):
        repository = Path(__file__).resolve().parent.parent
        sprint = json.loads(
            (repository / "sprints" / "lab-s06.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            sprint["base_ref"], "565c862aef1ee5fca20adebc2883580e70030257"
        )
        self.assertEqual(sprint["limits"]["timeout_seconds"], 900)
        self.assertEqual(sprint["phases"][1]["cmd_options"]["max_turns"], 70)
        self.assertEqual(
            [(phase["agent"], phase["execution_backend"]) for phase in sprint["phases"]],
            [
                ("antigravity", "herdr"),
                ("claude", "subprocess"),
                ("codex", "herdr"),
            ],
        )
        self.assertEqual(
            len({phase["branch"] for phase in sprint["phases"]}),
            len(sprint["phases"]),
        )
        self.assertNotIn(
            "herdr-session",
            {phase["execution_backend"] for phase in sprint["phases"]},
        )
        for phase in sprint["phases"]:
            self.assertTrue((repository / phase["prompt_file"]).is_file())

    def test_execute_agent_dispatches_through_registry(self):
        adapter = MagicMock()
        registry = MagicMock()
        registry.get.return_value = adapter
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s02.json",
            dry_run=True,
            skip_agent_exec=True,
            agent_registry=registry,
        )
        phase = runner.spec["phases"][0]
        with tempfile.TemporaryDirectory() as temporary_dir:
            runner.execute_agent(phase, Path(temporary_dir))
            registry.get.assert_called_once_with("antigravity")
            adapter.execute.assert_called_once()

    def test_controller_has_no_agent_command_construction(self):
        source = inspect.getsource(HermesSprintRunner.execute_agent)
        self.assertNotIn('"agy"', source)
        self.assertNotIn('"claude"', source)
        self.assertNotIn('"codex"', source)
        for adapter_type in (AntigravityAdapter, ClaudeAdapter, CodexAdapter):
            self.assertNotIn('"git"', inspect.getsource(adapter_type))

    def test_changed_file_limit_and_handoff_remain_mandatory(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s02.json",
            dry_run=True,
            skip_agent_exec=True,
        )
        runner.run_cmd = MagicMock(
            return_value=subprocess.CompletedProcess(
                ["git", "status"], 0, "".join(f" M file{number}.py\n" for number in range(16)), ""
            )
        )
        with self.assertRaises(SprintRunnerError) as changed_ctx:
            runner.validate_changed_files(Path("/tmp/worktree"))
        self.assertEqual(changed_ctx.exception.code, "FAILED_EXCESSIVE_FILES")
        runner.run_cmd.assert_called_once_with(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=Path("/tmp/worktree"),
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            with self.assertRaises(SprintRunnerError) as handoff_ctx:
                runner.validate_handoff_file(Path(temporary_dir), "HANDOFF.md")
        self.assertEqual(handoff_ctx.exception.code, "FAILED_MISSING_HANDOFF")

    def test_execute_phase_keeps_validation_commit_and_merge_in_controller(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s02.json",
            dry_run=False,
            skip_agent_exec=True,
        )
        runner.validate_python_syntax = MagicMock()
        runner.validate_changed_files = MagicMock(return_value=[" M changed.py"])
        runner.validate_handoff_file = MagicMock()

        def command_result(command, **kwargs):
            stdout = "abc123\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        runner.run_cmd = MagicMock(side_effect=command_result)
        phase = runner.spec["phases"][0]
        runner.execute_phase(phase)
        runner.validate_python_syntax.assert_called_once()
        runner.validate_changed_files.assert_called_once()
        runner.validate_handoff_file.assert_called_once()
        commands = [call.args[0] for call in runner.run_cmd.call_args_list]
        self.assertIn(["git", "add", "."], commands)
        self.assertTrue(any(command[:2] == ["git", "commit"] for command in commands))
        self.assertTrue(any(command[:2] == ["git", "merge"] for command in commands))

    def test_ready_for_review_requires_integration_tests(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s02.json",
            dry_run=True,
            skip_agent_exec=True,
        )
        runner.run_summary["phases"] = [{"phase": "one", "status": "SUCCESS"}]
        with self.assertRaises(SprintRunnerError) as ctx:
            runner.finalize()
        self.assertEqual(ctx.exception.code, "FAILED_TESTS")

    def test_later_phase_syncs_from_latest_integration(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
            dry_run=False,
            skip_agent_exec=True,
        )
        runner.run_summary["phases"] = [{"phase": "first", "status": "SUCCESS"}]
        runner.sync_phase_worktree = MagicMock()
        runner.validate_python_syntax = MagicMock()
        runner.validate_changed_files = MagicMock(return_value=[" M changed.py"])
        runner.validate_handoff_file = MagicMock()

        def command_result(command, **kwargs):
            stdout = "abc123\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        runner.run_cmd = MagicMock(side_effect=command_result)
        phase = runner.spec["phases"][1]
        runner.execute_phase(phase)
        runner.sync_phase_worktree.assert_called_once_with(
            runner.worktree_root / "codex", "s03/integration"
        )

    def test_sanitized_report_excludes_raw_and_machine_specific_data(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
            dry_run=True,
            skip_agent_exec=True,
        )
        runner.run_summary.update(
            {
                "status": "READY_FOR_REVIEW",
                "integration_commit": "abc123",
                "test_results": {"status": "PASSED", "output": "SECRET TEST OUTPUT"},
                "errors": [{"message": "/home/private token=SECRET"}],
                "phases": [
                    {
                        "phase": "verification",
                        "agent": "codex",
                        "backend": "herdr",
                        "status": "SUCCESS",
                        "changed_files_count": 4,
                        "commit_sha": "worker-secret-sha",
                        "runtime_metadata": {
                            "herdr_workspace_id": "machine-workspace",
                            "herdr_pane_id": "machine-pane",
                        },
                        "stdout": "SECRET MODEL OUTPUT",
                    }
                ],
            }
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_path = Path(temporary_dir) / "reports" / "run-summary.json"
            runner.export_sanitized_report(report_path)
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)
        self.assertEqual(
            report,
            {
                "integration_commit": "abc123",
                "phases": [
                    {
                        "agent": "codex",
                        "backend": "herdr",
                        "changed_files_count": 4,
                        "phase": "verification",
                        "status": "SUCCESS",
                    }
                ],
                "sprint_id": "lab-s03",
                "status": "READY_FOR_REVIEW",
                "test_status": "PASSED",
            },
        )
        self.assertNotIn("SECRET", report_text)
        self.assertNotIn("/home/", report_text)
        self.assertNotIn("machine-workspace", report_text)
        self.assertNotIn("machine-pane", report_text)

    def test_default_report_path_is_deterministic_and_opt_in(self):
        runner = HermesSprintRunner(
            spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
            dry_run=True,
            skip_agent_exec=True,
            export_report=True,
        )
        self.assertEqual(
            runner.report_path,
            runner.control_root / "reports" / "lab-s03" / "run-summary.json",
        )


class TestGenericVerification(unittest.TestCase):
    ABSENT = object()

    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def make_runner(self, root, verification=ABSENT):
        root.mkdir(parents=True, exist_ok=True)
        specification = {
            "sprint_id": "generic-verification",
            "worktree_root": str(root / "Worktrees With Spaces"),
            "runs_root": str(root / "Runs With Spaces"),
            "phases": [],
        }
        if verification is not self.ABSENT:
            specification["verification"] = verification
        spec_path = root / "specification.json"
        spec_path.write_text(json.dumps(specification), encoding="utf-8")
        runner = HermesSprintRunner(spec_path)
        runner.run_dir.mkdir(parents=True, exist_ok=True)
        return runner

    def test_generic_verification_runs_in_order_with_scoped_working_directories(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            verification = [
                {
                    "name": "first check",
                    "command": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('order.txt').write_text('first')",
                    ],
                },
                {
                    "name": "backend check",
                    "cwd": "backend",
                    "command": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; p=Path('../order.txt'); p.write_text(p.read_text() + ',second'); Path('cwd.txt').write_text('backend')",
                    ],
                    "timeout_seconds": 30,
                },
                {
                    "name": "final check",
                    "command": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; assert Path('order.txt').read_text() == 'first,second'",
                    ],
                },
            ]
            runner = self.make_runner(root, verification)
            integration = runner.worktree_root / "integration"
            (integration / "backend").mkdir(parents=True)
            self.assertEqual(runner.verification_steps[0]["timeout_seconds"], 300)
            self.assertEqual(runner.verification_steps[1]["timeout_seconds"], 30)

            runner.run_verification()

            self.assertEqual(runner.run_summary["verification_status"], "PASSED")
            self.assertEqual(
                runner.run_summary["verification_results"],
                [
                    {"name": "first check", "status": "PASSED"},
                    {"name": "backend check", "status": "PASSED"},
                    {"name": "final check", "status": "PASSED"},
                ],
            )
            self.assertEqual((integration / "order.txt").read_text(), "first,second")
            self.assertEqual(
                (integration / "backend" / "cwd.txt").read_text(), "backend"
            )
            self.assertTrue(
                (runner.run_dir / "verification_01_first_check_stdout.log").is_file()
            )
            self.assertTrue(
                (runner.run_dir / "verification_02_backend_check_stderr.log").is_file()
            )

    def test_generic_verification_fails_fast_and_skips_later_steps(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner = self.make_runner(
                root,
                [
                    {
                        "name": "pass",
                        "command": [sys.executable, "-c", "print('pass')"],
                    },
                    {
                        "name": "fail",
                        "command": [sys.executable, "-c", "raise SystemExit(7)"],
                    },
                    {
                        "name": "never",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('never.txt').write_text('ran')",
                        ],
                    },
                ],
            )
            integration = runner.worktree_root / "integration"
            integration.mkdir(parents=True)

            with self.assertRaises(SprintRunnerError) as context:
                runner.run_verification()

            self.assertEqual(context.exception.code, "FAILED_VERIFICATION")
            self.assertEqual(runner.run_summary["verification_status"], "FAILED")
            self.assertEqual(
                runner.run_summary["verification_results"],
                [
                    {"name": "pass", "status": "PASSED"},
                    {"name": "fail", "status": "FAILED"},
                ],
            )
            self.assertFalse((integration / "never.txt").exists())

    def test_invalid_verification_contracts_are_rejected_centrally(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            invalid_specs = [
                "pytest",
                ["not an object"],
                [{"name": "", "command": ["tool"]}],
                [{"name": "check", "command": "tool --check"}],
                [{"name": "check", "command": []}],
                [{"name": "check", "command": ["tool", 1]}],
                [{"name": "check", "command": ["tool"], "timeout_seconds": 0}],
                [{"name": "check", "command": ["tool"], "timeout_seconds": -1}],
                [{"name": "check", "command": ["tool"], "timeout_seconds": "5"}],
                [{"name": "check", "command": ["tool"], "timeout_seconds": True}],
                [
                    {"name": "same", "command": ["tool"]},
                    {"name": "same", "command": ["tool"]},
                ],
                [{"name": "check", "command": ["tool"], "cwd": "../outside"}],
                [{"name": "check", "command": ["tool"], "cwd": str(root)}],
                [{"name": "check", "command": ["tool"], "cwd": "C:\\outside"}],
                [
                    {
                        "name": "check",
                        "command": ["tool"],
                        "cwd": "\\\\server\\share",
                    }
                ],
            ]
            for index, verification in enumerate(invalid_specs):
                with self.subTest(index=index):
                    case_root = root / str(index)
                    case_root.mkdir()
                    with self.assertRaises(SprintRunnerError) as context:
                        self.make_runner(case_root, verification)
                    self.assertEqual(
                        context.exception.code,
                        "FAILED_INVALID_VERIFICATION_SPEC",
                    )

    def test_execute_selects_generic_or_legacy_verification_without_overlap(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            generic = self.make_runner(
                root / "generic",
                [{"name": "check", "command": ["tool"]}],
            )
            legacy = self.make_runner(root / "legacy")
            for runner in (generic, legacy):
                runner.prepare_environment = MagicMock()
                runner.run_verification = MagicMock()
                runner.run_tests_in_venv = MagicMock()
                runner.finalize = MagicMock()

            generic.execute()
            legacy.execute()

            generic.run_verification.assert_called_once_with()
            generic.run_tests_in_venv.assert_not_called()
            legacy.run_tests_in_venv.assert_called_once_with()
            legacy.run_verification.assert_not_called()

    def test_finalize_accepts_only_the_configured_verification_mode(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            generic = self.make_runner(
                root,
                [{"name": "check", "command": ["tool"]}],
            )
            generic.run_cmd = MagicMock(
                return_value=subprocess.CompletedProcess(
                    ["git", "rev-parse", "HEAD"], 0, "abc123\n", ""
                )
            )
            generic.run_summary["verification_status"] = "PASSED"
            generic.finalize()
            self.assertEqual(generic.run_summary["status"], "READY_FOR_REVIEW")

            generic.run_summary["verification_status"] = "FAILED"
            with self.assertRaises(SprintRunnerError) as context:
                generic.finalize()
            self.assertEqual(context.exception.code, "FAILED_VERIFICATION")

    def test_sanitized_report_contains_only_safe_generic_verification_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            runner = self.make_runner(
                root,
                [{"name": "lint", "command": ["secret-tool", "token-value"]}],
            )
            runner.run_summary.update(
                {
                    "status": "READY_FOR_REVIEW",
                    "verification_status": "PASSED",
                    "verification_results": [
                        {
                            "name": "lint",
                            "status": "PASSED",
                            "stdout": "SECRET OUTPUT",
                            "cwd": str(root),
                        }
                    ],
                    "integration_commit": "abc123",
                }
            )
            report_path = root / "report.json"

            runner.export_sanitized_report(report_path)
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)

            self.assertEqual(report["verification_status"], "PASSED")
            self.assertEqual(
                report["verification"],
                [{"name": "lint", "status": "PASSED"}],
            )
            self.assertNotIn("SECRET", report_text)
            self.assertNotIn(str(root), report_text)
            self.assertNotIn("token-value", report_text)


class TestExternalRepositorySupport(unittest.TestCase):
    def setUp(self):
        self.logging_patch = patch.object(
            HermesSprintRunner, "_setup_logging", return_value=MagicMock()
        )
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)

    def init_repository(self, repository, filename="README.md", content="initial\n"):
        repository.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Hermes Test"],
            cwd=repository,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "hermes@example.invalid"],
            cwd=repository,
            check=True,
        )
        (repository / filename).parent.mkdir(parents=True, exist_ok=True)
        (repository / filename).write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )

    def write_spec(self, path, **overrides):
        specification = {
            "sprint_id": "external-example",
            "base_ref": "main",
            "target_branch": "hermes/external-example",
            "phases": [],
            **overrides,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(specification), encoding="utf-8")
        return path

    def test_external_repo_owns_git_worktrees_while_control_root_owns_prompt(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            control_repo = root / "Hermes Project"
            target_repo = root / "Uni Green Project"
            self.init_repository(control_repo, "prompts/external.md", "external prompt\n")
            self.init_repository(target_repo)
            phase = {
                "name": "worker",
                "agent": "codex",
                "worktree_dir": "codex worker",
                "branch": "hermes/external-codex",
                "prompt_file": "prompts/external.md",
                "expected_handoff": "HANDOFF.md",
                "commit_message": "test: external worktree",
            }
            spec_path = self.write_spec(
                control_repo / "specs" / "external.json",
                control_root=str(control_repo),
                target_repo=str(target_repo),
                worktree_root=str(root / "Hermes Worktrees"),
                runs_root=str(root / "Hermes Runs"),
                phases=[phase],
            )
            adapter = MagicMock()
            registry = MagicMock()
            registry.get.return_value = adapter
            runner = HermesSprintRunner(
                spec_path,
                agent_registry=registry,
                export_report=True,
            )

            self.assertTrue(
                subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=control_repo,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
            runner.prepare_environment()
            runner.execute_agent(phase, runner.worktree_root / "codex worker")

            target_branches = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=target_repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            control_branches = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=control_repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertIn("hermes/external-example", target_branches)
            self.assertIn("hermes/external-codex", target_branches)
            self.assertEqual(control_branches, ["main"])
            context = adapter.execute.call_args.args[0]
            self.assertEqual(context.prompt, "external prompt")
            self.assertEqual(runner.target_repo, target_repo.resolve())
            self.assertEqual(runner.control_root, control_repo.resolve())
            self.assertEqual(
                runner.report_path,
                control_repo / "reports" / "external-example" / "run-summary.json",
            )

    def test_legacy_canonical_repo_normalizes_to_target_repo(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            legacy_repo = root / "legacy target"
            spec_path = self.write_spec(
                root / "specs" / "legacy.json",
                canonical_repo=str(legacy_repo),
                runs_root=str(root / "runs"),
            )
            runner = HermesSprintRunner(spec_path)
            self.assertEqual(runner.target_repo, legacy_repo.resolve())
            self.assertEqual(runner.control_root, runner_path.parent.parent)

    def test_explicit_target_repo_takes_precedence_over_legacy_field(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            target_repo = root / "new target"
            spec_path = self.write_spec(
                root / "specs" / "precedence.json",
                target_repo=str(target_repo),
                canonical_repo=str(root / "legacy target"),
                runs_root=str(root / "runs"),
            )
            runner = HermesSprintRunner(spec_path)
            self.assertEqual(runner.target_repo, target_repo.resolve())

    def test_existing_non_git_target_has_explicit_validation_error(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            target_repo = root / "not a repository"
            target_repo.mkdir()
            spec_path = self.write_spec(
                root / "specs" / "non-git.json",
                target_repo=str(target_repo),
                worktree_root=str(root / "worktrees"),
                runs_root=str(root / "runs"),
            )
            runner = HermesSprintRunner(spec_path)
            with self.assertRaises(SprintRunnerError) as context:
                runner.prepare_environment()
            self.assertEqual(context.exception.code, "FAILED_TARGET_REPO_NOT_GIT")
            self.assertIn(str(target_repo), context.exception.message)

    def test_relative_paths_resolve_from_spec_directory_not_current_directory(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            spec_dir = root / "control" / "specs"
            spec_path = self.write_spec(
                spec_dir / "relative.json",
                target_repo="../../target",
                control_root="..",
                worktree_root="../../worktrees",
                runs_root="../../runs",
            )
            original_directory = Path.cwd()
            try:
                os.chdir(root)
                first = HermesSprintRunner(spec_path)
                os.chdir(root / "control")
                second = HermesSprintRunner(spec_path)
            finally:
                os.chdir(original_directory)
            self.assertEqual(first.target_repo, second.target_repo)
            self.assertEqual(first.target_repo, (root / "target").resolve())
            self.assertEqual(first.control_root, (root / "control").resolve())

    def test_windows_venv_path_uses_native_layout_without_posix_resolution(self):
        venv = PureWindowsPath("C:/Users/user/Hermes Runs/venv")
        self.assertEqual(
            HermesSprintRunner._venv_python(venv, platform_name="nt"),
            PureWindowsPath("C:/Users/user/Hermes Runs/venv/Scripts/python.exe"),
        )

    @unittest.skipUnless(
        os.environ.get("HERMES_FULL_E2E") == "1",
        "Set HERMES_FULL_E2E=1 to run isolated Git/venv pipeline",
    )
    def test_full_external_repository_pipeline(self):
        class WritingAdapter:
            def execute(self, context):
                (context.worktree / "feature.py").write_text(
                    "VALUE = 42\n",
                    encoding="utf-8",
                )
                (context.worktree / "test_feature.py").write_text(
                    "from feature import VALUE\n\n\ndef test_value():\n    assert VALUE == 42\n",
                    encoding="utf-8",
                )
                (context.worktree / "HANDOFF.md").write_text(
                    "External repository pipeline complete.\n",
                    encoding="utf-8",
                )
                return SimpleNamespace(runtime_metadata={})

        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            control_repo = root / "Hermes Control"
            target_repo = root / "External Product"
            self.init_repository(control_repo, "prompts/e2e.md", "Build feature.\n")
            self.init_repository(target_repo, "requirements.txt", "pytest\n")
            phase = {
                "name": "delivery",
                "agent": "writer",
                "worktree_dir": "writer",
                "branch": "hermes/e2e-writer",
                "prompt_file": "prompts/e2e.md",
                "expected_handoff": "HANDOFF.md",
                "commit_message": "test: external delivery",
            }
            spec_path = self.write_spec(
                control_repo / "sprints" / "e2e.json",
                control_root=str(control_repo),
                target_repo=str(target_repo),
                target_branch="hermes/e2e-integration",
                worktree_root=str(root / "Hermes Worktrees"),
                runs_root=str(root / "Hermes Runs"),
                phases=[phase],
                limits={"max_changed_files": 5, "timeout_seconds": 120},
            )
            runner = HermesSprintRunner(
                spec_path,
                agent_registry=AgentRegistry({"writer": WritingAdapter}),
            )
            runner.run_dir.mkdir(parents=True, exist_ok=True)

            self.assertTrue(runner.execute(), runner.run_summary)
            self.assertEqual(runner.run_summary["status"], "READY_FOR_REVIEW")
            self.assertEqual(runner.run_summary["test_results"]["status"], "PASSED")
            integration = runner.worktree_root / "integration"
            self.assertEqual(
                subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=integration,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "hermes/e2e-integration",
            )


if __name__ == "__main__":
    unittest.main()
