import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import pytest

from runner.control_plane.event_publisher import RuntimeEventPublisher


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_subprocess_cross_process_ipc():
    """
    Verifies that a separate runner process (simulated via RuntimeEventPublisher)
    successfully communicates with an independent OS subprocess running Uvicorn/FastAPI.
    """
    port = get_free_port()
    host = "127.0.0.1"
    base_url = f"http://{host}:{port}"
    root_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Start real independent Uvicorn OS subprocess (Process A)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=root_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait for the independent OS process to bind and respond to /health
        max_wait = 6.0
        start_time = time.time()
        server_ready = False
        while time.time() - start_time < max_wait:
            if proc.poll() is not None:
                _, stderr = proc.communicate()
                pytest.fail(f"Uvicorn subprocess exited prematurely: {stderr.decode('utf-8')}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as resp:
                    if resp.status == 200:
                        server_ready = True
                        break
            except Exception:
                time.sleep(0.15)

        assert server_ready, "Uvicorn subprocess failed to become ready within timeout"

        # 2. In this test process (Process B), publish telemetry over HTTP IPC to the subprocess
        publisher = RuntimeEventPublisher(control_url=base_url, timeout=2.0)

        # Emit agent.started for codex
        published = publisher.publish(
            source_id="codex",
            kind="agent.started",
            detail="Running 186 test assertions in worktree sprint-ipc",
            job_id="sprint-ipc",
            metadata={"phase": "VERIFY", "task": "Subprocess Test Execution"},
        )
        assert published is True

        # 3. Query subprocess control API /events over TCP socket
        with urllib.request.urlopen(f"{base_url}/events?limit=5", timeout=1.0) as resp:
            assert resp.status == 200
            events = json.loads(resp.read().decode("utf-8"))
            event_details = [e["detail"] for e in events]
            assert any("Running 186 test assertions" in d for d in event_details)

        # 4. Query subprocess control API /agents over TCP socket
        with urllib.request.urlopen(f"{base_url}/agents", timeout=1.0) as resp:
            assert resp.status == 200
            agents = json.loads(resp.read().decode("utf-8"))
            codex = next(a for a in agents if a["id"] == "codex")
            assert codex["status"] == "RUNNING"
            assert codex["currentTask"] == "Subprocess Test Execution"

        # 5. Emit agent.finished for codex
        published_finish = publisher.publish(
            source_id="codex",
            kind="agent.finished",
            detail="186 tests passed in 14.2s",
            duration="14.2s",
            job_id="sprint-ipc",
        )
        assert published_finish is True

        # 6. Verify status in subprocess returned to IDLE
        with urllib.request.urlopen(f"{base_url}/agents", timeout=1.0) as resp:
            assert resp.status == 200
            agents_after = json.loads(resp.read().decode("utf-8"))
            codex_after = next(a for a in agents_after if a["id"] == "codex")
            assert codex_after["status"] == "IDLE"
            assert codex_after["currentTask"] is None

    finally:
        # Terminate and clean up the independent OS process
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
