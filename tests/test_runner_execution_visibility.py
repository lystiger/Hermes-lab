"""Sprint-runner executions reach the Execution page: runner sink -> POST /internal/events -> bus + registry."""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from runner.backends import events
from runner.backends.events import ExecutionEvent
from runner.backends.execution_registry import default_execution_registry

RUNNER_PATH = Path(__file__).resolve().parent.parent / "runner" / "run-hermes-sprint.py"
SPEC = importlib.util.spec_from_file_location("run_hermes_sprint_visibility", RUNNER_PATH)
RUNNER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER_MODULE)


class RecordingPublisher:
    def __init__(self, enabled=True, explode=False):
        self._enabled, self.explode, self.calls = enabled, explode, []

    def enabled(self):
        return self._enabled

    def publish(self, **kwargs):
        if self.explode:
            raise RuntimeError("api down")
        self.calls.append(kwargs)
        return True


def make_runner():
    return RUNNER_MODULE.HermesSprintRunner(
        spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
        dry_run=True,
        skip_agent_exec=True,
    )


def seat_event(kind=events.RESOURCE_ACQUIRED):
    return ExecutionEvent(
        kind=kind, job_id=None, detail="seat acquired",
        metadata={"backend": "openrig", "executionId": "exec-r1",
                  "resource": {"kind": "seat", "id": "01SEAT", "label": "worker"}},
    )


def test_runner_sink_posts_execution_events_tagged_with_the_running_phase(monkeypatch):
    publisher = RecordingPublisher()
    monkeypatch.setattr(RUNNER_MODULE, "default_publisher", publisher)
    runner = make_runner()
    runner._current_phase = {"name": "build", "agent": "claude"}

    runner._publish_execution_event(seat_event())

    [call] = publisher.calls
    assert call["kind"] == events.RESOURCE_ACQUIRED
    assert call["source_kind"] == "runtime" and call["source_id"] == "openrig"
    assert call["task_id"] == "build" and call["actor_id"] == "claude"
    assert call["job_id"] == runner.job_id
    assert call["metadata"]["resource"]["id"] == "01SEAT"


def test_runner_sink_never_fails_a_phase(monkeypatch):
    monkeypatch.setattr(RUNNER_MODULE, "default_publisher", RecordingPublisher(explode=True))
    make_runner()._publish_execution_event(seat_event())  # must not raise
    monkeypatch.setattr(RUNNER_MODULE, "default_publisher", RecordingPublisher(enabled=False))
    make_runner()._publish_execution_event(seat_event())


def test_internal_execution_events_feed_the_snapshot_and_carry_task_ids():
    from main import app

    client = TestClient(app)
    response = client.post("/internal/events", json={
        "source": {"id": "openrig", "kind": "runtime"},
        "kind": "execution.resource_acquired",
        "detail": "seat acquired",
        "jobId": "sprint-job-1",
        "taskId": "build",
        "actorId": "claude",
        "metadata": {"backend": "openrig", "executionId": "exec-int-1",
                     "resource": {"kind": "seat", "id": "01INTERNALSEAT", "label": "worker"}},
    })
    assert response.status_code == 202

    rows = [r for r in default_execution_registry.resources() if r["id"] == "01INTERNALSEAT"]
    assert rows and rows[0]["taskId"] == "build" and rows[0]["state"] == "acquiring"

    wire = client.get("/events", params={"limit": 5}).json()
    mine = [e for e in wire if e["kind"] == "execution.resource_acquired" and e.get("taskId") == "build"]
    assert mine and mine[-1]["actorId"] == "claude"


def test_internal_non_execution_events_never_touch_the_registry():
    from main import app

    before = default_execution_registry.resources()
    TestClient(app).post("/internal/events", json={
        "source": {"id": "claude", "kind": "agent"}, "kind": "phase.started", "detail": "x",
        "metadata": {"resource": {"kind": "seat", "id": "01NOPE", "label": "x"}},
    })
    assert default_execution_registry.resources() == before
