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


def test_subprocess_cross_process_job_lifecycle():
    """
    Verifies that a separate runner process emits job & phase lifecycle telemetry
    over HTTP IPC to an independent OS subprocess running Uvicorn/FastAPI.
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

        # 2. Simulate Hermes Sprint Runner (Process B) publishing job telemetry over HTTP IPC
        publisher = RuntimeEventPublisher(control_url=base_url, timeout=2.0)
        job_id = "run_ipc_unigreen_s01"

        # Emit job.created
        publisher.publish(
            source_id="hermes_runner",
            source_kind="runtime",
            kind="job.created",
            detail="Sprint unigreen-inquiry-v1 initialized",
            job_id=job_id,
            metadata={
                "sprintId": "unigreen-inquiry-v1",
                "title": "Unigreen Inquiry Delivery",
                "repository": "Unigreen",
                "branch": "hermes/unigreen-inquiry-v1/integration",
                "phases": [
                    {"name": "BUILD", "role": "builder", "agent": "antigravity"},
                    {"name": "HARDEN", "role": "hardener", "agent": "claude"},
                    {"name": "VERIFY", "role": "verifier", "agent": "codex"},
                ],
            },
        )

        # Emit job.started
        publisher.publish(
            source_id="hermes_runner",
            source_kind="runtime",
            kind="job.started",
            detail="Execution started",
            job_id=job_id,
        )

        # 3. Query subprocess /jobs over network
        with urllib.request.urlopen(f"{base_url}/jobs", timeout=1.0) as resp:
            assert resp.status == 200
            jobs = json.loads(resp.read().decode("utf-8"))
            ipc_job = next(j for j in jobs if j["id"] == job_id)
            assert ipc_job["status"] == "RUNNING"
            assert ipc_job["assignedAgentIds"] == ["gemini", "claude", "codex"]

        # 4. Emit phase.started for BUILD
        publisher.publish(
            source_id="antigravity",
            source_kind="agent",
            kind="phase.started",
            detail="Starting phase BUILD",
            job_id=job_id,
            metadata={"phase": "BUILD", "role": "builder", "agent": "antigravity"},
        )

        # Query /jobs/:id
        with urllib.request.urlopen(f"{base_url}/jobs/{job_id}", timeout=1.0) as resp:
            assert resp.status == 200
            job_detail = json.loads(resp.read().decode("utf-8"))
            assert job_detail["currentPhase"] == "BUILD"
            assert job_detail["phases"][0]["status"] == "RUNNING"

        # 5. Emit phase.completed for BUILD
        publisher.publish(
            source_id="antigravity",
            source_kind="agent",
            kind="phase.completed",
            detail="Phase BUILD complete",
            job_id=job_id,
            metadata={"phase": "BUILD", "commitSha": "sha_111222333", "changedFilesCount": 4},
        )

        # 6. Emit job.completed
        publisher.publish(
            source_id="hermes_runner",
            source_kind="runtime",
            kind="job.completed",
            detail="Sprint finished successfully",
            job_id=job_id,
            metadata={"integrationCommit": "sha_final_commit"},
        )

        # 7. Verify terminal state in subprocess
        with urllib.request.urlopen(f"{base_url}/jobs/{job_id}", timeout=1.0) as resp:
            assert resp.status == 200
            final_job = json.loads(resp.read().decode("utf-8"))
            assert final_job["status"] == "COMPLETED"
            assert final_job["phases"][0]["status"] == "SUCCEEDED"
            assert final_job["phases"][0]["commitSha"] == "sha_111222333"
            assert any(a["ref"] == "sha_final_commit" for a in final_job["artifacts"])

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
