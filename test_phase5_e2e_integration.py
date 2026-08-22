import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import urllib.request
import unittest

ROOT_DIR = Path(__file__).resolve().parent


class TestPhase5EndToEndIntegration(unittest.TestCase):
    """
    End-to-End Cross-Process integration test for Phase 5.1.
    Process A: Uvicorn running LysStack Control Plane on a dynamic test port.
    Process B: Managed Hermes Runner executing a multi-phase sprint.
    Verifies:
      - Live operator message posted to control plane reaches target agent's effective prompt.
      - Unrelated agent does not receive the message.
      - Consumed message transitions from DELIVERED to ACKNOWLEDGED upon execution.
      - Artifact trust is truthfully validated and persisted.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.port = 8995
        self.control_url = f"http://127.0.0.1:{self.port}"

        # 1. Start Control Plane (Process A)
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self.server_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to become healthy
        started = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{self.control_url}/health", timeout=1.0) as resp:
                    if resp.status == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)

        self.assertTrue(started, "LysStack Control Plane failed to start within 5 seconds")

    def tearDown(self):
        if self.server_proc:
            self.server_proc.terminate()
            try:
                self.server_proc.wait(timeout=3)
            except Exception:
                self.server_proc.kill()
        self.tmp_dir.cleanup()

    def test_multi_phase_sprint_cross_process_flow(self):
        # 1. Setup a test git target repository
        target_repo = self.tmp_path / "target_repo"
        target_repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=target_repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@lysstack.org"], cwd=target_repo, check=True)
        subprocess.run(["git", "config", "user.name", "LysStack Tester"], cwd=target_repo, check=True)
        (target_repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=target_repo, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=target_repo, check=True)

        # Create sprint specification with 2 phases + verification
        p1_prompt = self.tmp_path / "prompt_build.md"
        p1_prompt.write_text("Builder: Implement feature.\n", encoding="utf-8")
        p2_prompt = self.tmp_path / "prompt_harden.md"
        p2_prompt.write_text("Hardener: Review feature and test.\n", encoding="utf-8")

        job_id = "run_20260822_test_p51"
        thread_id = f"thread_job_{job_id}"

        sprint_spec = {
            "sprint_id": "test-p5",
            "name": "Phase 5.1 Multi-Agent Integration Sprint",
            "target_repo": str(target_repo),
            "target_branch": "hermes/test-p5/integration",
            "worktree_root": str(self.tmp_path / "worktrees"),
            "runs_root": str(self.tmp_path / "runs"),
            "phases": [
                {
                    "name": "01_builder",
                    "role": "builder",
                    "agent": "gemini",
                    "worktree_dir": "wt_builder",
                    "branch": "test-p5/builder",
                    "prompt_file": str(p1_prompt),
                    "expected_handoff": "HANDOFF_BUILD.md",
                    "commit_message": "feat: build complete",
                },
                {
                    "name": "02_hardener",
                    "role": "hardener",
                    "agent": "claude",
                    "worktree_dir": "wt_hardener",
                    "branch": "test-p5/hardener",
                    "prompt_file": str(p2_prompt),
                    "expected_handoff": "HANDOFF_HARDEN.md",
                    "commit_message": "fix: harden complete",
                }
            ],
            "verification": [
                {
                    "name": "check_target",
                    "command": [sys.executable, "-c", "print('Verified OK')"],
                    "timeout_seconds": 30
                }
            ]
        }

        spec_file = self.tmp_path / "test-p5.json"
        spec_file.write_text(json.dumps(sprint_spec, indent=2), encoding="utf-8")

        # 2. Pre-send an Operator Message targeted specifically to Claude via Control API (Process A)
        op_payload = json.dumps({
            "threadId": thread_id,
            "to": ["claude"],
            "kind": "operator",
            "intent": "operator_note",
            "text": "Please inspect scheduler mutex contention before modifying state."
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.control_url}/messages",
            data=op_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)
            op_msg_data = json.loads(resp.read().decode("utf-8"))
            op_msg_id = op_msg_data["id"]

        # Verify message is currently DELIVERED in Claude's inbox
        with urllib.request.urlopen(f"{self.control_url}/agents/claude/inbox?state=DELIVERED") as resp:
            inbox = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(any(e["messageId"] == op_msg_id for e in inbox))

        # 3. Run runner in Process B
        runner_script = ROOT_DIR / "runner" / "run-hermes-sprint.py"
        captured_prompts_file = self.tmp_path / "captured_prompts.json"

        test_driver_code = f"""
import sys
import json
from types import SimpleNamespace
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location("run_hermes_sprint", "{runner_script}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

runner = module.HermesSprintRunner(
    spec_path="{spec_file}",
    skip_agent_exec=False
)

captured_prompts = {{}}
original_execute_agent = runner.execute_agent

def simulated_agent(phase, wt_dir, mailbox_messages=None):
    agent_name = phase["agent"]
    prompt_file = runner.resolve_prompt_file(phase)
    effective_prompt = runner.build_effective_prompt(
        prompt_file.read_text(encoding="utf-8").strip(),
        current_agent=agent_name,
        mailbox_messages=mailbox_messages,
    )
    if agent_name not in captured_prompts or mailbox_messages:
        captured_prompts[agent_name] = effective_prompt

    # Simulate modified code and handoff file
    (wt_dir / f"file_{{agent_name}}.py").write_text("# code from " + agent_name + "\\n", encoding="utf-8")
    (wt_dir / phase["expected_handoff"]).write_text("# " + phase["name"] + " Handoff Evidence\\nSummary of changes.\\n", encoding="utf-8")
    return SimpleNamespace(runtime_metadata={{}})

runner.execute_agent = simulated_agent
success = runner.execute()

with open("{captured_prompts_file}", "w", encoding="utf-8") as f:
    json.dump(captured_prompts, f, indent=2)

sys.exit(0 if success else 1)
"""
        driver_file = self.tmp_path / "driver.py"
        driver_file.write_text(test_driver_code, encoding="utf-8")

        env = dict(os.environ)
        env["LYSSTACK_CONTROL_URL"] = self.control_url
        env["HERMES_JOB_ID"] = job_id

        run_proc = subprocess.run(
            [sys.executable, str(driver_file)],
            cwd=str(ROOT_DIR),
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertEqual(run_proc.returncode, 0, f"Runner failed with output:\n{run_proc.stdout}\n{run_proc.stderr}")

        # 4. Verify Effective Prompts
        self.assertTrue(captured_prompts_file.exists())
        with open(captured_prompts_file, "r", encoding="utf-8") as f:
            prompts = json.load(f)

        # Gemini (Builder) prompt MUST NOT have Claude's operator message
        gemini_prompt = prompts.get("gemini", "")
        self.assertNotIn("Please inspect scheduler mutex contention", gemini_prompt)

        # Claude (Hardener) prompt MUST have Gemini's handoff AND the Operator message
        claude_prompt = prompts.get("claude", "")
        self.assertIn("--- LYSSTACK OPERATIONAL THREAD ---", claude_prompt)
        self.assertIn("[from: gemini]", claude_prompt)
        self.assertIn("--- LYSSTACK OPERATIONAL MESSAGES FOR CLAUDE ---", claude_prompt)
        self.assertIn("[from: operator]", claude_prompt)
        self.assertIn("intent: operator_note", claude_prompt)
        self.assertIn("Please inspect scheduler mutex contention before modifying state.", claude_prompt)

        # 5. Verify Operator Message transitioned to ACKNOWLEDGED in Control Plane (Process A)
        with urllib.request.urlopen(f"{self.control_url}/agents/claude/inbox?state=ACKNOWLEDGED") as resp:
            inbox_acked = json.loads(resp.read().decode("utf-8"))
            acked_entry = next((e for e in inbox_acked if e["messageId"] == op_msg_id), None)
            self.assertIsNotNone(acked_entry, "Operator message was not marked ACKNOWLEDGED in Claude's mailbox")
            self.assertEqual(acked_entry["state"], "ACKNOWLEDGED")

        # 6. Verify Artifacts & Truthful Trust
        runs_dir = self.tmp_path / "runs"
        run_folder = next(runs_dir.glob("*_test-p5"))
        artifacts_path = run_folder / "artifacts.json"
        self.assertTrue(artifacts_path.exists())

        with open(artifacts_path, "r", encoding="utf-8") as f:
            artifacts = json.load(f)

        commit_arts = [a for a in artifacts if a.get("type") == "git_commit"]
        handoff_arts = [a for a in artifacts if a.get("type") == "handoff"]

        self.assertTrue(len(commit_arts) > 0)
        self.assertTrue(len(handoff_arts) > 0)

        # Git commits have status "not_applicable" and kind "git_reference"
        for ca in commit_arts:
            self.assertEqual(ca["trust"]["status"], "not_applicable")
            self.assertEqual(ca["trust"]["kind"], "git_reference")

        # Filesystem handoff artifacts have status "verified" and kind "path_containment"
        for ha in handoff_arts:
            self.assertEqual(ha["trust"]["status"], "verified")
            self.assertEqual(ha["trust"]["kind"], "path_containment")
            self.assertEqual(ha["trust"]["scope"], "hermes_run_root")


if __name__ == "__main__":
    unittest.main()
