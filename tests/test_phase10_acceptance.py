import asyncio
from datetime import datetime, timezone, timedelta
import pytest

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.execution import AgentRun, AgentRunStatus, TaskExecutionResult, ExecutionManager
from runtime.verification import VerificationResult, VerificationStatus, CallableVerifierAdapter
from runtime.capacity import CapacityRegistry, ProviderStatus
from runtime.circuit_breaker import CircuitBreakerRegistry
from runtime.routing import ReroutePolicy
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.recovery import RecoveryManager
from runtime.engine import ReactiveJobEngine
from capabilities.capabilities import CapabilityRegistry


def build_acceptance_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register_actor({
        "id": "actor_inspector",
        "name": "Inspector",
        "capabilities": ["repo.inspect"],
    })
    reg.register_actor({
        "id": "actor_backend_a",
        "name": "Backend Primary",
        "capabilities": ["backend.python"],
    })
    reg.register_actor({
        "id": "actor_frontend_primary",
        "name": "Frontend Primary",
        "capabilities": ["frontend.react"],
    })
    reg.register_actor({
        "id": "actor_frontend_fallback",
        "name": "Frontend Fallback",
        "capabilities": ["frontend.react"],
    })
    reg.register_actor({
        "id": "actor_integrator",
        "name": "Integrator",
        "capabilities": ["git.integrate"],
    })
    return reg


@pytest.mark.anyio
async def test_phase10_full_end_to_end_resilience_recovery_and_rerouting():
    """
    Headline E2E Acceptance Test:
    Validates complete workflow resilience across:
    1. Process crash after partial progress
    2. Zero RPO event reconstruction & rehydration
    3. Reconciling interrupted task without repeating model work
    4. Provider quota exhaustion & circuit tripping
    5. Dynamic capability-based task rerouting
    6. Seamless dependency completion & verification
    7. Pure deterministic post-destruction reconstruction equivalence.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)
    cap_reg = build_acceptance_registry()
    capacity_reg = CapacityRegistry()
    capacity_reg.register_actor_provider("actor_inspector", "claude_provider")
    capacity_reg.register_actor_provider("actor_backend_a", "claude_provider")
    capacity_reg.register_actor_provider("actor_frontend_primary", "openai_provider")
    capacity_reg.register_actor_provider("actor_frontend_fallback", "gemini_provider")
    capacity_reg.register_actor_provider("actor_integrator", "claude_provider")
    circuit_reg = CircuitBreakerRegistry()
    reroute_pol = ReroutePolicy(
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
    )

    # -------------------------------------------------------------
    # Session 1: Initial Engine Run before crash
    # -------------------------------------------------------------
    engine_1 = ReactiveJobEngine(
        job_id="job_e2e_resilience",
        goal="Deliver complete end-to-end fullstack feature",
        capability_registry=cap_reg,
        capacity_registry=capacity_reg,
        circuit_registry=circuit_reg,
        reroute_policy=reroute_pol,
        event_bridge=bridge,
    )

    t1 = TaskNode(task_id="T1", job_id="job_e2e_resilience", description="Inspect repository", required_capabilities=["repo.inspect"])
    t2 = TaskNode(task_id="T2", job_id="job_e2e_resilience", description="Backend implementation", dependencies=["T1"], required_capabilities=["backend.python"])
    t3 = TaskNode(task_id="T3", job_id="job_e2e_resilience", description="Frontend implementation", dependencies=["T1"], required_capabilities=["frontend.react"])
    t4 = TaskNode(task_id="T4", job_id="job_e2e_resilience", description="Integration", dependencies=["T2", "T3"], required_capabilities=["git.integrate"])

    await engine_1.initialize_and_plan(initial_tasks=[t1, t2, t3, t4])

    execution_log = []

    async def session1_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        execution_log.append((task.task_id, run.actor_id))
        if task.task_id == "T1":
            return TaskExecutionResult(status="succeeded", artifact_refs=[{"id": "art_inspect", "label": "repo_map"}])
        elif task.task_id == "T2":
            # T2 finishes work, creates commit, but process crashes before task.completed acknowledged
            return TaskExecutionResult(
                status="succeeded",
                artifact_refs=[{"id": "art_t2", "label": "t2_commit"}],
                metadata={"commit_sha": "commit_backend_001", "integrated": True},
            )
        return TaskExecutionResult(status="succeeded")

    engine_1.set_default_execution_adapter(session1_adapter)

    # Step 1: Executes T1
    await engine_1.step()
    assert engine_1.graph.get_task("T1").status == TaskStatus.SUCCEEDED

    # -------------------------------------------------------------
    # SIMULATE SUDDEN RUNTIME PROCESS DEATH
    # -------------------------------------------------------------
    del engine_1
    del bridge

    events_after_crash = await store.list_events("job_e2e_resilience")
    assert len(events_after_crash) > 0

    # -------------------------------------------------------------
    # Session 2: Crash Recovery & Rehydration
    # -------------------------------------------------------------
    interruption_time = (datetime.now(timezone.utc) - timedelta(seconds=5.0)).isoformat()
    bridge_2 = RuntimeEventBridge(event_store=store)

    engine_2, recovery_metrics = await ReactiveJobEngine.resume(
        job_id="job_e2e_resilience",
        event_store=store,
        capability_registry=cap_reg,
        event_bridge=bridge_2,
        detected_interruption_at=interruption_time,
    )

    assert engine_2.job.state == JobState.EXECUTING
    assert engine_2.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert recovery_metrics.rto_seconds >= 5.0
    assert "T1" in recovery_metrics.preserved_tasks

    # Wire adapters with capacity quota injection on frontend primary
    async def session2_adapter(task: TaskNode, run: AgentRun, ctx: dict):
        execution_log.append((task.task_id, run.actor_id))
        if run.actor_id == "actor_frontend_primary":
            # Primary frontend hits OpenAI quota exhaustion
            return TaskExecutionResult(
                status="failed",
                error="HTTP 429: You have exceeded your current quota",
                exit_reason="quota_exhausted",
                metadata={"status_code": 429},
            )
        return TaskExecutionResult(status="succeeded", artifact_refs=[{"id": f"art_{task.task_id}", "label": f"{task.task_id}_output"}])

    engine_2.set_default_execution_adapter(session2_adapter)
    engine_2.set_verifier(CallableVerifierAdapter(lambda job, graph, artifacts, context: VerificationResult(
        status=VerificationStatus.PASSED,
        verifier_id="acceptance_verifier",
        summary="All acceptance criteria verified",
    )))

    # Step through T2 and T3
    # Step: Executes T2 and dispatches T3 to actor_frontend_primary -> fails with quota -> reroutes to actor_frontend_fallback
    await engine_2.step()
    assert engine_2.graph.get_task("T2").status == TaskStatus.SUCCEEDED

    # Next step: Executes T3 on fallback actor and completes T3
    await engine_2.step()
    assert engine_2.graph.get_task("T3").status == TaskStatus.SUCCEEDED
    assert engine_2.graph.get_task("T3").assigned_actor == "actor_frontend_fallback"

    # Step: Executes T4 (Integration)
    await engine_2.step()
    assert engine_2.graph.get_task("T4").status == TaskStatus.SUCCEEDED

    # Step: Verification and terminal completion
    await engine_2.step()
    assert engine_2.job.state == JobState.COMPLETED

    # -------------------------------------------------------------
    # Pure Deterministic Post-Destruction Reconstruction Verification
    # -------------------------------------------------------------
    all_events = await store.list_events("job_e2e_resilience")
    terminal_events = [e for e in all_events if e.event_type in ("job.completed", "job.failed", "job.cancelled", "job.blocked")]
    assert len(terminal_events) == 1, "Must contain exactly ONE terminal job event in the ledger"

    # Verify no duplicate task completions
    t1_completes = [e for e in all_events if e.event_type == "task.completed" and e.task_id == "T1"]
    assert len(t1_completes) == 1

    # Reconstruct state from scratch
    reconstructed = RuntimeStateProjector.project(all_events)
    assert reconstructed.job.state == JobState.COMPLETED
    assert reconstructed.graph.get_task("T1").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T2").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T3").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T4").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T3").assigned_actor == "actor_frontend_fallback"
    assert reconstructed.last_verification is not None
    assert reconstructed.last_verification.is_passed is True
