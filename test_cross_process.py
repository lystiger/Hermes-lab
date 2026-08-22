import socket
import threading
import time
import urllib.request
import json
import uvicorn
import pytest

from main import app
from runner.control_plane.event_publisher import RuntimeEventPublisher


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_cross_process_ipc_event_transport():
    """
    Verifies that a separate runner process (simulated via RuntimeEventPublisher over TCP)
    successfully communicates with the live Uvicorn/FastAPI control-plane process over HTTP IPC.
    """
    port = get_free_port()
    host = "127.0.0.1"
    base_url = f"http://{host}:{port}"

    # 1. Start real Uvicorn server in a separate background thread (simulating Process A)
    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config=config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    max_wait = 5.0
    start_time = time.time()
    server_ready = False
    while time.time() - start_time < max_wait:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.1)

    assert server_ready, "Uvicorn test server failed to start within timeout"

    try:
        # 2. Simulate Hermes Sprint Runner (Process B) publishing telemetry over HTTP IPC
        publisher = RuntimeEventPublisher(control_url=base_url, timeout=2.0)

        # Emit agent.started for codex
        published = publisher.publish(
            source_id="codex",
            kind="agent.started",
            detail="Running 186 test assertions in worktree sprint-ipc",
            job_id="sprint-ipc",
            metadata={"phase": "VERIFY", "task": "Test Execution"},
        )
        assert published is True

        # 3. Query control API process /events over real network
        with urllib.request.urlopen(f"{base_url}/events?limit=5", timeout=1.0) as resp:
            assert resp.status == 200
            events = json.loads(resp.read().decode("utf-8"))
            event_details = [e["detail"] for e in events]
            assert any("Running 186 test assertions" in d for d in event_details)

        # 4. Query control API process /agents over real network
        with urllib.request.urlopen(f"{base_url}/agents", timeout=1.0) as resp:
            assert resp.status == 200
            agents = json.loads(resp.read().decode("utf-8"))
            codex = next(a for a in agents if a["id"] == "codex")
            assert codex["status"] == "RUNNING"
            assert codex["currentTask"] == "Test Execution"

        # 5. Emit agent.finished for codex
        published_finish = publisher.publish(
            source_id="codex",
            kind="agent.finished",
            detail="186 tests passed in 14.2s",
            duration="14.2s",
            job_id="sprint-ipc",
        )
        assert published_finish is True

        # 6. Verify status in control API process returned to IDLE
        with urllib.request.urlopen(f"{base_url}/agents", timeout=1.0) as resp:
            assert resp.status == 200
            agents_after = json.loads(resp.read().decode("utf-8"))
            codex_after = next(a for a in agents_after if a["id"] == "codex")
            assert codex_after["status"] == "IDLE"
            assert codex_after["currentTask"] is None

    finally:
        # Stop background Uvicorn server
        server.should_exit = True
        server_thread.join(timeout=2.0)
