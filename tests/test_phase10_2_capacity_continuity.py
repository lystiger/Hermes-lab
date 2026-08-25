import asyncio
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from runtime.capacity import (
    CapacityRegistry,
    ProviderStatus,
    ProviderFailureClass,
    default_capacity_registry,
)
from runtime.task_graph import TaskNode, TaskStatus
from runtime.observations import Observation, ObservationRegistry
from runtime.hermes_adapter import HermesActorAdapter
from runtime.execution import AgentRun


@pytest.mark.anyio
async def test_capacity_registry_telemetry_reporting():
    """
    Verifies CapacityRegistry aggregates token usage, provider success/failure counts,
    failure breakdowns by class, and throttling occurrences.
    """
    registry = CapacityRegistry()
    registry.register_actor_provider("claude_sonnet", "anthropic")
    registry.register_actor_provider("gemini_pro", "google")

    # 1. Record usage on anthropic
    registry.record_usage(
        provider_id="anthropic",
        job_id="job_alpha",
        actor_id="claude_sonnet",
        input_tokens=1500,
        output_tokens=300,
        cached_tokens=200,
    )
    registry.record_provider_success("anthropic")

    # 2. Record rate limit failure on anthropic
    registry.record_provider_failure(
        provider_id="anthropic",
        failure_class=ProviderFailureClass.RATE_LIMITED,
        retry_after_seconds=30.0,
        reason="429 Rate limit exceeded",
    )

    # 3. Record success on google
    registry.record_usage(
        provider_id="google",
        job_id="job_alpha",
        actor_id="gemini_pro",
        input_tokens=800,
        output_tokens=150,
        cached_tokens=0,
    )
    registry.record_provider_success("google")

    # 4. Ingest report
    report = registry.get_telemetry_report()
    summary = report["summary"]
    assert summary["total_providers"] == 2
    assert summary["total_tokens"] == (1500 + 300 + 800 + 150)
    assert summary["input_tokens"] == 2300
    assert summary["output_tokens"] == 450
    assert summary["cached_tokens"] == 200
    assert summary["total_throttling_events"] == 1
    assert summary["total_failures"] == 1

    # Provider breakdown
    anthropic_data = report["providers"]["anthropic"]
    assert anthropic_data["status"] == "throttled"
    assert anthropic_data["throttling_count"] == 1
    assert anthropic_data["failure_breakdown"]["rate_limited"] == 1
    assert anthropic_data["total_requests"] == 2
    assert anthropic_data["success_count"] == 1
    assert anthropic_data["failure_count"] == 1
    assert anthropic_data["success_rate"] == 0.5

    # Job telemetry
    job_tel = registry.get_job_telemetry("job_alpha")
    assert job_tel["tokens"]["total_tokens"] == (1500 + 300 + 800 + 150)
    assert job_tel["tokens"]["cached_tokens"] == 200


@pytest.mark.anyio
async def test_control_api_capacity_telemetry_endpoints():
    """
    Verifies /capacity/telemetry and /jobs/{job_id}/telemetry endpoints.
    """
    default_capacity_registry.reset_telemetry()
    default_capacity_registry.register_actor_provider("agent_x", "provider_test")
    default_capacity_registry.record_usage(
        provider_id="provider_test",
        job_id="job_test_api",
        actor_id="agent_x",
        input_tokens=100,
        output_tokens=50,
    )
    default_capacity_registry.record_provider_success("provider_test")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # GET /capacity/telemetry
        res = await client.get("/capacity/telemetry")
        assert res.status_code == 200
        data = res.json()
        assert "summary" in data
        assert data["summary"]["total_tokens"] == 150
        assert "provider_test" in data["providers"]

        # GET /jobs/{job_id}/telemetry
        res_job = await client.get("/jobs/job_test_api/telemetry")
        assert res_job.status_code == 200
        data_job = res_job.json()
        assert data_job["job_id"] == "job_test_api"
        assert data_job["tokens"]["total_tokens"] == 150


def test_context_continuity_section_generation():
    """
    Verifies build_continuity_section correctly renders reroute notices,
    prior attempt errors, and structured observations.
    """
    adapter = HermesActorAdapter()
    task = TaskNode(
        task_id="T_CONT",
        job_id="job_cont_1",
        description="Implement payment processor",
        attempt=1,
        error="SyntaxError: invalid syntax at line 42",
        metadata={
            "previous_actor": "antigravity",
            "last_reroute_reason": "rate_limit_exceeded",
        },
    )

    obs1 = Observation(
        job_id="job_cont_1",
        task_id="T_CONT",
        kind="discovery",
        content="Discovered Stripe API version is 2026-08-01",
    )
    obs2 = Observation(
        job_id="job_cont_1",
        task_id="T_CONT",
        kind="constraint",
        content="Requires idempotency key header on all POST requests",
    )

    prior_runs = [
        {"run_id": "run_1", "status": "failed", "exit_reason": "syntax_error"}
    ]

    effective_prompt = adapter.build_effective_prompt(
        base_prompt="Write the payment module.",
        current_agent="claude",
        role="builder",
        task=task,
        observations=[obs1, obs2],
        failure_history=prior_runs,
    )

    assert "--- LYSSTACK CONTINUITY CONTEXT ---" in effective_prompt
    assert "[Reroute Notice] Execution rerouted from 'antigravity'. Reason: rate_limit_exceeded" in effective_prompt
    assert "[Previous Failure (Attempt 1)]" in effective_prompt
    assert "SyntaxError: invalid syntax at line 42" in effective_prompt
    assert "- [discovery] Discovered Stripe API version is 2026-08-01" in effective_prompt
    assert "- [constraint] Requires idempotency key header on all POST requests" in effective_prompt
    assert "- Run run_1: status=failed, exit_reason=syntax_error" in effective_prompt
    assert "--- END CONTINUITY CONTEXT ---" in effective_prompt
    assert "Write the payment module." in effective_prompt
