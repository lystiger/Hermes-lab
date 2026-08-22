#!/usr/bin/env python3
import json
import socket
import sys
import threading
import time
import urllib.request
import uvicorn

from main import app
from runner.control_plane.event_publisher import RuntimeEventPublisher


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_phase4_smoke_test():
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[*] Starting LysStack control-plane process on {base_url}...")

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config=config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    time.sleep(1.0)

    try:
        # Step 1: Health check
        print("[*] 1. Checking GET /health...")
        with urllib.request.urlopen(f"{base_url}/health", timeout=1.0) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            print(f"    -> Health response: {health}")
            assert health["status"] == "ok"

        # Step 2: Initialize sprint job
        job_id = "run_20260822_unigreen_inquiry_demo"
        sprint_id = "unigreen-inquiry-v1"
        publisher = RuntimeEventPublisher(control_url=base_url)

        print(f"[*] 2. Initializing sprint '{sprint_id}' (Job ID: {job_id})...")
        publisher.publish(
            source_id="hermes_runner",
            source_kind="runtime",
            kind="job.created",
            detail="Sprint unigreen-inquiry-v1 initialized",
            job_id=job_id,
            metadata={
                "sprintId": sprint_id,
                "title": "Unigreen Public Inquiry Submission",
                "repository": "Unigreen",
                "branch": "hermes/unigreen-inquiry-v1/integration",
                "phases": [
                    {"name": "BUILD", "role": "builder", "agent": "antigravity"},
                    {"name": "HARDEN", "role": "hardener", "agent": "claude"},
                    {"name": "VERIFY", "role": "verifier", "agent": "codex"},
                ],
            },
        )
        publisher.publish(
            source_id="hermes_runner",
            source_kind="runtime",
            kind="job.started",
            detail="Execution started",
            job_id=job_id,
        )

        # Step 3: Query /jobs in real control plane
        print("[*] 3. Querying GET /jobs...")
        with urllib.request.urlopen(f"{base_url}/jobs", timeout=1.0) as resp:
            jobs = json.loads(resp.read().decode("utf-8"))
            active_job = next(j for j in jobs if j["id"] == job_id)
            print(f"    -> Found job: {active_job['title']} (Status: {active_job['status']}, Agents: {active_job['assignedAgentIds']})")
            assert active_job["status"] == "RUNNING"

        # Step 4: Phase 1 (BUILD / Gemini)
        print("[*] 4. Executing Phase 1: BUILD (Agent: Gemini)...")
        publisher.publish(
            source_id="antigravity",
            source_kind="agent",
            kind="phase.started",
            detail="Starting phase BUILD",
            job_id=job_id,
            metadata={"phase": "BUILD", "role": "builder", "agent": "antigravity", "order": 1},
        )
        with urllib.request.urlopen(f"{base_url}/jobs/{job_id}", timeout=1.0) as resp:
            detail = json.loads(resp.read().decode("utf-8"))
            print(f"    -> Job currentPhase: {detail['currentPhase']}, Phase 1 status: {detail['phases'][0]['status']}")
            assert detail["currentPhase"] == "BUILD"
            assert detail["phases"][0]["status"] == "RUNNING"

        publisher.publish(
            source_id="antigravity",
            source_kind="agent",
            kind="phase.completed",
            detail="BUILD complete",
            job_id=job_id,
            metadata={"phase": "BUILD", "commitSha": "sha_build_9918", "changedFilesCount": 5, "durationMs": 32000},
        )

        # Step 5: Phase 2 (HARDEN / Claude)
        print("[*] 5. Executing Phase 2: HARDEN (Agent: Claude)...")
        publisher.publish(
            source_id="claude",
            source_kind="agent",
            kind="phase.started",
            detail="Starting phase HARDEN",
            job_id=job_id,
            metadata={"phase": "HARDEN", "role": "hardener", "agent": "claude", "order": 2},
        )
        publisher.publish(
            source_id="claude",
            source_kind="agent",
            kind="phase.completed",
            detail="HARDEN complete",
            job_id=job_id,
            metadata={"phase": "HARDEN", "commitSha": "sha_harden_4421", "changedFilesCount": 2, "durationMs": 18500},
        )

        # Step 6: Phase 3 (VERIFY / Codex)
        print("[*] 6. Executing Phase 3: VERIFY (Agent: Codex)...")
        publisher.publish(
            source_id="codex",
            source_kind="agent",
            kind="phase.started",
            detail="Starting phase VERIFY",
            job_id=job_id,
            metadata={"phase": "VERIFY", "role": "verifier", "agent": "codex", "order": 3},
        )
        publisher.publish(
            source_id="codex",
            source_kind="agent",
            kind="phase.completed",
            detail="VERIFY complete",
            job_id=job_id,
            metadata={"phase": "VERIFY", "durationMs": 14200},
        )

        # Step 7: Complete sprint
        print("[*] 7. Completing sprint...")
        publisher.publish(
            source_id="hermes_runner",
            source_kind="runtime",
            kind="job.completed",
            detail="Sprint unigreen-inquiry-v1 completed successfully",
            job_id=job_id,
            metadata={"integrationCommit": "sha_final_integration_commit"},
        )

        # Step 8: Final verification
        with urllib.request.urlopen(f"{base_url}/jobs/{job_id}", timeout=1.0) as resp:
            final_detail = json.loads(resp.read().decode("utf-8"))
            print(f"    -> Final Job Status: {final_detail['status']}")
            print(f"    -> Phases: {[(p['name'], p['status'], p.get('commitSha')) for p in final_detail['phases']]}")
            print(f"    -> Artifacts: {[a['label'] for a in final_detail['artifacts']]}")
            assert final_detail["status"] == "COMPLETED"
            assert final_detail["progress"] == 1.0
            assert all(p["status"] == "SUCCEEDED" for p in final_detail["phases"])

        print("\n[SUCCESS] Phase 4 Real Job Lifecycle & Queue vertical slice verified end-to-end!")

    finally:
        server.should_exit = True
        server_thread.join(timeout=2.0)


if __name__ == "__main__":
    run_phase4_smoke_test()
