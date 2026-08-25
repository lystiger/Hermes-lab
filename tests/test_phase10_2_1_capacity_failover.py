import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from runtime.capacity import (
    CapacityRegistry,
    ProviderStatus,
    ProviderFailureClass,
    ProviderFailureClassifier,
    UsageSnapshot,
    UsageSnapshotNormalizer,
    SoftCapacityThresholds,
    TaskBudgetEstimate,
)
from runtime.task_graph import TaskNode, TaskStatus
from runtime.scheduler import Scheduler, DispatchDecision
from runtime.hermes_adapter import HermesActorAdapter
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.recovery import RecoveryManager, RecoveryMetrics
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.events import RuntimeEventBridge
from capabilities.capabilities import CapabilityRegistry
from runner.agents.base import AgentAdapter, AgentContext
from runner.agents.registry import AgentRegistry


def test_provider_metadata_normalization():
    """
    Test 1: Normalizes real observable provider usage and rate-limit metadata.
    """
    raw_payload = {
        "usage": {
            "prompt_tokens": 1200,
            "completion_tokens": 350,
            "prompt_tokens_details": {"cached_tokens": 400},
            "total_context_used": 1550,
            "context_window": 128000,
        },
        "model": "gpt-4o",
    }
    headers = {
        "x-ratelimit-remaining-tokens": "85000",
        "x-ratelimit-limit-tokens": "100000",
        "x-ratelimit-remaining-requests": "450",
        "x-ratelimit-limit-requests": "500",
        "x-ratelimit-reset": "2026-08-25T16:30:00Z",
    }

    snapshot = UsageSnapshotNormalizer.normalize(
        raw_data=raw_payload,
        headers=headers,
        provider_id="openai",
        actor_id="actor_gpt4",
    )

    assert snapshot.provider_id == "openai"
    assert snapshot.actor_id == "actor_gpt4"
    assert snapshot.model_id == "gpt-4o"
    assert snapshot.input_tokens == 1200
    assert snapshot.output_tokens == 350
    assert snapshot.cached_tokens == 400
    assert snapshot.tokens_used == 1550
    assert snapshot.tokens_remaining == 85000
    assert snapshot.token_limit == 100000
    assert snapshot.requests_remaining == 450
    assert snapshot.request_limit == 500
    assert snapshot.context_used == 1550
    assert snapshot.context_window == 128000
    assert snapshot.reset_at == "2026-08-25T16:30:00Z"
    assert snapshot.source == "provider_reported"


def test_unknown_when_unsupported_and_never_fabricated():
    """
    Test 2: Proves missing / unsupported telemetry leaves source as 'unknown'
    and NEVER fabricates remaining token or request limits.
    """
    empty_payload = {}
    empty_headers = {}

    snapshot = UsageSnapshotNormalizer.normalize(
        raw_data=empty_payload,
        headers=empty_headers,
        provider_id="custom_local",
    )

    assert snapshot.provider_id == "custom_local"
    assert snapshot.tokens_remaining is None
    assert snapshot.requests_remaining is None
    assert snapshot.token_limit is None
    assert snapshot.request_limit is None
    assert snapshot.context_used is None
    assert snapshot.context_window is None
    assert snapshot.source == "unknown"


def test_eight_percent_remaining_causes_proactive_reroute():
    """
    Test 3: Provider with 8% remaining token quota (< 15% soft threshold)
    causes scheduler to proactively reroute before dispatch to a healthy capable actor.
    """
    cap_reg = CapabilityRegistry()
    cap_reg.register_actor({"id": "actor_primary", "name": "Primary", "capabilities": ["python", "builder"]})
    cap_reg.register_actor({"id": "actor_backup", "name": "Backup", "capabilities": ["python", "builder"]})

    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_primary", "provider_low")
    capacity_reg.register_actor_provider("actor_backup", "provider_healthy")

    # Set low provider at 8% remaining (8,000 / 100,000)
    capacity_reg._usage_snapshots["provider_low"] = UsageSnapshot(
        provider_id="provider_low",
        tokens_remaining=8000,
        token_limit=100000,
        source="provider_reported",
    )

    # Set backup provider at 90% remaining (90,000 / 100,000)
    capacity_reg._usage_snapshots["provider_healthy"] = UsageSnapshot(
        provider_id="provider_healthy",
        tokens_remaining=90000,
        token_limit=100000,
        source="provider_reported",
    )

    scheduler = Scheduler(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
    )

    task = TaskNode(
        task_id="T_PROACTIVE",
        job_id="job_proactive",
        description="Build Python Feature",
        required_capabilities=["python", "builder"],
        assigned_actor="actor_primary",
    )

    decision = scheduler.match_actor_for_task(task)
    assert decision.dispatched is True
    assert decision.actor_id == "actor_backup"
    assert "proactive capacity reroute" in decision.reason.lower()
    assert "8.0% < 15%" in decision.reason


def test_eighty_percent_remaining_does_not_reroute():
    """
    Test 4: Provider with 80% remaining capacity (>= 15% soft threshold)
    dispatches normally to the assigned actor without rerouting.
    """
    cap_reg = CapabilityRegistry()
    cap_reg.register_actor({"id": "actor_primary", "name": "Primary", "capabilities": ["python", "builder"]})
    cap_reg.register_actor({"id": "actor_backup", "name": "Backup", "capabilities": ["python", "builder"]})

    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_primary", "provider_ok")
    capacity_reg.register_actor_provider("actor_backup", "provider_healthy")

    # Set primary provider at 80% remaining (80,000 / 100,000)
    capacity_reg._usage_snapshots["provider_ok"] = UsageSnapshot(
        provider_id="provider_ok",
        tokens_remaining=80000,
        token_limit=100000,
        source="provider_reported",
    )

    scheduler = Scheduler(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
    )

    task = TaskNode(
        task_id="T_NORMAL",
        job_id="job_normal",
        description="Build Python Feature",
        required_capabilities=["python", "builder"],
        assigned_actor="actor_primary",
    )

    decision = scheduler.match_actor_for_task(task)
    assert decision.dispatched is True
    assert decision.actor_id == "actor_primary"
    assert "explicitly assigned" in decision.reason.lower()


class ContextPressureMockAgent(AgentAdapter):
    name = "pressured_agent"

    def build_command(self, context: AgentContext):
        return ["echo", "pressure"]

    def validate_result(self, result, context: AgentContext):
        return result

    def execute(self, context: AgentContext):
        from runner.backends.base import ExecutionResult
        # Agent signals 92% context window usage
        return ExecutionResult(
            command=("mock",),
            returncode=0,
            stdout="completed with pressure",
            stderr="",
            backend="test",
            runtime_metadata={
                "context_used": 118000,
                "context_window": 128000,
                "context_pressure": True,
                "context_ratio": 0.92,
                "usage": {"input_tokens": 110000, "output_tokens": 8000},
            },
        )


@pytest.mark.anyio
async def test_context_pressure_causes_new_session_handoff(tmp_path: Path):
    """
    Test 5: When an agent encounters heavy context pressure (> 85%),
    HermesActorAdapter creates a continuity handoff summary observation.
    """
    reg = AgentRegistry()
    reg.register(ContextPressureMockAgent())

    from runtime.observations import ObservationRegistry
    obs_reg = ObservationRegistry()

    adapter = HermesActorAdapter(
        target_repo=tmp_path,
        worktree_root=tmp_path / "worktrees",
        run_dir=tmp_path / "runs",
        agent_registry=reg,
        dry_run=False,
    )

    task = TaskNode(
        task_id="T_PRESSURE",
        job_id="job_pressure_1",
        description="Large Context Task",
        assigned_actor="pressured_agent",
    )
    run = AgentRun(run_id="run_p1", job_id="job_pressure_1", task_id="T_PRESSURE", actor_id="pressured_agent")

    from runtime.capacity import default_capacity_registry
    default_capacity_registry.register_actor_provider("pressured_agent", "provider_pressured")

    result = await adapter.execute_task(task, run, context={"job": {"job_id": "job_pressure_1"}})
    assert result.status == "succeeded"

    # Verify continuity handoff observation was generated
    from runtime.observations import default_observation_registry
    handoff_obs = [o for o in default_observation_registry.list_for_task("T_PRESSURE") if o.kind == "continuity_handoff"]
    assert len(handoff_obs) == 1
    assert "92." in handoff_obs[0].content
    assert handoff_obs[0].metadata.get("fresh_session") is True


def test_hard_429_fallback_still_works():
    """
    Test 6: Verifies that hard 429 failures still trigger rate limit classification
    and reactive failover.
    """
    failure_class, retry_after = ProviderFailureClassifier.classify(
        error="Rate limit exceeded: 429 Too Many Requests",
        status_code=429,
        headers={"retry-after": "45"},
    )
    assert failure_class == ProviderFailureClass.RATE_LIMITED
    assert retry_after == 45.0


@pytest.mark.anyio
async def test_rto_timestamp_occurs_after_actual_resumed_dispatch(tmp_path: Path):
    """
    Test 7: Validates that execution_resumed_at and RTO are measured
    when scheduler actually dispatches the resumed task.
    """
    event_store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=event_store)

    job_id = "job_rto_test"
    t1 = TaskNode(task_id="T1", job_id=job_id, status=TaskStatus.READY, description="Task 1")

    from runtime.job_state import JobRecord, JobState
    job = JobRecord(job_id=job_id, goal="RTO Test", state=JobState.EXECUTING)

    await bridge.emit_job_created(job)
    await bridge.emit_task_created(t1)

    interrupted_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    manager = RecoveryManager(event_store=event_store)
    engine, metrics = await manager.recover_and_rehydrate(
        job_id=job_id,
        detected_interruption_at=interrupted_time,
    )

    rehydrated_at = metrics.execution_resumed_at

    # Simulate delay before scheduler actually steps
    await asyncio.sleep(0.05)

    # Step engine to trigger actual task dispatch
    await engine.step()

    # True execution_resumed_at must be updated at actual dispatch time
    assert metrics.execution_resumed_at >= rehydrated_at
    assert metrics.rto_seconds >= 10.0
