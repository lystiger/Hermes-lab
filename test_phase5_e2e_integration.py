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
    End-to-End Cross-Process integration test for Phase 5.
    Process A: Uvicorn running LysStack Control Plane on a dynamic test port.
    Process B: Managed Hermes Runner executing a multi-phase sprint.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.port = 8993
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

        sprint_spec = {
            "sprint_id": "test-p5",
            "name": "Phase 5 Multi-Agent Integration Sprint",
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

        # 2. Run runner in Process B with simulated worker file changes and handoff files
        runner_script = ROOT_DIR / "runner" / "run-hermes-sprint.py"
        job_id = "run_20260822_test_p5"

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

def simulated_agent(phase, wt_dir):
    # Simulate modified code
    (wt_dir / f"file_{{phase['agent']}}.py").write_text("# code from " + phase["agent"] + "\\n", encoding="utf-8")
    # Simulate generated handoff
    (wt_dir / phase["expected_handoff"]).write_text("# " + phase["name"] + " Handoff Evidence\\nSummary of changes.\\n", encoding="utf-8")
    return SimpleNamespace(runtime_metadata={{}})

runner.execute_agent = simulated_agent
success = runner.execute()
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

        # 3. Verify Thread & Messages on Process A via HTTP API
        # A. GET /threads?jobId=...
        req = urllib.request.urlopen(f"{self.control_url}/threads?jobId={job_id}")
        threads = json.loads(req.read().decode("utf-8"))
        self.assertEqual(len(threads), 1)
        thread = threads[0]
        thread_id = thread["id"]
        self.assertEqual(thread["jobId"], job_id)

        # B. GET /threads/{thread_id}/messages
        req = urllib.request.urlopen(f"{self.control_url}/threads/{thread_id}/messages")
        messages = json.loads(req.read().decode("utf-8"))
        self.assertTrue(len(messages) >= 3, f"Expected at least 3 messages (2 handoffs + 1 verify), got {len(messages)}")

        # Check Message 1: Gemini -> Claude (BUILD Handoff)
        m1 = messages[0]
        self.assertEqual(m1["from"]["id"], "gemini")
        self.assertEqual(m1["to"][0]["id"], "claude")
        self.assertEqual(m1["kind"], "handoff")
        self.assertEqual(m1["intent"], "review_request")
        self.assertTrue(any(a["type"] == "git_commit" for a in m1["artifactRefs"]))
        self.assertTrue(any(a["type"] == "handoff" for a in m1["artifactRefs"]))

        # Check Message 2: Claude -> Hermes (HARDEN Handoff)
        m2 = messages[1]
        self.assertEqual(m2["from"]["id"], "claude")
        self.assertEqual(m2["kind"], "handoff")
        self.assertEqual(m2["intent"], "verification_request")

        # Check Message 3: Verification Result
        m3 = messages[2]
        self.assertEqual(m3["kind"], "verification_result")
        self.assertEqual(m3["intent"], "verification_result")
        self.assertIn("Verification passed", m3["text"])

        # C. GET /agents/claude/inbox
        req = urllib.request.urlopen(f"{self.control_url}/agents/claude/inbox")
        inbox = json.loads(req.read().decode("utf-8"))
        self.assertTrue(any(e["messageId"] == m1["id"] for e in inbox))

        # D. Verify Disk Persistence
        runs_dir = self.tmp_path / "runs"
        run_folder = next(runs_dir.glob("*_test-p5"))
        self.assertTrue((run_folder / "messages.jsonl").exists())
        self.assertTrue((run_folder / "artifacts.json").exists())


if __name__ == "__main__":
    unittest.main()
