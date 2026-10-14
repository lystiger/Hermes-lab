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


def real_publisher(monkeypatch, delay=0.0, explode=False):
    """The real RuntimeEventPublisher with only its HTTP transport stubbed."""
    import time as _time
    from control_plane.event_publisher import RuntimeEventPublisher

    publisher = RuntimeEventPublisher(control_url="http://hermes.test")
    posts = []

    def post(path, payload):
        if delay:
            _time.sleep(delay)
        if explode:
            raise RuntimeError("api down")
        posts.append(payload)
        return True

    monkeypatch.setattr(publisher, "_post_json", post)
    monkeypatch.setattr(RUNNER_MODULE, "default_publisher", publisher)
    return posts


def make_runner():
    return RUNNER_MODULE.HermesSprintRunner(
        spec_path=Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json",
        dry_run=True,
        skip_agent_exec=True,
    )


def seat_event(kind=events.RESOURCE_ACQUIRED, execution_id="exec-r1"):
    return ExecutionEvent(
        kind=kind, job_id="lab-s03", detail="seat event",
        metadata={"backend": "openrig", "executionId": execution_id,
                  "resource": {"kind": "seat", "id": "01SEAT", "label": "worker"}},
    )


def test_runner_sink_posts_through_the_real_publisher_with_the_runner_job_and_phase(monkeypatch):
    posts = real_publisher(monkeypatch)
    runner = make_runner()
    runner._current_phase = {"name": "build", "agent": "claude"}

    runner._publish_execution_event(seat_event())
    runner._flush_execution_events()

    [payload] = posts
    assert payload["kind"] == events.RESOURCE_ACQUIRED
    assert payload["source"] == {"id": "openrig", "kind": "runtime", "displayName": "Openrig", "accentColor": None}
    assert payload["jobId"] == runner.job_id and runner.job_id != "lab-s03"
    assert (payload["taskId"], payload["actorId"]) == ("build", "claude")


def test_late_events_keep_the_phase_that_started_their_execution(monkeypatch):
    posts = real_publisher(monkeypatch)
    runner = make_runner()
    runner._current_phase = {"name": "phase1", "agent": "claude"}
    runner._publish_execution_event(seat_event(events.STARTED, "exec-1"))
    runner._current_phase = {"name": "phase2", "agent": "codex"}
    # Phase one's pooled seat expires while phase two runs.
    runner._publish_execution_event(seat_event(events.RESOURCE_RELEASED, "exec-1"))
    runner._publish_execution_event(seat_event(events.STARTED, "exec-2"))
    runner._flush_execution_events()

    assert [(p["taskId"], p["actorId"]) for p in posts] == [
        ("phase1", "claude"), ("phase1", "claude"), ("phase2", "codex"),
    ]


def test_a_slow_or_failing_api_never_delays_or_fails_a_phase(monkeypatch):
    import time as _time

    real_publisher(monkeypatch, delay=0.5)
    runner = make_runner()
    started = _time.monotonic()
    for _ in range(5):
        runner._publish_execution_event(seat_event())
    assert _time.monotonic() - started < 0.2  # queued, not posted inline

    real_publisher(monkeypatch, explode=True)
    failing = make_runner()
    failing._publish_execution_event(seat_event())
    failing._flush_execution_events(timeout=1)  # must not raise


def test_a_disabled_publisher_is_a_no_op(monkeypatch):
    from control_plane.event_publisher import RuntimeEventPublisher

    monkeypatch.delenv("LYSSTACK_CONTROL_URL", raising=False)
    monkeypatch.setattr(RUNNER_MODULE, "default_publisher", RuntimeEventPublisher(control_url=""))
    runner = make_runner()
    runner._publish_execution_event(seat_event())
    assert runner.__dict__.get("_exec_event_q") is None


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
