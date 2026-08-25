import asyncio
from datetime import datetime, timezone
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskNode, TaskStatus
from runtime.execution import AgentRun, TaskExecutionResult
from runtime.capacity import CapacityRegistry, ProviderFailureClass, ProviderStatus
from runtime.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerRegistry, CircuitState
from runtime.routing import ReroutePolicy
from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from capabilities.capabilities import CapabilityRegistry


def create_multi_actor_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register_actor({
        "id": "actor_codex",
        "name": "Codex Actor",
        "capabilities": ["code.generate", "code.test"],
    })
    reg.register_actor({
        "id": "actor_gemini",
        "name": "Gemini Actor",
        "capabilities": ["code.generate", "code.test"],
    })
    reg.register_actor({
        "id": "actor_specialized",
        "name": "Specialized Actor",
        "capabilities": ["db.migration"],
    })
    return reg


@pytest.mark.anyio
async def test_quota_exhaustion_reroutes_task_to_capable_alternative():
    """
    Test Y & Z: When an actor encounters quota exhaustion, the task is rerouted
    to an alternative capable actor based strictly on capabilities.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    cap_registry = create_multi_actor_registry()
    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_codex", "openai")
    capacity_reg.register_actor_provider("actor_gemini", "google")
    circuit_reg = CircuitBreakerRegistry()
    reroute_pol = ReroutePolicy(
        capability_registry=cap_registry,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
    )

    engine = ReactiveJobEngine(
        job_id="job_reroute_1",
        goal="Generate component",
        capability_registry=cap_registry,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
        reroute_policy=reroute_pol,
        event_bridge=bridge,
    )

    t1 = TaskNode(
        task_id="T1",
        job_id="job_reroute_1",
        description="Generate code",
        required_capabilities=["code.generate"],
        assigned_actor="actor_codex",
    )
    await engine.initialize_and_plan(initial_tasks=[t1])

    executed_actors = []

    async def dynamic_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        executed_actors.append(run.actor_id)
        if run.actor_id == "actor_codex":
            # Simulate quota exhaustion
            return TaskExecutionResult(
                status="failed",
                error="Exceeded your current quota",
                exit_reason="quota_exhausted",
                metadata={"status_code": 429},
            )
        else:
            return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(dynamic_adapter)

    # 1. Step 1: Dispatches to actor_codex -> fails with quota -> rerouted to actor_gemini
    await engine.step()

    # Verify task was rerouted to actor_gemini
    assert engine.graph.get_task("T1").assigned_actor == "actor_gemini"
    assert engine.graph.get_task("T1").status == TaskStatus.READY
    assert capacity_reg.get_provider_status("openai") == ProviderStatus.QUOTA_EXHAUSTED

    # 2. Step 2: Dispatches to actor_gemini -> succeeds
    await engine.step()

    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert executed_actors == ["actor_codex", "actor_gemini"]

    # Verify reroute event in ledger
    events = await store.list_events("job_reroute_1")
    event_types = [e.event_type for e in events]
    assert "task.rerouted" in event_types
    reroute_event = next(e for e in events if e.event_type == "task.rerouted")
    assert reroute_event.payload["fromActor"] == "actor_codex"
    assert reroute_event.payload["toActor"] == "actor_gemini"


@pytest.mark.anyio
async def test_waiting_for_capacity_and_resumption():
    """
    Test AA & AB: When all capable providers are throttled, engine enters
    WAITING_FOR_CAPACITY, and transitions back to EXECUTING once capacity recovers.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    cap_registry = create_multi_actor_registry()
    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_specialized", "db_provider")
    circuit_reg = CircuitBreakerRegistry()
    reroute_pol = ReroutePolicy(
        capability_registry=cap_registry,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
    )

    # Throttle db_provider with a short cooldown
    capacity_reg.set_provider_status(
        provider_id="db_provider",
        status=ProviderStatus.THROTTLED,
        reason="Rate limit",
        reset_in_seconds=0.1,
    )

    engine = ReactiveJobEngine(
        job_id="job_wait_cap",
        goal="Run DB migration",
        capability_registry=cap_registry,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
        reroute_policy=reroute_pol,
        event_bridge=bridge,
    )

    t1 = TaskNode(
        task_id="T1",
        job_id="job_wait_cap",
        description="Migrate DB",
        required_capabilities=["db.migration"],
    )
    await engine.initialize_and_plan(initial_tasks=[t1])

    async def success_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        return TaskExecutionResult(status="succeeded")

    engine.set_default_execution_adapter(success_adapter)

    # 1. Step 1: Only capable actor is throttled -> enters WAITING_FOR_CAPACITY
    await engine.step()
    assert engine.job.state == JobState.WAITING_FOR_CAPACITY

    # Verify event emitted
    events = await store.list_events("job_wait_cap")
    assert "job.waiting_for_capacity" in [e.event_type for e in events]

    # 2. Wait for reset cooldown to elapse
    await asyncio.sleep(0.15)
    assert capacity_reg.get_provider_status("db_provider") == ProviderStatus.AVAILABLE

    # 3. Step 2: Detects capacity restored -> transitions back to EXECUTING
    await engine.step()
    assert engine.job.state == JobState.EXECUTING

    # 4. Step 3: Successfully schedules and executes T1
    await engine.step()
    assert engine.graph.get_task("T1").status == TaskStatus.SUCCEEDED


def test_circuit_breaker_state_lifecycle():
    """
    Test AF, AG, AH, AI, AJ: Circuit breaker transitions from CLOSED -> OPEN -> HALF_OPEN -> CLOSED/OPEN.
    """
    config = CircuitBreakerConfig(
        failure_threshold=2,
        cooldown_seconds=0.1,
        half_open_success_threshold=1,
    )
    cb = CircuitBreaker(name="test_actor", config=config)

    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True

    # 1. First failure
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    # 2. Second failure trips OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False  # AG: OPEN circuit blocks traffic

    # 3. Fast-forward cooldown -> HALF_OPEN (AH)
    cb._opened_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True

    # 4. Successful probe closes circuit (AI)
    cb.record_success()
    assert cb.state == CircuitState.CLOSED

    # 5. Failed probe re-opens circuit (AJ)
    cb.trip_open(cooldown_seconds=0.1)
    cb._opened_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
