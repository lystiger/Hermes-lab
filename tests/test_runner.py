import os
import sys
import json
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

# Dynamically import runner/run-hermes-sprint.py
runner_path = Path(__file__).resolve().parent.parent / "runner" / "run-hermes-sprint.py"
spec = importlib.util.spec_from_file_location("run_hermes_sprint", runner_path)
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)

HermesSprintRunner = runner_module.HermesSprintRunner
SprintRunnerError = runner_module.SprintRunnerError


class TestHermesSprintRunnerValidation(unittest.TestCase):
    def setUp(self):
        self.spec_path = Path("/home/lystiger/hermes-lab/sprints/lab-s02.json")
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


if __name__ == "__main__":
    unittest.main()
