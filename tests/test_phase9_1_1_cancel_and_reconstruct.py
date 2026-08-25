import asyncio
import copy
from fastapi.testclient import TestClient
import pytest
import uuid

from main import app
from jobs.job_service import job_service
from runtime.events import RuntimeEventBridge
from runtime.job_state import JobState
from runtime.storage.config import get_global_event_store
from runtime.storage.projector import RuntimeStateProjector
from runtime.task_graph import TaskStatus
from runtime.execution import AgentRunStatus


@pytest.fixture
def client():
    return TestClient(app)


def test_post_jobs_persists_job_created_before_acknowledging(client):
    """
    Scenario: POST /jobs must persist job.created and initial tasks into the durable event ledger
    BEFORE acknowledging 202 Accepted.
    """
    response = client.post(
        "/jobs",
        json={"sprintId": "lab-s02", "dryRun": True},
    )
    assert response.status_code == 202
    data = response.json()
    job_id = data["jobId"]
    assert job_id is not None

    # Query events directly from /jobs/{id}/events or store
    events_resp = client.get(f"/jobs/{job_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) >= 1

    event_types = [e["event_type"] for e in events]
    assert "job.created" in event_types
    assert events[0]["sequence"] == 1


def test_cancel_job_and_reconstruct_completely_from_store(client):
    """
    Scenario: Route POST /jobs/{job_id}/cancel through launcher, verify no double task.cancelled events,
    and reconstruct the complete session exclusively from the durable store.
    """
    import asyncio
    from runtime.engine import ReactiveJobEngine
    from runtime.task_graph import TaskNode
    from runtime.execution import AgentRun, TaskExecutionResult

    job_id = f"job_api_cancel_{uuid.uuid4().hex[:8]}"
    store = get_global_event_store()
    bridge = RuntimeEventBridge(event_store=store)

    engine = ReactiveJobEngine(
        job_id=job_id,
        goal="Test endpoint cancel",
        event_bridge=bridge,
    )

    t1 = TaskNode(task_id="T1_long", job_id=job_id, description="Long task")
    t2 = TaskNode(task_id="T2_dep", job_id=job_id, description="Dep task", dependencies=["T1_long"])

    async def _setup():
        await engine.initialize_and_plan(initial_tasks=[t1, t2])
    asyncio.run(_setup())

    job_service.register_engine(engine)

    # 1. Cancel the active job via API endpoint
    cancel_resp = client.post(f"/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["cancelled"] is True
    assert engine.state == JobState.CANCELLED

    # 2. Retrieve event ledger from API
    events_resp = client.get(f"/jobs/{job_id}/events")
    assert events_resp.status_code == 200
    event_dtos = events_resp.json()
    assert len(event_dtos) >= 2

    # 3. Verify no double task.cancelled for any single task
    task_cancelled_events = [e for e in event_dtos if e["event_type"] == "task.cancelled"]
    task_ids_cancelled = [e.get("task_id") or e.get("payload", {}).get("taskId") for e in task_cancelled_events]
    assert len(task_ids_cancelled) == len(set(task_ids_cancelled)), "No task should have duplicate task.cancelled events"

    # 4. Reconstruct exclusively from stored events using RuntimeStateProjector
    from runtime.storage.schema_registry import StoredRuntimeEvent
    stored_events = [StoredRuntimeEvent.from_dict(e) for e in event_dtos]
    reconstructed = RuntimeStateProjector.project(stored_events)

    assert reconstructed.job.state == JobState.CANCELLED
    assert reconstructed.job.job_id == job_id

    # Verify no tasks or runs are left in RUNNING, READY, or PENDING state
    for task in reconstructed.graph.list_tasks():
        assert task.status == TaskStatus.CANCELLED

    for run in reconstructed.runs:
        assert run.status == AgentRunStatus.CANCELLED
