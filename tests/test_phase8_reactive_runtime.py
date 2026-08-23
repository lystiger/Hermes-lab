import asyncio
import unittest
from datetime import datetime

from runtime import (
    JobState,
    JobRecord,
    InvalidStateTransitionError,
    TaskStatus,
    TaskNode,
    TaskGraph,
    Observation,
    ObservationRegistry,
    AgentRunStatus,
    AgentRun,
    TaskExecutionResult,
    VerificationStatus,
    VerificationResult,
    VerificationCheck,
    RuntimeLimits,
    GraphMutationType,
    GraphMutation,
    ReplanReason,
    ReplanRequest,
    ReplanResult,
    BoundedReplanner,
    RuntimeEventBridge,
    ReactiveScheduler,
    ReactiveJobEngine,
)
from capabilities.capabilities import CapabilityRegistry, Capability, DEFAULT_CAPABILITY_PROFILES
from personas.persona import AgentProfile


def create_test_capability_registry():
    registry = CapabilityRegistry()
    
    gemini = AgentProfile(
        id="gemini",
        displayName="Gemini",
        capabilities=["implementation", "code.python", "code.typescript", "frontend.react", "testing.unit"],
    )
    claude = AgentProfile(
        id="claude",
        displayName="Claude",
        capabilities=["review.code", "review.architecture", "repo.read", "code.python", "frontend.react"],
    )
    codex = AgentProfile(
        id="codex",
        displayName="Codex",
        capabilities=["verification", "review.correctness", "review.code", "testing.integration"],
    )
    
    registry.register_actor(gemini)
    registry.register_actor(claude)
    registry.register_actor(codex)
    return registry


class TestPhase8JobStateMachine(unittest.IsolatedAsyncioTestCase):
    async def test_job_state_machine_legal_and_illegal_transitions(self):
        """Test job state transitions enforce rules centrally and record history."""
        job = JobRecord(job_id="job_sm_1", goal="Test Job State Machine")
        self.assertEqual(job.state, JobState.CREATED)

        # Illegal transition directly to COMPLETED
        with self.assertRaises(InvalidStateTransitionError):
            job.transition_to(JobState.COMPLETED)

        # CREATED -> PLANNING
        job.transition_to(JobState.PLANNING)
        self.assertEqual(job.state, JobState.PLANNING)

        # PLANNING -> EXECUTING
        job.transition_to(JobState.EXECUTING)
        self.assertEqual(job.state, JobState.EXECUTING)

        # EXECUTING -> VERIFYING
        job.transition_to(JobState.VERIFYING)
        self.assertEqual(job.state, JobState.VERIFYING)

        # VERIFYING -> REPAIRING
        job.transition_to(JobState.REPAIRING)
        self.assertEqual(job.state, JobState.REPAIRING)
        self.assertEqual(job.repair_count, 1)

        # REPAIRING -> EXECUTING
        job.transition_to(JobState.EXECUTING)
        self.assertEqual(job.state, JobState.EXECUTING)

        # EXECUTING -> VERIFYING -> COMPLETED
        job.transition_to(JobState.VERIFYING)
        job.transition_to(JobState.COMPLETED)
        self.assertEqual(job.state, JobState.COMPLETED)
        self.assertTrue(job.is_terminal)

        # Transitioning out of terminal COMPLETED is illegal
        with self.assertRaises(InvalidStateTransitionError):
            job.transition_to(JobState.EXECUTING)


class TestPhase8ReactiveRuntimeScenarios(unittest.IsolatedAsyncioTestCase):
    async def test_scenario_a_dependency_scheduling(self):
        """
        Test A — dependency scheduling:
        T1 -> T2.
        T2 must not execute before T1 succeeds.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()
        engine = ReactiveJobEngine(
            job_id="job_test_a",
            goal="Test A - Dependency Scheduling",
            capability_registry=registry,
            event_bridge=events,
        )

        execution_order = []

        async def mock_exec(task: TaskNode, run: AgentRun, ctx: dict):
            execution_order.append(task.task_id)
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_exec)

        t1 = TaskNode(
            task_id="T1",
            job_id="job_test_a",
            description="Inspect repository",
            required_capabilities=["repo.read"],
        )
        t2 = TaskNode(
            task_id="T2",
            job_id="job_test_a",
            description="Identify relevant subsystem",
            dependencies=["T1"],
            required_capabilities=["review.architecture"],
        )

        await engine.initialize_and_plan(initial_tasks=[t1, t2])
        self.assertEqual(engine.state, JobState.EXECUTING)

        # Step 1: Only T1 should be ready and execute
        ready_before_t1 = engine.graph.find_ready_tasks()
        self.assertEqual([t.task_id for t in ready_before_t1], ["T1"])

        await engine.step()
        self.assertEqual(execution_order, ["T1"])
        self.assertEqual(engine.graph.get_task("T1").status, TaskStatus.SUCCEEDED)
        self.assertEqual(engine.graph.get_task("T2").status, TaskStatus.PENDING)

        # Step 2: Now T2 is ready and executes
        ready_after_t1 = engine.graph.find_ready_tasks()
        self.assertEqual([t.task_id for t in ready_after_t1], ["T2"])

        await engine.step()
        self.assertEqual(execution_order, ["T1", "T2"])
        self.assertEqual(engine.graph.get_task("T2").status, TaskStatus.SUCCEEDED)

        # Final step: verification -> complete
        await engine.step()
        self.assertEqual(engine.state, JobState.COMPLETED)

    async def test_scenario_b_parallel_scheduling(self):
        """
        Test B — parallel scheduling:
        T1 -> T2 and T3.
        T2 and T3 become READY after T1 and execute concurrently.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()
        engine = ReactiveJobEngine(
            job_id="job_test_b",
            goal="Test B - Parallel Scheduling",
            capability_registry=registry,
            event_bridge=events,
        )

        running_concurrently = set()
        max_concurrency_seen = 0

        async def mock_exec(task: TaskNode, run: AgentRun, ctx: dict):
            nonlocal max_concurrency_seen
            running_concurrently.add(task.task_id)
            max_concurrency_seen = max(max_concurrency_seen, len(running_concurrently))
            await asyncio.sleep(0.01)  # allow overlap
            running_concurrently.remove(task.task_id)
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_exec)

        t1 = TaskNode(task_id="T1", job_id="job_test_b", description="Setup", required_capabilities=["repo.read"])
        t2 = TaskNode(task_id="T2", job_id="job_test_b", description="Branch A", dependencies=["T1"], required_capabilities=["code.python"])
        t3 = TaskNode(task_id="T3", job_id="job_test_b", description="Branch B", dependencies=["T1"], required_capabilities=["frontend.react"])

        await engine.initialize_and_plan(initial_tasks=[t1, t2, t3])

        # Run T1
        await engine.step()
        self.assertEqual(engine.graph.get_task("T1").status, TaskStatus.SUCCEEDED)

        # Both T2 and T3 are ready
        ready_tasks = engine.graph.find_ready_tasks()
        ready_ids = {t.task_id for t in ready_tasks}
        self.assertEqual(ready_ids, {"T2", "T3"})

        # Execute T2 and T3 in parallel
        await engine.step()
        self.assertEqual(max_concurrency_seen, 2)

        # step() returns on FIRST_COMPLETED, so the second branch may still be in flight.
        # Drain it rather than assuming both timers fired in the same loop wakeup.
        for _ in range(5):
            if not engine.graph.has_running_tasks():
                break
            await engine.step()

        self.assertEqual(engine.graph.get_task("T2").status, TaskStatus.SUCCEEDED)
        self.assertEqual(engine.graph.get_task("T3").status, TaskStatus.SUCCEEDED)

    async def test_scenario_c_runtime_graph_expansion(self):
        """
        Test C — runtime graph expansion:
        Start with T1 -> T2.
        After T1 completes, expand graph with T3 and T4 without restarting the job.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()

        class DynamicPlanner:
            async def plan(self, req: ReplanRequest) -> ReplanResult:
                if req.reason == ReplanReason.OBSERVATION_DISCOVERY:
                    t3 = TaskNode(task_id="T3", job_id=req.job_id, description="Extra analysis", dependencies=["T1"], required_capabilities=["code.python"])
                    t4 = TaskNode(task_id="T4", job_id=req.job_id, description="Extra test", dependencies=["T3"], required_capabilities=["testing.unit"])
                    return ReplanResult(
                        mutations=[
                            GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t3),
                            GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t4),
                        ],
                        explanation="Added T3 and T4 following T1 observation",
                    )
                return ReplanResult()

        engine = ReactiveJobEngine(
            job_id="job_test_c",
            goal="Test C - Graph Expansion",
            capability_registry=registry,
            planner=DynamicPlanner(),
            event_bridge=events,
        )

        async def mock_exec(task: TaskNode, run: AgentRun, ctx: dict):
            if task.task_id == "T1":
                return TaskExecutionResult(
                    status="succeeded",
                    observations=[Observation(observation_id="obs1", job_id="job_test_c", kind="discovery", content="Subsystem needs deep analysis")],
                    metadata={"trigger_replan": True, "replan_reason": "Dynamic expansion required"},
                )
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_exec)

        t1 = TaskNode(task_id="T1", job_id="job_test_c", description="T1 initial", required_capabilities=["repo.read"])
        t2 = TaskNode(task_id="T2", job_id="job_test_c", description="T2 initial", dependencies=["T1"], required_capabilities=["frontend.react"])

        await engine.initialize_and_plan(initial_tasks=[t1, t2])
        self.assertEqual(engine.graph.count(), 2)

        # Step T1
        await engine.step()
        self.assertEqual(engine.graph.get_task("T1").status, TaskStatus.SUCCEEDED)
        # Graph now dynamically expanded with T3 and T4
        self.assertEqual(engine.graph.count(), 4)
        self.assertIsNotNone(engine.graph.get_task("T3"))
        self.assertIsNotNone(engine.graph.get_task("T4"))

        # Run remaining tasks until complete
        await engine.run_until_complete()
        self.assertEqual(engine.state, JobState.COMPLETED)
        self.assertTrue(engine.graph.is_all_completed())

    async def test_scenario_d_retry(self):
        """
        Test D — retry:
        Task fails once and succeeds on retry.
        Ensure attempt counter and events are correct.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()
        engine = ReactiveJobEngine(
            job_id="job_test_d",
            goal="Test D - Retry",
            capability_registry=registry,
            event_bridge=events,
        )

        attempt_history = []

        async def mock_exec(task: TaskNode, run: AgentRun, ctx: dict):
            attempt_history.append(task.attempt)
            if len(attempt_history) == 1:
                return TaskExecutionResult(status="failed", error="Transient network hiccup")
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_exec)

        t1 = TaskNode(
            task_id="T1",
            job_id="job_test_d",
            description="Flipping task",
            required_capabilities=["code.python"],
            max_attempts=2,
        )

        await engine.initialize_and_plan(initial_tasks=[t1])

        # First attempt: fails, reset to READY
        await engine.step()
        self.assertEqual(attempt_history, [1])
        task_after_first = engine.graph.get_task("T1")
        self.assertEqual(task_after_first.attempt, 1)
        self.assertEqual(task_after_first.status, TaskStatus.READY)

        # Second attempt: succeeds
        await engine.step()
        self.assertEqual(attempt_history, [1, 2])
        task_after_second = engine.graph.get_task("T1")
        self.assertEqual(task_after_second.attempt, 2)
        self.assertEqual(task_after_second.status, TaskStatus.SUCCEEDED)

        # Verify -> complete
        await engine.step()
        self.assertEqual(engine.state, JobState.COMPLETED)

        # Check captured events
        kinds = [e["kind"] for e in events.captured_events]
        self.assertIn("task.started", kinds)
        self.assertIn("task.failed", kinds)
        self.assertIn("task.completed", kinds)

    async def test_scenario_e_bounded_repair(self):
        """
        Test E — bounded repair:
        Verification fails initially with repair recommendation.
        Runtime enters VERIFYING -> REPAIRING -> EXECUTING.
        Repair task executes, next verification passes.
        Ensure repair budget is enforced if it keeps failing.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()

        verification_calls = 0

        async def mock_verify(job, graph, artifacts, ctx):
            nonlocal verification_calls
            verification_calls += 1
            if verification_calls == 1:
                return VerificationResult(
                    status=VerificationStatus.REPAIRABLE,
                    summary="Missing edge case tests",
                    repair_recommendations=[
                        {
                            "task_id": "T_REPAIR_1",
                            "description": "Add edge case unit test",
                            "required_capabilities": ["testing.unit"],
                        }
                    ],
                )
            return VerificationResult(status=VerificationStatus.PASSED, summary="All checks and repairs verified")

        engine = ReactiveJobEngine(
            job_id="job_test_e",
            goal="Test E - Bounded Repair",
            capability_registry=registry,
            verifier=mock_verify,
            event_bridge=events,
        )

        async def mock_exec(task: TaskNode, run: AgentRun, ctx: dict):
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_exec)

        t1 = TaskNode(task_id="T1", job_id="job_test_e", description="Build feature", required_capabilities=["implementation"])
        await engine.initialize_and_plan(initial_tasks=[t1])

        # Run T1
        await engine.step()
        self.assertEqual(engine.graph.get_task("T1").status, TaskStatus.SUCCEEDED)

        # Enter verification -> fails repairable -> enters REPAIRING -> schedules T_REPAIR_1 -> back to EXECUTING
        await engine.step()
        self.assertEqual(engine.job.repair_count, 1)
        self.assertEqual(engine.job.state, JobState.EXECUTING)
        self.assertIsNotNone(engine.graph.get_task("T_REPAIR_1"))

        # Run repair task
        await engine.step()
        self.assertEqual(engine.graph.get_task("T_REPAIR_1").status, TaskStatus.SUCCEEDED)

        # Next verification: passes -> COMPLETED
        await engine.step()
        self.assertEqual(engine.state, JobState.COMPLETED)
        self.assertEqual(verification_calls, 2)

    async def test_scenario_f_blocked_state(self):
        """
        Test F — blocked state:
        Task failure exhausts attempts, replanner has no solution / budget exhausted.
        Job becomes BLOCKED with a structured reason.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()

        engine = ReactiveJobEngine(
            job_id="job_test_f",
            goal="Test F - Blocked State",
            capability_registry=registry,
            limits=RuntimeLimits(max_replans_per_job=1, max_task_attempts=1),
            event_bridge=events,
        )

        async def mock_fail_exec(task: TaskNode, run: AgentRun, ctx: dict):
            return TaskExecutionResult(status="failed", error="Unrecoverable syntax error")

        engine.set_default_execution_adapter(mock_fail_exec)

        t1 = TaskNode(task_id="T1", job_id="job_test_f", description="Fatal task", required_capabilities=["code.python"], max_attempts=1)
        await engine.initialize_and_plan(initial_tasks=[t1])

        await engine.run_until_complete()

        self.assertEqual(engine.state, JobState.BLOCKED)
        self.assertIsNotNone(engine.job.blocked_reason)
        reason_str = str(engine.job.blocked_reason).lower()
        self.assertTrue("exhausted" in reason_str or "blocked" in reason_str)

    async def test_scenario_g_capability_routing(self):
        """
        Test G — capability routing:
        A task requiring 'review.code' must be assigned to an actor possessing that capability (e.g. claude/codex, not gemini).
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()
        engine = ReactiveJobEngine(
            job_id="job_test_g",
            goal="Test G - Capability Routing",
            capability_registry=registry,
            event_bridge=events,
        )

        assigned_actors = {}

        async def mock_exec(task: TaskNode, run: AgentRun, ctx: dict):
            assigned_actors[task.task_id] = run.actor_id
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_exec)

        t_review = TaskNode(
            task_id="T_REV",
            job_id="job_test_g",
            description="Architecture & Code Review",
            required_capabilities=["review.code", "review.architecture"],
        )
        t_impl = TaskNode(
            task_id="T_IMPL",
            job_id="job_test_g",
            description="Python Implementation",
            required_capabilities=["implementation", "code.python"],
        )

        await engine.initialize_and_plan(initial_tasks=[t_review, t_impl])
        await engine.run_until_complete()

        self.assertEqual(assigned_actors["T_REV"], "claude")
        self.assertEqual(assigned_actors["T_IMPL"], "gemini")

    async def test_scenario_h_no_premature_completion(self):
        """
        Test H — no premature completion:
        Job may only become COMPLETED when all required work finished AND verification passed.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()

        # Verifier that deliberately fails
        async def failing_verifier(job, graph, artifacts, ctx):
            return VerificationResult(status=VerificationStatus.FAILED, summary="Hard requirement failed")

        engine = ReactiveJobEngine(
            job_id="job_test_h",
            goal="Test H - No Premature Completion",
            capability_registry=registry,
            verifier=failing_verifier,
            event_bridge=events,
        )

        async def mock_exec(task: TaskNode, run: AgentRun, ctx: dict):
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_exec)

        t1 = TaskNode(task_id="T1", job_id="job_test_h", description="Task 1", required_capabilities=["repo.read"])
        await engine.initialize_and_plan(initial_tasks=[t1])

        await engine.step()  # executes T1 -> SUCCEEDED
        self.assertEqual(engine.graph.get_task("T1").status, TaskStatus.SUCCEEDED)
        self.assertEqual(engine.state, JobState.VERIFYING)

        await engine.step()  # verification fails -> FAILED
        self.assertEqual(engine.state, JobState.FAILED)
        self.assertNotEqual(engine.state, JobState.COMPLETED)

    async def test_acceptance_scenario_end_to_end(self):
        """
        Full Phase 8 Acceptance Scenario (Section 19):
        Goal: "Inspect a repository, identify a frontend regression, fix it, test it, and have another agent review the patch."
        1. PLANNING -> T1 inspect repository (Gemini)
        2. EXECUTING -> Gemini executes T1.
           Observation: "Regression appears related to canvas interaction."
        3. Planner expands graph:
           T2 reproduce issue
           T3 inspect recent frontend changes
           (T2 and T3 execute in parallel)
        4. Claude reports probable root cause.
           Runtime adds: T4 implement fix, T5 run frontend tests.
           T4 succeeds, T5 succeeds.
        5. VERIFYING -> Codex reviews patch.
           Codex finds mobile regression.
        6. REPAIRING -> Runtime adds:
           T6 fix mobile regression, T7 rerun tests, T8 final review.
        7. Execution continues -> VERIFYING -> Final review passes -> COMPLETED.
        """
        events = RuntimeEventBridge()
        registry = create_test_capability_registry()

        plan_stage = 0

        class AcceptancePlanner:
            async def plan(self, req: ReplanRequest) -> ReplanResult:
                nonlocal plan_stage
                if req.reason == ReplanReason.INITIAL_PLAN:
                    t1 = TaskNode(task_id="T1", job_id=req.job_id, description="Inspect repository", required_capabilities=["repo.read"])
                    return ReplanResult(mutations=[GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t1)], explanation="Initial plan: inspect repo")

                elif req.reason == ReplanReason.OBSERVATION_DISCOVERY:
                    plan_stage += 1
                    if plan_stage == 1:
                        # Expand with T2 and T3 in parallel
                        t2 = TaskNode(task_id="T2", job_id=req.job_id, description="Reproduce issue", dependencies=["T1"], required_capabilities=["code.python"])
                        t3 = TaskNode(task_id="T3", job_id=req.job_id, description="Inspect recent frontend changes", dependencies=["T1"], required_capabilities=["frontend.react"])
                        return ReplanResult(
                            mutations=[
                                GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t2),
                                GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t3),
                            ],
                            explanation="Parallel investigation of canvas regression",
                        )
                    elif plan_stage == 2:
                        # Add fix T4 and test T5
                        t4 = TaskNode(task_id="T4", job_id=req.job_id, description="Implement fix", dependencies=["T2", "T3"], required_capabilities=["implementation", "frontend.react"])
                        t5 = TaskNode(task_id="T5", job_id=req.job_id, description="Run frontend tests", dependencies=["T4"], required_capabilities=["testing.unit"])
                        return ReplanResult(
                            mutations=[
                                GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t4),
                                GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t5),
                            ],
                            explanation="Implementation and testing of canvas fix",
                        )

                elif req.reason == ReplanReason.VERIFICATION_REPAIR:
                    # Add T6, T7, T8
                    t6 = TaskNode(task_id="T6", job_id=req.job_id, description="Fix mobile regression", required_capabilities=["implementation", "frontend.react"])
                    t7 = TaskNode(task_id="T7", job_id=req.job_id, description="Rerun frontend tests", dependencies=["T6"], required_capabilities=["testing.unit"])
                    t8 = TaskNode(task_id="T8", job_id=req.job_id, description="Final review", dependencies=["T7"], required_capabilities=["review.code"])
                    return ReplanResult(
                        mutations=[
                            GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t6),
                            GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t7),
                            GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=t8),
                        ],
                        explanation="Repair mobile regression and re-verify",
                    )

                return ReplanResult()

        verify_attempts = 0

        async def acceptance_verifier(job, graph, artifacts, ctx):
            nonlocal verify_attempts
            verify_attempts += 1
            if verify_attempts == 1:
                return VerificationResult(
                    status=VerificationStatus.REPAIRABLE,
                    verifier_id="codex",
                    summary="Codex review found mobile viewport regression in canvas interaction.",
                    checks=[
                        VerificationCheck(name="desktop_tests", passed=True),
                        VerificationCheck(name="mobile_viewport", passed=False, repairable=True, detail="Touch drag event not handled"),
                    ],
                )
            return VerificationResult(
                status=VerificationStatus.PASSED,
                verifier_id="codex",
                summary="Final review passed: all canvas interaction and mobile touch events verified.",
                checks=[
                    VerificationCheck(name="desktop_tests", passed=True),
                    VerificationCheck(name="mobile_viewport", passed=True),
                    VerificationCheck(name="code_review", passed=True),
                ],
            )

        engine = ReactiveJobEngine(
            job_id="job_acceptance",
            goal="Inspect a repository, identify a frontend regression, fix it, test it, and have another agent review the patch.",
            capability_registry=registry,
            planner=AcceptancePlanner(),
            verifier=acceptance_verifier,
            event_bridge=events,
        )

        executed_tasks = []

        async def mock_actor_executor(task: TaskNode, run: AgentRun, ctx: dict):
            executed_tasks.append((task.task_id, run.actor_id))
            if task.task_id == "T1":
                return TaskExecutionResult(
                    status="succeeded",
                    observations=[Observation(observation_id="obs_canvas", job_id="job_acceptance", kind="discovery", content="Regression appears related to canvas interaction.")],
                    metadata={"trigger_replan": True, "replan_reason": "Canvas observation requires parallel investigation"},
                )
            elif task.task_id in {"T2", "T3"}:
                if task.task_id == "T3":
                    return TaskExecutionResult(
                        status="succeeded",
                        observations=[Observation(observation_id="obs_cause", job_id="job_acceptance", kind="hypothesis", content="Event listener missing passive flag")],
                        metadata={"trigger_replan": True, "replan_reason": "Root cause identified; ready for fix"},
                    )
                return TaskExecutionResult(status="succeeded")
            return TaskExecutionResult(status="succeeded")

        engine.set_default_execution_adapter(mock_actor_executor)

        final_job = await engine.run_until_complete()

        self.assertEqual(final_job.state, JobState.COMPLETED)
        self.assertEqual(verify_attempts, 2)
        self.assertEqual(final_job.repair_count, 1)

        executed_task_ids = [tid for tid, _ in executed_tasks]
        # Check all expected tasks were executed
        self.assertIn("T1", executed_task_ids)
        self.assertIn("T2", executed_task_ids)
        self.assertIn("T3", executed_task_ids)
        self.assertIn("T4", executed_task_ids)
        self.assertIn("T5", executed_task_ids)
        self.assertIn("T6", executed_task_ids)
        self.assertIn("T7", executed_task_ids)
        self.assertIn("T8", executed_task_ids)

        # Verify capability routing occurred
        actor_map = dict(executed_tasks)
        self.assertEqual(actor_map["T1"], "claude")  # repo.read
        self.assertEqual(actor_map["T4"], "gemini")  # implementation
        self.assertTrue(actor_map["T8"] in {"claude", "codex"})  # review.code
