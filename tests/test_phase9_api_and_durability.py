import asyncio
import os
import pytest
from fastapi.testclient import TestClient

from main import app
from jobs.job_service import job_service, JobDetailDTO
from runtime.storage.config import (
    create_event_store,
    get_global_event_store,
    set_global_event_store,
    init_storage_lifespan,
    StorageUnavailableError,
)
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.schema_registry import create_event


@pytest.fixture
def test_client():
    return TestClient(app)


def test_historical_event_api_without_live_engine(test_client):
    """Requirement O: Historical event API returns persisted events even when no engine exists in memory."""
    store = get_global_event_store()
    job_id = "job_historical_999"

    # Populate store with persisted events
    async def _populate():
        await store.append(
            create_event(
                job_id=job_id,
                sequence=1,
                event_type="job.created",
                payload={"goal": "Durable Historical Sprint", "title": "Durable Job"},
            )
        )
        await store.append(
            create_event(
                job_id=job_id,
                sequence=2,
                event_type="task.created",
                task_id="T_hist_1",
                payload={"taskId": "T_hist_1", "description": "Database Migration"},
            )
        )
        await store.append(
            create_event(
                job_id=job_id,
                sequence=3,
                event_type="job.completed",
                payload={"detail": "Job completed durably"},
            )
        )

    asyncio.run(_populate())

    # Ensure engine is NOT in process memory
    assert job_service.get_engine(job_id) is None

    # 1. GET /jobs/{id}/events
    resp_events = test_client.get(f"/jobs/{job_id}/events")
    assert resp_events.status_code == 200
    events = resp_events.json()
    assert len(events) == 3
    assert events[0]["eventType"] == "job.created" or events[0]["event_type"] == "job.created"
    assert events[1]["taskId"] == "T_hist_1" or events[1]["task_id"] == "T_hist_1"
    assert events[2]["sequence"] == 3

    # 2. GET /jobs/{id} reconstructs job state from persisted store
    resp_job = test_client.get(f"/jobs/{job_id}")
    assert resp_job.status_code == 200
    job_data = resp_job.json()
    assert job_data["id"] == job_id
    assert job_data["status"] == "COMPLETED"
    assert job_data["title"] == "Durable Job"

    # 3. GET /jobs/{id}/tasks reconstructs task graph
    resp_tasks = test_client.get(f"/jobs/{job_id}/tasks")
    assert resp_tasks.status_code == 200
    tasks = resp_tasks.json()
    assert len(tasks) == 1
    assert tasks[0]["taskId"] == "T_hist_1"


@pytest.mark.anyio
async def test_startup_fails_fast_when_configured_postgres_is_unavailable(monkeypatch):
    """Requirement M: Configured Postgres unavailable -> explicit startup failure -> no silent memory fallback."""
    # Set unreachable Postgres URL and explicit backend
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://baduser:badpass@127.0.0.1:59999/baddb")
    monkeypatch.setenv("HERMES_STORAGE_BACKEND", "postgres")

    # Reset global store to force factory creation
    set_global_event_store(None)

    # init_storage_lifespan must fail fast with StorageUnavailableError
    with pytest.raises(StorageUnavailableError) as excinfo:
        await init_storage_lifespan()

    assert "PostgreSQL database is unavailable at startup" in str(excinfo.value)

    # Clean up environment
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("HERMES_STORAGE_BACKEND", raising=False)
    set_global_event_store(InMemoryRuntimeEventStore())


def test_compatibility_existing_phase8_endpoints(test_client):
    """Requirement P: Existing Phase 8 runtime endpoints remain fully functional with in-memory store."""
    # Health check
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Version & ready
    assert test_client.get("/ready").status_code == 200
    assert test_client.get("/version").status_code == 200
