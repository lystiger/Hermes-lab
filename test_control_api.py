import asyncio
import json
import httpx
from main import app
from event_bus import event_bus, RuntimeEvent


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


def test_agents_endpoint():
    response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)
    assert len(agents) >= 3

    agent_ids = [a["id"] for a in agents]
    assert "gemini" in agent_ids
    assert "claude" in agent_ids
    assert "codex" in agent_ids

    for ag in agents:
        assert "id" in ag
        assert "displayName" in ag
        assert "provider" in ag
        assert "model" in ag
        assert "role" in ag
        assert "capabilities" in ag
        assert "status" in ag
        assert isinstance(ag["capabilities"], list)


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


def test_event_bus_subscription_and_delivery():
    queue = asyncio.Queue()
    event_bus.subscribe(queue)

    try:
        evt = event_bus.publish(
            source_id="codex",
            source_kind="agent",
            kind="tool.finished",
            detail="Codex pytest finished",
            duration="2.4s",
        )

        assert not queue.empty()
        received = queue.get_nowait()
        assert received.id == evt.id
        assert received.kind == "tool.finished"
        assert received.dur == "2.4s"
    finally:
        event_bus.unsubscribe(queue)

    # After unsubscribing, new events should not be queued
    evt2 = event_bus.publish(
        source_id="codex",
        source_kind="agent",
        kind="tool.finished",
        detail="Unsubscribed test",
    )
    assert queue.empty()
