#!/usr/bin/env python3
"""
Phase 5.1.1 Real CLI Smoke Test
Executes a multi-phase sprint workflow via the Hermes Sprint Runner CLI
verifying mailbox message consumption, effective prompt injection, post-execution acknowledgement,
and truthful artifact trust evaluation end-to-end.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import urllib.request
import uvicorn

from main import app

ROOT_DIR = Path(__file__).resolve().parent


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_phase511_smoke_test():
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[*] 1. Starting LysStack control-plane on {base_url}...")

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config=config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    time.sleep(1.0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Health check
        with urllib.request.urlopen(f"{base_url}/health", timeout=1.0) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            print(f"    -> Health check: {health['status']} (version {health['version']})")
            assert health["status"] == "ok"

        # 2. Setup target git repo
        target_repo = tmp_path / "target_repo"
        target_repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=target_repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "smoke@lysstack.org"], cwd=target_repo, check=True)
        subprocess.run(["git", "config", "user.name", "Smoke Tester"], cwd=target_repo, check=True)
        (target_repo / "README.md").write_text("# Smoke Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=target_repo, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=target_repo, check=True)

        job_id = "run_smoke_511"
        thread_id = f"thread_job_{job_id}"

        # 3. Create Sprint Spec
        p1_prompt = tmp_path / "prompt_builder.md"
        p1_prompt.write_text("Builder: Implement feature.\n", encoding="utf-8")
        p2_prompt = tmp_path / "prompt_hardener.md"
        p2_prompt.write_text("Hardener: Review feature and test.\n", encoding="utf-8")

        spec = {
            "sprint_id": "smoke-511",
            "name": "Phase 5.1.1 Smoke Test Sprint",
            "target_repo": str(target_repo),
            "target_branch": "hermes/smoke-511/integration",
            "worktree_root": str(tmp_path / "worktrees"),
            "runs_root": str(tmp_path / "runs"),
            "phases": [
                {
                    "name": "01_builder",
                    "role": "builder",
                    "agent": "gemini",
                    "worktree_dir": "wt_builder",
                    "branch": "smoke-511/builder",
                    "prompt_file": str(p1_prompt),
                    "expected_handoff": "HANDOFF_BUILD.md",
                    "commit_message": "feat: builder complete",
                },
                {
                    "name": "02_hardener",
                    "role": "hardener",
                    "agent": "claude",
                    "worktree_dir": "wt_hardener",
                    "branch": "smoke-511/hardener",
                    "prompt_file": str(p2_prompt),
                    "expected_handoff": "HANDOFF_HARDEN.md",
                    "commit_message": "fix: hardener complete",
                }
            ],
            "verification": [
                {
                    "name": "verify_target",
                    "command": [sys.executable, "-c", "print('Smoke verification OK')"],
                    "timeout_seconds": 30
                }
            ]
        }

        spec_file = tmp_path / "smoke-511.json"
        spec_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")

        # 4. Post Operator Guidance Message to Claude via Control Plane
        print("[*] 2. Sending operator guidance message to Claude via Control Plane...")
        op_payload = json.dumps({
            "threadId": thread_id,
            "to": ["claude"],
            "kind": "operator",
            "intent": "operator_note",
            "text": "CRITICAL: Ensure atomic transaction rollback before committing."
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/messages",
            data=op_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 201
            op_data = json.loads(resp.read().decode("utf-8"))
            op_msg_id = op_data["id"]
            print(f"    -> Message created: {op_msg_id}")

        # Verify message is currently DELIVERED
        with urllib.request.urlopen(f"{base_url}/agents/claude/inbox?state=DELIVERED") as resp:
            inbox = json.loads(resp.read().decode("utf-8"))
            assert any(e["messageId"] == op_msg_id for e in inbox)
            print("    -> Message confirmed in Claude mailbox (DELIVERED)")

        # 5. Execute Runner CLI with simulated adapter execution hook
        print("[*] 3. Executing Hermes Runner CLI workflow...")
        runner_script = ROOT_DIR / "runner" / "run-hermes-sprint.py"
        captured_prompts_file = tmp_path / "prompts_out.json"

        cli_driver_code = f"""
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

captured = {{}}

def simulated_agent(phase, wt_dir, mailbox_messages=None):
    agent_name = phase["agent"]
    prompt_file = runner.resolve_prompt_file(phase)
    effective_prompt = runner.build_effective_prompt(
        prompt_file.read_text(encoding="utf-8").strip(),
        current_agent=agent_name,
        mailbox_messages=mailbox_messages,
    )
    captured[agent_name] = effective_prompt
    (wt_dir / f"file_{{agent_name}}.py").write_text("# output by " + agent_name + "\\n", encoding="utf-8")
    (wt_dir / phase["expected_handoff"]).write_text("# " + phase["name"] + " Handoff\\nOK\\n", encoding="utf-8")
    return SimpleNamespace(runtime_metadata={{}})

runner.execute_agent = simulated_agent
success = runner.execute()

with open("{captured_prompts_file}", "w", encoding="utf-8") as f:
    json.dump(captured, f, indent=2)

sys.exit(0 if success else 1)
"""
        driver_file = tmp_path / "driver.py"
        driver_file.write_text(cli_driver_code, encoding="utf-8")

        env = dict(os.environ)
        env["LYSSTACK_CONTROL_URL"] = base_url
        env["HERMES_JOB_ID"] = job_id

        proc = subprocess.run(
            [sys.executable, str(driver_file)],
            cwd=str(ROOT_DIR),
            env=env,
            capture_output=True,
            text=True,
        )

        if proc.returncode != 0:
            print("RUNNER STDOUT:\n", proc.stdout)
            print("RUNNER STDERR:\n", proc.stderr)
            raise RuntimeError(f"Runner failed with exit code {proc.returncode}")

        print("    -> Hermes Sprint Runner completed with returncode 0")

        # 6. Verify Effective Prompts
        with open(captured_prompts_file, "r", encoding="utf-8") as f:
            prompts = json.load(f)

        assert "Ensure atomic transaction rollback" not in prompts.get("gemini", "")
        claude_p = prompts.get("claude", "")
        assert "--- LYSSTACK OPERATIONAL MESSAGES FOR CLAUDE ---" in claude_p
        assert "Ensure atomic transaction rollback" in claude_p
        print("    -> Prompt verification: Operator guidance successfully injected into Claude context")

        # 7. Verify Post-Execution Acknowledgement
        with urllib.request.urlopen(f"{base_url}/agents/claude/inbox?state=ACKNOWLEDGED") as resp:
            inbox_acked = json.loads(resp.read().decode("utf-8"))
            acked = any(e["messageId"] == op_msg_id for e in inbox_acked)
            assert acked, "Operator message was not acknowledged"
            print("    -> Mailbox verification: Message transitioned from DELIVERED to ACKNOWLEDGED")

        # 8. Verify Truthful Artifact Trust
        run_folder = next((tmp_path / "runs").glob("*_smoke-511"))
        with open(run_folder / "artifacts.json", "r", encoding="utf-8") as f:
            artifacts = json.load(f)

        for a in artifacts:
            t = a.get("trust", {})
            if a.get("type") == "git_commit":
                assert t.get("status") == "not_applicable"
                assert t.get("kind") == "git_reference"
            elif a.get("type") == "handoff":
                assert t.get("status") == "verified"
                assert t.get("kind") == "path_containment"
                assert t.get("scope") == "hermes_run_root"
        print("    -> Artifact trust verification: All artifacts have truthful trust metadata")

    print("\n========================================================")
    print("✅ PHASE 5.1.1 REAL CLI SMOKE TEST PASSED SUCCESSFULLY!")
    print("========================================================\n")


if __name__ == "__main__":
    run_phase511_smoke_test()
