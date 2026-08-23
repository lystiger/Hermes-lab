#!/usr/bin/env python3
import json
import socket
import sys
import threading
import time
import urllib.request
import uvicorn

from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app
from runner.control_plane.event_publisher import RuntimeEventPublisher


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_smoke_test():
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    print(f"[*] Starting LysStack control-plane process on {base_url}...")

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config=config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    time.sleep(1.0)

    try:
        # Step 1: Check /health
        print("[*] 1. Checking GET /health...")
        with urllib.request.urlopen(f"{base_url}/health", timeout=1.0) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            print(f"    -> Health response: {health}")
            assert health["status"] == "ok"

        # Step 2: Check initial /agents
        print("[*] 2. Checking initial GET /agents...")
        with urllib.request.urlopen(f"{base_url}/agents", timeout=1.0) as resp:
            agents = json.loads(resp.read().decode("utf-8"))
            claude = next(a for a in agents if a["id"] == "claude")
            print(f"    -> Claude initial status: {claude['status']}")
            assert claude["status"] == "IDLE"

        # Step 3: Runner Process B emits agent.started over HTTP IPC
        print("[*] 3. Runner (Process B) emitting 'agent.started' for Claude to POST /internal/events...")
        publisher = RuntimeEventPublisher(control_url=base_url)
        published = publisher.publish(
            source_id="claude",
            kind="agent.started",
            detail="Executing HARDEN security review on branch feat/redis-store",
            job_id="sprint-phase3",
            metadata={"phase": "HARDEN", "task": "Store Invariant Verification"},
        )
        assert published is True
        print("    -> Telemetry event accepted by LysStack control plane.")

        # Step 4: Verify /events contains the runner event
        print("[*] 4. Querying GET /events in control plane...")
        with urllib.request.urlopen(f"{base_url}/events?limit=5", timeout=1.0) as resp:
            events = json.loads(resp.read().decode("utf-8"))
            recent_event = next(e for e in events if e["kind"] == "agent.started" and e["source"]["id"] == "claude")
            print(f"    -> Found event in canonical history: [{recent_event['id']}] {recent_event['kind']} - {recent_event['detail']}")

        # Step 5: Verify /agents reflects RUNNING
        print("[*] 5. Querying GET /agents...")
        with urllib.request.urlopen(f"{base_url}/agents", timeout=1.0) as resp:
            agents = json.loads(resp.read().decode("utf-8"))
            claude_running = next(a for a in agents if a["id"] == "claude")
            print(f"    -> Claude active status: {claude_running['status']} (Task: {claude_running['currentTask']})")
            assert claude_running["status"] == "RUNNING"
            assert claude_running["currentTask"] == "Store Invariant Verification"

        # Step 6: Runner Process B emits agent.finished
        print("[*] 6. Runner (Process B) emitting 'agent.finished' for Claude...")
        publisher.publish(
            source_id="claude",
            kind="agent.finished",
            detail="HARDEN phase completed: Invariants verified",
            duration="3.18s",
            job_id="sprint-phase3",
        )

        # Step 7: Verify /agents returned to IDLE
        print("[*] 7. Querying GET /agents after completion...")
        with urllib.request.urlopen(f"{base_url}/agents", timeout=1.0) as resp:
            agents = json.loads(resp.read().decode("utf-8"))
            claude_idle = next(a for a in agents if a["id"] == "claude")
            print(f"    -> Claude completed status: {claude_idle['status']}")
            assert claude_idle["status"] == "IDLE"
            assert claude_idle["currentTask"] is None

        print("\n[SUCCESS] Entire cross-process vertical slice verified end-to-end!")

    finally:
        server.should_exit = True
        server_thread.join(timeout=2.0)


if __name__ == "__main__":
    run_smoke_test()
