import asyncio
import copy
from datetime import datetime, timezone
import pytest
import uuid

from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.execution import ActorAdapter, AgentRun, AgentRunStatus, ExecutionManager, TaskExecutionResult
from runtime.job_state import JobRecord, JobState
from runtime.limits import RuntimeLimits
from runtime.observations import Observation, ObservationRegistry
from runtime.replanning import (
    GraphMutation,
    GraphMutationType,
    PlannerAdapter,
    ReplanReason,
    ReplanRequest,
    ReplanResult,
)
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.verification import (
    VerificationCheck,
    VerificationResult,
    VerificationStatus,
    VerifierAdapter,
)


@pytest.mark.anyio
async def test_complete_phase9_acceptance_scenario():
    """
    Core Phase 9 Acceptance Test:
    Executes a multi-stage, multi-agent reactive runtime workflow:
    1. Job Created & Initial Planning -> T1 inspect repository.
    2. T1 executes -> discovers 'missing auth migration' observation (flagged requires_follow_up=True).
    3. Discovery replan triggers -> planner expands graph with T2 (migration) and T3 (unit tests).
    4. T2 and T3 execute concurrently.
    5. All graph tasks finish -> verification runs and fails with repairable check failure.
    6. Repair triggered -> T4 repair task added.
    7. T4 executes and succeeds.
    8. Verification re-runs -> PASSED.
    9. Engine reaches COMPLETED terminal state.
    10. Entire in-memory engine, graph, runs, and registry objects are completely destroyed.
    11. Entire session is reconstructed EXCLUSIVELY from the append-only event store ledger.
    12. Assertions verify exact deterministic match.
    """
    job_id = f"job_p9_acceptance_{uuid.uuid4().hex[:8]}"
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    # 1. Custom Actor Adapter simulating multi-agent task execution
    class ScenarioActorAdapter(ActorAdapter):
        def __init__(self):
            self.execution_counts = {}

        async def execute_task(self, task: TaskNode, run: AgentRun, context=None) -> TaskExecutionResult:
            self.execution_counts[task.task_id] = self.execution_counts.get(task.task_id, 0) + 1

            if task.task_id == "T1_inspect":
                # Discover missing migration requiring follow-up
                obs = Observation(
                    observation_id=f"obs_discovery_{job_id}",
                    job_id=job_id,
                    kind="discovery",
                    content="Discovered missing authentication migration scripts",
                    task_id="T1_inspect",
                    actor_id="claude",
                    metadata={"requires_follow_up": True, "area": "database"},
                )
                return TaskExecutionResult(
                    status="succeeded",
                    exit_reason="inspection_completed",
                    observations=[obs],
                    artifact_refs=[{"id": "art_inspect", "type": "report", "ref": "/reports/inspect.json"}],
                )

            elif task.task_id in ("T2_migration", "discover_obs_discovery_" + job_id):
                return TaskExecutionResult(
                    status="succeeded",
                    exit_reason="migration_applied",
                    artifact_refs=[{"id": "art_mig_commit", "type": "git_commit", "ref": "commit_sha_mig_01"}],
                )

            elif task.task_id == "T3_tests":
                return TaskExecutionResult(
                    status="succeeded",
                    exit_reason="tests_added",
                    artifact_refs=[{"id": "art_test_commit", "type": "git_commit", "ref": "commit_sha_test_01"}],
                )

            elif task.task_id.startswith("repair_") or task.task_id == "T4_repair":
                return TaskExecutionResult(
                    status="succeeded",
                    exit_reason="repaired",
                    artifact_refs=[{"id": "art_repair_commit", "type": "git_commit", "ref": "commit_sha_repair_01"}],
                )

            return TaskExecutionResult(status="succeeded", exit_reason="done")

    # 2. Custom Planner Adapter expanding graph on observation and repair
    class ScenarioPlanner(PlannerAdapter):
        async def plan(self, request: ReplanRequest) -> ReplanResult:
            reason_str = str(request.reason.value if hasattr(request.reason, "value") else request.reason).lower()

            if "initial" in reason_str:
                t1 = TaskNode(
                    task_id="T1_inspect",
                    job_id=request.job_id,
                    description="Inspect codebase and schema",
                    required_capabilities=["repo.read"],
                    assigned_actor="claude",
                )
                return ReplanResult(
                    mutations=[GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t1)],
                    explanation="Initial inspection planned",
                )

            elif "observation" in reason_str or "discovery" in reason_str:
                # Add T2 and T3
                t2 = TaskNode(
                    task_id="T2_migration",
                    job_id=request.job_id,
                    description="Apply auth DB migration",
                    dependencies=["T1_inspect"],
                    required_capabilities=["implementation"],
                    assigned_actor="gemini",
                )
                t3 = TaskNode(
                    task_id="T3_tests",
                    job_id=request.job_id,
                    description="Add auth unit tests",
                    dependencies=["T2_migration"],
                    required_capabilities=["testing.unit"],
                    assigned_actor="codex",
                )
                return ReplanResult(
                    mutations=[
                        GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t2, reason="Add migration"),
                        GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t3, reason="Add test coverage"),
                    ],
                    explanation="Expanded graph with migration and testing tasks from discovery",
                )

            elif "verification" in reason_str or "repair" in reason_str:
                t4 = TaskNode(
                    task_id="T4_repair",
                    job_id=request.job_id,
                    description="Fix authentication token validation bug",
                    dependencies=["T3_tests"],
                    required_capabilities=["implementation"],
                    assigned_actor="antigravity",
                )
                return ReplanResult(
                    mutations=[
                        GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t4, reason="Fix auth token verification"),
                    ],
                    explanation="Planned repair task for verification failure",
                )

            return ReplanResult(mutations=[], explanation="No mutations")

    # 3. Custom Verifier Adapter: fails on first run with repair recommendation, passes on second run
    class ScenarioVerifier(VerifierAdapter):
        def __init__(self):
            self.run_count = 0

        async def verify(self, job, graph, artifacts=None, context=None) -> VerificationResult:
            self.run_count += 1
            if self.run_count == 1:
                return VerificationResult(
                    status=VerificationStatus.REPAIRABLE,
                    verifier_id="pytest_auth_suite",
                    summary="TestAuthToken::test_expired_token failed: expected 401 Unauthorized, got 500",
                    checks=[
                        VerificationCheck(name="db_schema_valid", passed=True),
                        VerificationCheck(
                            name="unit_tests_pass",
                            passed=False,
                            error="test_expired_token failed",
                            repairable=True,
                        ),
                    ],
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    verifier_id="pytest_auth_suite",
                    summary="All 18 auth test checks passed cleanly",
                    checks=[
                        VerificationCheck(name="db_schema_valid", passed=True),
                        VerificationCheck(name="unit_tests_pass", passed=True),
                    ],
                )

    # Instantiate engine
    actor_adapter = ScenarioActorAdapter()
    planner = ScenarioPlanner()
    verifier = ScenarioVerifier()

    engine = ReactiveJobEngine(
        job_id=job_id,
        goal="Implement robust auth migration and verification",
        title="Acceptance Scenario Job",
        actor_adapter=actor_adapter,
        planner=planner,
        verifier=verifier,
        event_bridge=bridge,
        limits=RuntimeLimits(max_replans_per_job=5, max_repairs_per_job=3),
    )

    # Run engine to completion
    final_job = await engine.run_until_complete(max_steps=20)
    assert final_job.state == JobState.COMPLETED
    assert engine.job.replan_count >= 1
    assert engine.job.repair_count >= 1

    # Record snapshot of in-memory objects before destroying them
    original_job_dict = copy.deepcopy(engine.job.to_dict())
    original_tasks = {t.task_id: t.to_dict() for t in engine.graph.list_tasks()}
    original_runs = [r.to_dict() for r in engine.execution_manager.list_runs_for_job(job_id)]
    original_obs = [o.to_dict() for o in engine.observation_registry.list_for_job(job_id)]
    original_artifacts = engine.get_artifacts()

    # -------------------------------------------------------------
    # DESTROY ALL IN-MEMORY RUNTIME OBJECTS (simulate process restart)
    # -------------------------------------------------------------
    del engine
    del actor_adapter
    del planner
    del verifier
    del bridge

    # Fetch canonical event ledger exclusively from the durable store
    persisted_events = await store.list_events(job_id)
    assert len(persisted_events) > 10, "Expected a rich event ledger for acceptance workflow"

    # Verify per-job strict monotonic sequence ordering: 1, 2, 3, ...
    sequences = [e.sequence for e in persisted_events]
    assert sequences == list(range(1, len(persisted_events) + 1)), "Event sequences must be strictly 1, 2, 3, ... with no gaps or duplicates"

    # -------------------------------------------------------------
    # RECONSTRUCT EXCLUSIVELY FROM PERSISTED EVENT LEDGER
    # -------------------------------------------------------------
    reconstructed = RuntimeStateProjector.project(persisted_events)

    # 1. Assert Job Record matches
    assert reconstructed.job.job_id == job_id
    assert reconstructed.job.state == JobState.COMPLETED
    assert reconstructed.job.replan_count == original_job_dict["replan_count"]
    assert reconstructed.job.repair_count == original_job_dict["repair_count"]
    assert reconstructed.job.title == original_job_dict["title"]
    assert reconstructed.job.goal == original_job_dict["goal"]
    assert reconstructed.job.started_at is not None
    assert reconstructed.job.completed_at is not None

    # 2. Assert Task Graph matches
    reconstructed_tasks = {t.task_id: t.to_dict() for t in reconstructed.graph.list_tasks()}
    assert set(reconstructed_tasks.keys()) == set(original_tasks.keys())
    for task_id, orig_t in original_tasks.items():
        rec_t = reconstructed_tasks[task_id]
        assert rec_t["status"] == orig_t["status"]
        assert rec_t["dependencies"] == orig_t["dependencies"]
        assert rec_t["assignedActor"] == orig_t["assignedActor"]

    # 3. Assert Agent Runs match
    reconstructed_runs = [r.to_dict() for r in reconstructed.runs]
    assert len(reconstructed_runs) == len(original_runs)
    for orig_r, rec_r in zip(original_runs, reconstructed_runs):
        assert rec_r["run_id"] == orig_r["run_id"]
        assert rec_r["task_id"] == orig_r["task_id"]
        assert rec_r["actor_id"] == orig_r["actor_id"]
        assert rec_r["status"] == orig_r["status"]
        assert rec_r["exit_reason"] == orig_r["exit_reason"]

    # 4. Assert Observations match
    reconstructed_obs = [o.to_dict() for o in reconstructed.observations]
    assert len(reconstructed_obs) == len(original_obs)
    for orig_o, rec_o in zip(original_obs, reconstructed_obs):
        assert rec_o["observation_id"] == orig_o["observation_id"]
        assert rec_o["content"] == orig_o["content"]
        assert rec_o["kind"] == orig_o["kind"]
        assert rec_o["metadata"] == orig_o["metadata"]

    # 5. Assert Verification matches
    assert reconstructed.last_verification is not None
    assert reconstructed.last_verification.status == VerificationStatus.PASSED

    # 6. Assert Event ordering is deterministic
    event_types = [e.event_type for e in persisted_events]
    assert event_types[0] == "job.created"
    assert "replan.requested" in event_types
    assert "replan.completed" in event_types
    assert "verification.failed" in event_types
    assert "verification.passed" in event_types
    assert event_types[-1] == "job.completed"
