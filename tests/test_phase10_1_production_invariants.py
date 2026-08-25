import asyncio
from datetime import datetime, timezone
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskNode, TaskStatus
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.capacity import CapacityRegistry, ProviderStatus, ProviderFailureClass, ProviderFailureClassifier
from runtime.circuit_breaker import CircuitBreakerRegistry
from runtime.routing import ReroutePolicy
from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from capabilities.capabilities import CapabilityRegistry
from jobs.job_launcher import JobLauncher


def create_mock_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register_actor({
        "id": "actor_primary",
        "name": "Primary Code Actor",
        "capabilities": ["code.generate"],
    })
    reg.register_actor({
        "id": "actor_fallback",
        "name": "Fallback Code Actor",
        "capabilities": ["code.generate"],
    })
    return reg


@pytest.mark.anyio
async def test_pre_dispatch_capability_rerouting():
    """
    Test: When a task has an explicit assigned_actor that is currently unavailable
    (circuit open, throttled, or quota exhausted), the scheduler reroutes the task
    to an available capable actor BEFORE dispatch.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    cap_reg = create_mock_registry()
    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_primary", "provider_primary")
    capacity_reg.register_actor_provider("actor_fallback", "provider_fallback")
    circuit_reg = CircuitBreakerRegistry()
    reroute_pol = ReroutePolicy(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
    )

    # Mark provider_primary as QUOTA_EXHAUSTED
    capacity_reg.set_provider_status("provider_primary", ProviderStatus.QUOTA_EXHAUSTED, reason="Credit expired")

    engine = ReactiveJobEngine(
        job_id="job_pre_dispatch",
        goal="Test pre-dispatch rerouting",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
        reroute_policy=reroute_pol,
        event_bridge=bridge,
    )

    t1 = TaskNode(
        task_id="T1",
        job_id="job_pre_dispatch",
        description="Generate code",
        required_capabilities=["code.generate"],
        assigned_actor="actor_primary",
    )
    await engine.initialize_and_plan(initial_tasks=[t1])

    executed_actor = []

    async def adapter(task: TaskNode, run: AgentRun, ctx: dict):
        executed_actor.append(run.actor_id)
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(adapter)

    # Step: Pre-dispatch reroutes to actor_fallback and executes successfully
    await engine.step()

    assert executed_actor == ["actor_fallback"]
    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert engine.graph.get_task("T1").assigned_actor == "actor_fallback"

    # Verify task.rerouted and task.ready were emitted
    events = await store.list_events("job_pre_dispatch")
    event_types = [e.event_type for e in events]
    assert "task.rerouted" in event_types
    assert "task.ready" in event_types


@pytest.mark.anyio
async def test_waiting_for_capacity_does_not_exhaust_max_steps():
    """
    Test: Cycles in WAITING_FOR_CAPACITY do not decrement/consume the execution step budget.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    cap_reg = create_mock_registry()
    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_primary", "provider_primary")
    circuit_reg = CircuitBreakerRegistry()
    reroute_pol = ReroutePolicy(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
    )

    # Throttle provider with reset in 0.1s
    capacity_reg.set_provider_status("provider_primary", ProviderStatus.THROTTLED, reset_in_seconds=0.1)

    engine = ReactiveJobEngine(
        job_id="job_step_budget",
        goal="Test max steps decoupling",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
        reroute_policy=reroute_pol,
        event_bridge=bridge,
    )

    t1 = TaskNode(
        task_id="T1",
        job_id="job_step_budget",
        description="Run code",
        required_capabilities=["code.generate"],
        assigned_actor="actor_primary",
    )
    await engine.initialize_and_plan(initial_tasks=[t1])

    async def adapter(task: TaskNode, run: AgentRun, ctx: dict):
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(adapter)

    # Set max_steps to only 5. Engine should wait multiple polling cycles without BLOCKED transition.
    job_res = await engine.run_until_complete(max_steps=5)
    assert job_res.state == JobState.COMPLETED
    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED


@pytest.mark.anyio
async def test_usage_metadata_ingestion_into_capacity_registry():
    """
    Test: Task execution results carrying input/output/cached token usage
    are ingested into CapacityRegistry accounting.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    cap_reg = create_mock_registry()
    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_primary", "provider_primary")
    circuit_reg = CircuitBreakerRegistry()

    engine = ReactiveJobEngine(
        job_id="job_usage_test",
        goal="Test token telemetry ingestion",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
        event_bridge=bridge,
    )

    t1 = TaskNode(
        task_id="T1",
        job_id="job_usage_test",
        description="Run LLM task",
        required_capabilities=["code.generate"],
        assigned_actor="actor_primary",
    )
    await engine.initialize_and_plan(initial_tasks=[t1])

    async def adapter(task: TaskNode, run: AgentRun, ctx: dict):
        return TaskExecutionResult(
            status="succeeded",
            metadata={
                "input_tokens": 1500,
                "output_tokens": 750,
                "cached_tokens": 300,
            },
        )

    engine.set_default_execution_adapter(adapter)

    await engine.step()

    usage = capacity_reg.get_usage("provider_primary")
    assert usage.input_tokens == 1500
    assert usage.output_tokens == 750
    assert usage.cached_tokens == 300
    assert usage.tokens_used == 2250


def test_expanded_provider_failure_classification():
    """
    Test: ProviderFailureClassifier correctly categorizes model unavailable,
    content filters, authentication, and network failures.
    """
    # 1. Model Unavailable
    c1, _ = ProviderFailureClassifier.classify("Error: model 'gpt-5-turbo' does not exist")
    assert c1 == ProviderFailureClass.MODEL_UNAVAILABLE

    # 2. Content Filter
    c2, _ = ProviderFailureClassifier.classify("Prompt blocked by safety policy")
    assert c2 == ProviderFailureClass.CONTENT_FILTER

    # 3. Authentication
    c3, _ = ProviderFailureClassifier.classify("HTTP 401: Invalid API Key provided", status_code=401)
    assert c3 == ProviderFailureClass.AUTHENTICATION

    # 4. Network / Connection
    c4, _ = ProviderFailureClassifier.classify("Connection refused: Failed to establish a new connection")
    assert c4 == ProviderFailureClass.NETWORK


@pytest.mark.anyio
async def test_job_launcher_resume_rebuilds_hermes_adapters(tmp_path):
    """
    Test: JobLauncher.resume_async resolves sprint specification and binds
    real HermesActorAdapter, HermesVerifierAdapter, and HermesPlannerAdapter.
    """
    from jobs.job_launcher import JobLauncher
    from runtime.storage.config import set_global_event_store, set_global_lease_store
    from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
    from runtime.lease import InMemoryJobLeaseStore
    from runtime.hermes_adapter import HermesActorAdapter, HermesVerifierAdapter, HermesPlannerAdapter
    import json

    sprints_dir = tmp_path / "sprints"
    sprints_dir.mkdir()
    sprint_spec = {
        "name": "Integration Sprint 99",
        "target_repo": str(tmp_path),
        "target_branch": "sprint/sprint_99/integration",
        "phases": [
            {"name": "p1", "role": "builder"},
            {"name": "p2", "role": "verifier"},
        ],
        "verification": [
            {"name": "pytest", "cmd": "pytest"}
        ],
    }
    (sprints_dir / "sprint_99.json").write_text(json.dumps(sprint_spec), encoding="utf-8")

    event_store = InMemoryRuntimeEventStore()
    lease_store = InMemoryJobLeaseStore()
    set_global_event_store(event_store)
    set_global_lease_store(lease_store)

    bridge = RuntimeEventBridge(event_store=event_store)
    job = JobRecord(
        job_id="run_20260825_100000_sprint_99",
        goal="Sprint 99 Goal",
        metadata={"sprint_id": "sprint_99"},
    )
    await bridge.emit_job_created(job)
    job.state = JobState.EXECUTING
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    launcher = JobLauncher(sprints_dir=sprints_dir)
    res = await launcher.resume_async(job_id=job.job_id)

    assert res["resumed"] is True
    from jobs.job_service import job_service
    resumed_engine = job_service.get_engine(job.job_id)
    assert resumed_engine is not None
    assert isinstance(resumed_engine.default_execution_adapter, HermesActorAdapter)
    assert isinstance(resumed_engine.verifier, HermesVerifierAdapter)
    assert isinstance(resumed_engine.planner, HermesPlannerAdapter)

    # Cleanup
    launcher.cancel(job.job_id)


@pytest.mark.anyio
async def test_lease_heartbeat_and_release_lifecycle():
    """
    Test: JobLeaseManager acquires lease, maintains background heartbeat,
    and cleanly releases lease upon cancellation/termination.
    """
    from runtime.lease import InMemoryJobLeaseStore, JobLeaseManager

    lease_store = InMemoryJobLeaseStore()
    mgr = JobLeaseManager(
        lease_store=lease_store,
        owner_id="node_test_1",
        duration_seconds=10.0,
        heartbeat_interval_seconds=0.05,
    )

    acquired = await mgr.acquire_and_start_heartbeat("job_lease_test")
    assert acquired is True

    lease = await lease_store.get_lease("job_lease_test")
    assert lease is not None
    assert lease.owner_id == "node_test_1"

    # Wait for heartbeat tick
    await asyncio.sleep(0.12)
    lease_after_hb = await lease_store.get_lease("job_lease_test")
    assert lease_after_hb is not None

    # Release
    released = await mgr.release_and_stop_heartbeat("job_lease_test")
    assert released is True

    lease_final = await lease_store.get_lease("job_lease_test")
    assert lease_final is None
