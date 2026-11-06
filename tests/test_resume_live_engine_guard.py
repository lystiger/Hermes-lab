import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient

from main import app
from jobs.job_launcher import job_launcher
from jobs.job_service import job_service
from runtime.engine import ReactiveJobEngine
from runtime.job_state import JobState
from runtime.storage.config import get_global_event_store
from runtime.storage.schema_registry import create_event


def test_resume_refuses_409_when_engine_live(monkeypatch):
    client = TestClient(app)
    job_id = f"job_live_{uuid.uuid4().hex[:8]}"

    # Arrange: populate durable event store with an unfinished job
    store = get_global_event_store()
    asyncio.run(
        store.append(
            create_event(
                job_id=job_id,
                sequence=1,
                event_type="job.created",
                payload={
                    "goal": "Test live engine resume guard",
                    "title": "Live Engine Job",
                    "status": "EXECUTING",
                },
            )
        )
    )

    # Arrange: register a live engine for this job
    engine = ReactiveJobEngine(job_id=job_id, goal="Test live engine resume guard")
    engine.job.state = JobState.EXECUTING
    job_service.register_engine(engine)

    # Ensure engine is registered and not terminal
    assert job_service.get_engine(job_id) is not None
    assert not job_service.get_engine(job_id).job.is_terminal

    # Track calls to the background engine start path
    start_calls = []
    monkeypatch.setattr(
        job_launcher,
        "_start_engine_background",
        lambda eng: start_calls.append(eng),
    )

    # Initial start of the live engine
    job_launcher._start_engine_background(engine)
    assert len(start_calls) == 1

    try:
        # Act: attempt to resume a job whose engine is already live
        response = client.post(f"/jobs/{job_id}/resume")

        # Assert: must refuse with HTTP 409 Conflict
        assert response.status_code == 409

        # Assert: engine start path is not called a second time
        assert len(start_calls) == 1
    finally:
        # Clean up in-memory registrations and lease tasks
        job_service._engines.pop(job_id, None)
        job_service._jobs.pop(job_id, None)
        job_launcher._active_async_tasks.pop(job_id, None)
        lm_info = job_launcher._lease_managers.pop(job_id, None)
        if lm_info:
            _, task_hb, _ = lm_info
            task_hb.cancel()
