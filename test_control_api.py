import asyncio
import json
import httpx
import pytest
from main import app
from event_bus import event_bus, RuntimeEvent
from agent_service import agent_service
from runner.control_plane.event_publisher import RuntimeEventPublisher


class ASGITestClient:
    @staticmethod
    def get(path, headers=None, params=None):
        async def perform_request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as async_client:
                return await async_client.get(path, headers=headers, params=params)

        return asyncio.run(perform_request())

    @staticmethod
    def post(path, json_data=None, headers=None):
        async def perform_request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as async_client:
                return await async_client.post(path, json=json_data, headers=headers)

        return asyncio.run(perform_request())


client = ASGITestClient()


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "lysstack"
    assert "version" in data
    assert "uptimeSeconds" in data
    assert "timestamp" in data


def test_agents_endpoint_is_registry_driven():
    response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)
    assert len(agents) >= 3

    agent_ids = [a["id"] for a in agents]
    # Verify antigravity mapped to gemini
    assert "gemini" in agent_ids
    assert "claude" in agent_ids
    assert "codex" in agent_ids

    # Elysia must NOT be fake-registered if not in registry
    assert "elysia" not in agent_ids

    for ag in agents:
        assert "id" in ag
        assert "displayName" in ag
        assert "provider" in ag
        assert "model" in ag
        assert "role" in ag
        assert "capabilities" in ag
        assert "status" in ag
        assert isinstance(ag["capabilities"], list)


def test_internal_events_ingress_and_state_reduction():
    # 1. Start agent execution for claude
    start_payload = {
        "source": {
            "id": "claude",
            "kind": "agent",
            "displayName": "Claude",
        },
        "kind": "agent.started",
        "detail": "Reviewing security architecture in worktree sprint-01",
        "jobId": "sprint-01",
        "metadata": {"phase": "HARDEN", "task": "Store Review"},
    }

    res_start = client.post("/internal/events", json_data=start_payload)
    assert res_start.status_code == 202
    data_start = res_start.json()
    assert data_start["accepted"] is True
    assert data_start["eventId"].startswith("evt_")
    assert data_start["normalizedSourceId"] == "claude"

    # Verify agent status changed to RUNNING
    agents_res = client.get("/agents")
    agents = agents_res.json()
    claude = next(a for a in agents if a["id"] == "claude")
    assert claude["status"] == "RUNNING"
    assert claude["currentTask"] == "Store Review"

    # Verify event appears in /events
    events_res = client.get("/events?limit=5")
    events = events_res.json()
    event_ids = [e["id"] for e in events]
    assert data_start["eventId"] in event_ids

    # 2. Finish agent execution for claude
    finish_payload = {
        "source": {
            "id": "claude",
            "kind": "agent",
        },
        "kind": "agent.finished",
        "detail": "Phase HARDEN completed successfully",
        "duration": "4.21s",
        "jobId": "sprint-01",
    }

    res_finish = client.post("/internal/events", json_data=finish_payload)
    assert res_finish.status_code == 202

    # Verify agent status returned to IDLE
    agents_res_after = client.get("/agents")
    claude_after = next(a for a in agents_res_after.json() if a["id"] == "claude")
    assert claude_after["status"] == "IDLE"
    assert claude_after["currentTask"] is None


def test_internal_events_antigravity_normalization():
    payload = {
        "source": {
            "id": "antigravity",
            "kind": "agent",
        },
        "kind": "agent.started",
        "detail": "Building vehicle state store migration",
        "jobId": "sprint-02",
        "metadata": {"phase": "BUILD"},
    }

    res = client.post("/internal/events", json_data=payload)
    assert res.status_code == 202
    data = res.json()
    assert data["normalizedSourceId"] == "gemini"

    # Check gemini agent status is RUNNING
    agents = client.get("/agents").json()
    gemini = next(a for a in agents if a["id"] == "gemini")
    assert gemini["status"] == "RUNNING"

    # Send failed event
    fail_payload = {
        "source": {
            "id": "antigravity",
            "kind": "agent",
        },
        "kind": "agent.failed",
        "detail": "Build failed on pytest syntax check",
        "duration": "1.2s",
        "jobId": "sprint-02",
    }
    client.post("/internal/events", json_data=fail_payload)

    # Check gemini status is ERROR
    agents_failed = client.get("/agents").json()
    gemini_failed = next(a for a in agents_failed if a["id"] == "gemini")
    assert gemini_failed["status"] == "ERROR"

    # Reset gemini to IDLE for subsequent tests
    agent_service.set_agent_status("gemini", "IDLE")


def test_internal_events_invalid_payload_rejected():
    invalid_payload = {
        "source": {
            "id": "gemini",
            "kind": "invalid_kind_foo",  # invalid enum
        },
        "kind": "agent.started",
        "detail": "Testing rejection",
    }

    res = client.post("/internal/events", json_data=invalid_payload)
    assert res.status_code == 422  # Unprocessable Entity


def test_publisher_failure_isolation():
    # 1. When URL is unset, publish returns False without raising
    no_url_publisher = RuntimeEventPublisher(control_url=None)
    assert no_url_publisher.publish("claude", "agent.started", "No URL test") is False

    # 2. When URL is unreachable, publish catches error, logs warning, returns False without crashing
    dead_url_publisher = RuntimeEventPublisher(control_url="http://127.0.0.1:59999", timeout=0.2)
    assert dead_url_publisher.publish("claude", "agent.started", "Dead URL test") is False


def test_events_endpoint_and_event_bus():
    evt1 = event_bus.publish(
        source_id="test_runner",
        source_kind="system",
        kind="test.step_1",
        detail="Executing step 1 in test",
    )
    evt2 = event_bus.publish(
        source_id="gemini",
        source_kind="agent",
        kind="agent.started",
        detail="Gemini starting task",
    )

    response = client.get("/events?limit=10")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 2

    ids = [e["id"] for e in events]
    assert evt1.id in ids
    assert evt2.id in ids

    response_after = client.get(f"/events?after={evt1.id}")
    assert response_after.status_code == 200
    after_events = response_after.json()
    after_ids = [e["id"] for e in after_events]
    assert evt1.id not in after_ids
    assert evt2.id in after_ids
