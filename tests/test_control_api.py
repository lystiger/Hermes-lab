import asyncio
import json
import httpx
import pytest
from main import app
from events.event_bus import event_bus
from personas.agent_service import agent_service
from jobs.job_service import job_service
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


def test_agents_endpoint_is_registry_driven():
    response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)
    agent_ids = [a["id"] for a in agents]
    assert "gemini" in agent_ids
    assert "claude" in agent_ids
    assert "codex" in agent_ids
    assert "elysia" not in agent_ids


def test_job_lifecycle_reduction_and_querying():
    job_id = "run_test_unigreen_01"

    # 1. job.created
    res_create = client.post(
        "/internal/events",
        json_data={
            "source": {"id": "hermes_runner", "kind": "runtime"},
            "kind": "job.created",
            "detail": "Sprint unigreen-inquiry-v1 initialized",
            "jobId": job_id,
            "metadata": {
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
        },
    )
    assert res_create.status_code == 202

    # Query /jobs
    jobs_res = client.get("/jobs")
    assert jobs_res.status_code == 200
    jobs = jobs_res.json()
    job_item = next(j for j in jobs if j["id"] == job_id)
    assert job_item["sprintId"] == "unigreen-inquiry-v1"
    assert job_item["title"] == "Unigreen Inquiry Delivery"
    assert job_item["assignedAgentIds"] == ["gemini", "claude", "codex"]

    # 2. job.started
    client.post(
        "/internal/events",
        json_data={
            "source": {"id": "hermes_runner", "kind": "runtime"},
            "kind": "job.started",
            "detail": "Execution started",
            "jobId": job_id,
        },
    )

    detail_res = client.get(f"/jobs/{job_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["status"] == "RUNNING"
    assert len(detail["phases"]) == 3
    assert detail["phases"][0]["name"] == "BUILD"
    assert detail["phases"][0]["status"] == "PENDING"
    assert detail["phases"][0]["agentId"] == "gemini"

    # 3. phase.started for BUILD
    client.post(
        "/internal/events",
        json_data={
            "source": {"id": "antigravity", "kind": "agent"},
            "kind": "phase.started",
            "detail": "Starting phase BUILD",
            "jobId": job_id,
            "metadata": {"phase": "BUILD", "role": "builder", "agent": "antigravity"},
        },
    )

    detail_p1 = client.get(f"/jobs/{job_id}").json()
    assert detail_p1["currentPhase"] == "BUILD"
    assert detail_p1["phases"][0]["status"] == "RUNNING"

    # 4. phase.completed for BUILD
    client.post(
        "/internal/events",
        json_data={
            "source": {"id": "antigravity", "kind": "agent"},
            "kind": "phase.completed",
            "detail": "Phase BUILD completed",
            "jobId": job_id,
            "metadata": {
                "phase": "BUILD",
                "role": "builder",
                "commitSha": "abc1234567890",
                "changedFilesCount": 3,
                "durationMs": 45000,
            },
        },
    )

    detail_p1_done = client.get(f"/jobs/{job_id}").json()
    assert detail_p1_done["phases"][0]["status"] == "SUCCEEDED"
    assert detail_p1_done["phases"][0]["commitSha"] == "abc1234567890"

    # 5. job.completed
    client.post(
        "/internal/events",
        json_data={
            "source": {"id": "hermes_runner", "kind": "runtime"},
            "kind": "job.completed",
            "detail": "Sprint completed successfully",
            "jobId": job_id,
            "metadata": {"integrationCommit": "fedcba987654"},
        },
    )

    final_detail = client.get(f"/jobs/{job_id}").json()
    assert final_detail["status"] == "COMPLETED"
    assert final_detail["progress"] == 1.0
    assert len(final_detail["artifacts"]) > 0
    assert final_detail["artifacts"][0]["ref"] == "fedcba987654"


def test_job_not_found_returns_404():
    res = client.get("/jobs/non_existent_job_xyz")
    assert res.status_code == 404


def test_post_jobs_security_validation():
    # 1. Invalid sprint ID format
    bad_res1 = client.post("/jobs", json_data={"sprintId": "../../../etc/passwd"})
    assert bad_res1.status_code == 400

    # 2. Unknown sprint ID
    bad_res2 = client.post("/jobs", json_data={"sprintId": "unknown_sprint_999"})
    assert bad_res2.status_code == 400


def test_publisher_failure_isolation():
    publisher = RuntimeEventPublisher(control_url="http://127.0.0.1:59999", timeout=0.2)
    assert publisher.publish("claude", "agent.started", "Dead URL test") is False


def test_reactive_runtime_query_endpoints():
    from runtime import ReactiveJobEngine, TaskNode, TaskExecutionResult, Observation

    jid = "job_reactive_api_test"
    engine = ReactiveJobEngine(
        job_id=jid,
        goal="API testing for reactive tasks and observations",
    )
    t1 = TaskNode(task_id="T1", job_id=jid, description="API Task 1", required_capabilities=["implementation"])
    engine.graph.add_task(t1)
    engine.observation_registry.add_observation(job_id=jid, kind="discovery", content="API observation content", task_id="T1")

    job_service.register_engine(engine)

    # 1. GET /jobs/{id}
    job_res = client.get(f"/jobs/{jid}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["id"] == jid
    assert len(job_data["tasks"]) == 1
    assert job_data["tasks"][0]["task_id"] == "T1"

    # 2. GET /jobs/{id}/tasks
    tasks_res = client.get(f"/jobs/{jid}/tasks")
    assert tasks_res.status_code == 200
    tasks_data = tasks_res.json()
    assert len(tasks_data) == 1
    assert tasks_data[0]["task_id"] == "T1"

    # 3. GET /jobs/{id}/observations
    obs_res = client.get(f"/jobs/{jid}/observations")
    assert obs_res.status_code == 200
    obs_data = obs_res.json()
    assert len(obs_data) == 1
    assert obs_data[0]["content"] == "API observation content"

    # 4. GET /jobs/{id}/events
    events_res = client.get(f"/jobs/{jid}/events")
    assert events_res.status_code == 200
