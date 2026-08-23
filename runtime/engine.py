import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Union

from runtime.job_state import JobRecord, JobState, TERMINAL_JOB_STATES
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.observations import Observation, ObservationRegistry, default_observation_registry
from runtime.execution import ExecutionManager, ActorAdapter
from runtime.verification import (
    VerificationResult,
    VerificationStatus,
    VerifierAdapter,
    DefaultPassVerifierAdapter,
    CallableVerifierAdapter,
)
from runtime.limits import RuntimeLimits
from runtime.replanning import (
    ReplanReason,
    ReplanRequest,
    ReplanResult,
    GraphMutation,
    GraphMutationType,
    PlannerAdapter,
    CallablePlannerAdapter,
    BoundedReplanner,
)
from runtime.events import RuntimeEventBridge
from runtime.scheduler import ReactiveScheduler
from capabilities.capabilities import CapabilityRegistry, default_capability_registry

logger = logging.getLogger("hermes.runtime.engine")


class ReactiveJobEngine:
    """
    Authoritative reactive runtime execution engine.
    Orchestrates the entire job lifecycle:
    goal -> job -> PLANNING -> initial graph -> event-driven scheduler -> execution ->
    observations + artifacts -> VERIFYING -> bounded repair/replan -> COMPLETED/BLOCKED.
    """

    def __init__(
        self,
        job_id: str,
        goal: str,
        title: Optional[str] = None,
        repository: Optional[str] = None,
        branch: Optional[str] = None,
        priority: str = "P1",
        limits: Optional[RuntimeLimits] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        observation_registry: Optional[ObservationRegistry] = None,
        execution_manager: Optional[ExecutionManager] = None,
        actor_adapter: Optional[Union[ActorAdapter, Callable, Any]] = None,
        default_adapter: Optional[Union[ActorAdapter, Callable, Any]] = None,
        verifier: Optional[Union[VerifierAdapter, Callable, Any]] = None,
        planner: Optional[Union[PlannerAdapter, Callable, Any]] = None,
        event_bridge: Optional[RuntimeEventBridge] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.limits = limits or RuntimeLimits()
        self.event_bridge = event_bridge or RuntimeEventBridge()

        self.job = JobRecord(
            job_id=job_id,
            goal=goal,
            title=title or goal[:80],
            repository=repository,
            branch=branch,
            priority=priority,
            metadata=metadata or {},
        )

        self.graph = TaskGraph(job_id=job_id)
        self.capability_registry = capability_registry or default_capability_registry
        self.observation_registry = observation_registry or default_observation_registry
        self.execution_manager = execution_manager or ExecutionManager()
        adapter_to_set = actor_adapter or default_adapter
        if adapter_to_set:
            self.execution_manager.set_default_adapter(adapter_to_set)

        self.bounded_replanner = BoundedReplanner(limits=self.limits)
        self.scheduler = ReactiveScheduler(
            capability_registry=self.capability_registry,
            limits=self.limits,
            event_bridge=self.event_bridge,
        )

        # Set up verifier
        if verifier is None:
            self.verifier: VerifierAdapter = DefaultPassVerifierAdapter()
        elif hasattr(verifier, "verify"):
            self.verifier = verifier
        elif callable(verifier):
            self.verifier = CallableVerifierAdapter(verifier)
        else:
            raise TypeError("verifier must have a verify() method or be callable")

        # Set up planner
        if planner is None:
            self.planner: Optional[PlannerAdapter] = None
        elif hasattr(planner, "plan"):
            self.planner = planner
        elif callable(planner):
            self.planner = CallablePlannerAdapter(planner)
        else:
            raise TypeError("planner must have a plan() method or be callable")

        self._artifacts: List[Dict[str, Any]] = []
        self._last_verification_result: Optional[VerificationResult] = None
        self._active_async_tasks: Set[asyncio.Task] = set()

        # Emit initial job created
        self.event_bridge.emit_job_created(self.job)

    @property
    def state(self) -> JobState:
        return self.job.state

    @property
    def actor_adapter(self) -> Optional[ActorAdapter]:
        return self.execution_manager.default_adapter if self.execution_manager else None

    @property
    def is_terminal(self) -> bool:
        return self.job.is_terminal

    def get_artifacts(self) -> List[Dict[str, Any]]:
        all_artifacts = list(self._artifacts)
        for t in self.graph.list_tasks():
            for art in t.artifact_refs:
                if art not in all_artifacts:
                    all_artifacts.append(art)
        return all_artifacts

    def register_actor(self, profile: Any) -> None:
        self.capability_registry.register_actor(profile)

    def register_execution_adapter(self, actor_id: str, adapter: Union[ActorAdapter, Callable]) -> None:
        self.execution_manager.register_adapter(actor_id, adapter)

    def set_default_execution_adapter(self, adapter: Union[ActorAdapter, Callable]) -> None:
        self.execution_manager.set_default_adapter(adapter)

    def set_planner(self, planner: Union[PlannerAdapter, Callable, Any]) -> None:
        if hasattr(planner, "plan"):
            self.planner = planner
        elif callable(planner):
            self.planner = CallablePlannerAdapter(planner)
        else:
            self.planner = None

    def set_verifier(self, verifier: Union[VerifierAdapter, Callable, Any]) -> None:
        if hasattr(verifier, "verify"):
            self.verifier = verifier
        elif callable(verifier):
            self.verifier = CallableVerifierAdapter(verifier)
        else:
            self.verifier = DefaultPassVerifierAdapter()

    async def initialize_and_plan(
        self,
        initial_tasks: Optional[List[Union[TaskNode, Dict[str, Any]]]] = None,
    ) -> None:
        """
        Initial decomposition phase: transitions job CREATED -> PLANNING -> EXECUTING.
        """
        if self.job.state != JobState.CREATED:
            logger.warning("Job %s is not in CREATED state; skipping initialize_and_plan", self.job.job_id)
            return

        self.job.transition_to(JobState.PLANNING, reason="Starting initial plan decomposition", event_bridge=self.event_bridge)

        # 1. Add provided initial tasks (enforcing authoritative runtime limits)
        if initial_tasks:
            for t in initial_tasks:
                if self.graph.count() >= self.limits.max_tasks_per_job:
                    logger.warning("Max tasks limit (%d) reached; skipping task", self.limits.max_tasks_per_job)
                    break
                if isinstance(t, dict):
                    node = TaskNode.from_dict(t)
                else:
                    node = t
                node.max_attempts = min(node.max_attempts, self.limits.max_task_attempts)
                try:
                    added_node = self.graph.add_task(node)
                    self.event_bridge.emit_task_created(added_node, reason="initial_task")
                except ValueError as e:
                    logger.warning("Initial task addition skipped: %s", e)

        # 2. If planner is configured and graph is still empty (or planner wants to augment)
        if self.planner:
            replan_req = ReplanRequest(
                job_id=self.job.job_id,
                goal=self.job.goal,
                reason=ReplanReason.INITIAL_PLAN,
                completed_tasks=[],
                failed_tasks=[],
                current_graph=self.graph,
                new_observations=self.observation_registry.list_for_job(self.job.job_id),
                produced_artifacts=self.get_artifacts(),
                replan_budget_remaining=max(0, self.limits.max_replans_per_job - self.job.replan_count),
            )
            plan_res = await self.planner.plan(replan_req)
            self.bounded_replanner.apply_mutations(self.graph, plan_res, self.job.job_id, self.event_bridge)
            self.event_bridge.emit_replan_completed(self.job.job_id, len(plan_res.mutations), plan_res.explanation)

        if self.graph.count() == 0:
            self.job.transition_to(
                JobState.BLOCKED,
                reason="Initial planning produced zero executable tasks",
                event_bridge=self.event_bridge,
            )
            return

        self.job.transition_to(JobState.EXECUTING, reason="Initial plan decomposition completed", event_bridge=self.event_bridge)

    async def request_replan(self, reason: Union[ReplanReason, str], detail: Optional[str] = None) -> bool:
        """
        Bounded replan trigger. Invokes planner with current state and observations.
        """
        if self.job.replan_count >= self.limits.max_replans_per_job:
            logger.warning("Replan limit reached for job %s (%d/%d)", self.job.job_id, self.job.replan_count, self.limits.max_replans_per_job)
            self.job.transition_to(
                JobState.BLOCKED,
                reason=f"Exhausted maximum allowed replans ({self.limits.max_replans_per_job}): {detail or reason}",
                event_bridge=self.event_bridge,
            )
            return False

        if not self.planner:
            logger.info("No planner configured for job %s; cannot replan", self.job.job_id)
            return False

        # Transition to PLANNING
        if self.job.can_transition_to(JobState.PLANNING):
            self.job.transition_to(
                JobState.PLANNING,
                reason=f"Replanning triggered: {reason}",
                event_bridge=self.event_bridge,
                metadata={"replan_reason": str(reason), "replan_detail": detail},
            )

        budget_remaining = max(0, self.limits.max_replans_per_job - self.job.replan_count)
        self.event_bridge.emit_replan_requested(self.job.job_id, str(reason), budget_remaining)

        completed_tasks = [t for t in self.graph.list_tasks() if t.status == TaskStatus.SUCCEEDED]
        failed_tasks = [t for t in self.graph.list_tasks() if t.status == TaskStatus.FAILED]

        replan_req = ReplanRequest(
            job_id=self.job.job_id,
            goal=self.job.goal,
            reason=reason,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            current_graph=self.graph,
            new_observations=self.observation_registry.list_for_job(self.job.job_id),
            produced_artifacts=self.get_artifacts(),
            replan_budget_remaining=budget_remaining,
            detail=detail,
        )

        plan_res = await self.planner.plan(replan_req)
        affected = self.bounded_replanner.apply_mutations(self.graph, plan_res, self.job.job_id, self.event_bridge)
        self.event_bridge.emit_replan_completed(self.job.job_id, len(plan_res.mutations), plan_res.explanation)

        if not plan_res.should_continue or (not self.graph.has_active_tasks() and not self.graph.is_all_completed()):
            self.job.transition_to(
                JobState.BLOCKED,
                reason=f"Planner concluded execution cannot proceed: {plan_res.explanation}",
                event_bridge=self.event_bridge,
            )
            return False

        # Transition back to EXECUTING
        if self.job.can_transition_to(JobState.EXECUTING):
            self.job.transition_to(
                JobState.EXECUTING,
                reason="Applying replanned task graph",
                event_bridge=self.event_bridge,
            )
        return True

    async def step(self) -> bool:
        """
        Executes a single reactive progression cycle.
        Returns True if the engine should continue cycling, False if job reached terminal state.
        """
        if self.is_terminal:
            return False

        # 1. State: CREATED -> trigger initialize_and_plan
        if self.job.state == JobState.CREATED:
            await self.initialize_and_plan()
            return not self.is_terminal

        # 2. State: EXECUTING
        if self.job.state == JobState.EXECUTING:
            # Check if all tasks in graph are already succeeded
            if self.graph.is_all_completed():
                self.job.transition_to(JobState.VERIFYING, reason="All tasks succeeded; entering verification", event_bridge=self.event_bridge)
                return True

            # Schedule and launch any newly ready tasks
            new_async_tasks = await self.scheduler.schedule_ready_tasks(
                graph=self.graph,
                execution_manager=self.execution_manager,
                context={"job": self.job.to_dict()},
            )
            for t in new_async_tasks:
                self._active_async_tasks.add(t)

            if self._active_async_tasks:
                # Wait for FIRST completed task (allows newly ready dependent tasks to dispatch immediately without waiting for unrelated slow tasks)
                done, pending = await asyncio.wait(
                    self._active_async_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                self._active_async_tasks = pending

                for completed_task in done:
                    try:
                        res = completed_task.result()
                        if isinstance(res, tuple) and len(res) == 2:
                            task_node, exec_res = res
                            # Ingest observations
                            for obs in exec_res.observations:
                                if isinstance(obs, Observation):
                                    self.observation_registry.register(obs)
                                    self.event_bridge.emit_observation_created(obs)
                                elif isinstance(obs, dict):
                                    registered = self.observation_registry.add_observation(
                                        job_id=self.job.job_id,
                                        kind=obs.get("kind", "discovery"),
                                        content=obs.get("content", ""),
                                        task_id=task_node.task_id,
                                        actor_id=task_node.assigned_actor,
                                        metadata=obs.get("metadata", {}),
                                    )
                                    self.event_bridge.emit_observation_created(registered)

                            # Check if execution result explicitly requests replan
                            if exec_res.metadata.get("trigger_replan"):
                                await self.request_replan(
                                    reason=ReplanReason.OBSERVATION_DISCOVERY,
                                    detail=exec_res.metadata.get("replan_reason", "Observation triggered dynamic plan expansion"),
                                )
                                if self.is_terminal:
                                    return False
                    except Exception as exc:
                        logger.error("Error processing completed task: %s", exc)

            if self.is_terminal:
                return False

            # Check after execution batch
            if self.graph.is_all_completed():
                self.job.transition_to(JobState.VERIFYING, reason="All tasks succeeded; entering verification", event_bridge=self.event_bridge)
                return True

            # Check for permanent task failures (exhausted retries)
            failed_tasks = [t for t in self.graph.list_tasks() if t.status == TaskStatus.FAILED]
            if failed_tasks and not self.graph.has_running_tasks():
                failed_desc = ", ".join([f"{t.task_id} (attempt {t.attempt}/{t.max_attempts})" for t in failed_tasks])
                logger.info("Task failures detected: %s. Attempting replan.", failed_desc)
                replanned = await self.request_replan(
                    reason=ReplanReason.TASK_FAILURE,
                    detail=f"Task(s) {failed_desc} exhausted max attempts",
                )
                if not replanned and not self.is_terminal:
                    self.job.transition_to(
                        JobState.BLOCKED,
                        reason=f"Task failure exhausted retries and replan failed: {failed_desc}",
                        event_bridge=self.event_bridge,
                    )
                return not self.is_terminal

            # Check if graph is stalled (dependency deadlock or unrunnable pending tasks)
            if self.graph.is_stalled():
                blocked_tasks = self.graph.find_dependency_blocked_tasks()
                logger.info("Execution stalled (%d blocked tasks). Incomplete tasks cannot run. Attempting replan.", len(blocked_tasks))
                replanned = await self.request_replan(
                    reason=ReplanReason.RUNTIME_BLOCKED,
                    detail=f"{len(blocked_tasks)} tasks blocked by dependency failures",
                )
                if not replanned and not self.is_terminal:
                    self.job.transition_to(
                        JobState.BLOCKED,
                        reason="Task graph blocked: no tasks are ready and all paths are exhausted",
                        event_bridge=self.event_bridge,
                    )
                return not self.is_terminal

            return not self.is_terminal

        # 3. State: VERIFYING
        if self.job.state == JobState.VERIFYING:
            verifier_id = getattr(self.verifier, "verifier_id", "verifier")
            self.event_bridge.emit_verification_started(self.job.job_id, verifier_id)

            artifacts = self.get_artifacts()
            ver_res = await self.verifier.verify(
                job=self.job,
                graph=self.graph,
                artifacts=artifacts,
                context={"job": self.job.to_dict()},
            )
            self._last_verification_result = ver_res

            if ver_res.is_passed:
                self.event_bridge.emit_verification_passed(self.job.job_id, ver_res)
                self.job.transition_to(
                    JobState.COMPLETED,
                    reason=f"Verification passed: {ver_res.summary}",
                    event_bridge=self.event_bridge,
                )
                return False

            elif ver_res.is_repairable:
                self.event_bridge.emit_verification_failed(self.job.job_id, ver_res)

                if self.job.repair_count >= self.limits.max_repairs_per_job:
                    self.job.transition_to(
                        JobState.BLOCKED,
                        reason=f"Verification failed after {self.limits.max_repairs_per_job} repair cycles: {ver_res.summary}",
                        event_bridge=self.event_bridge,
                    )
                    return False

                self.job.transition_to(
                    JobState.REPAIRING,
                    reason=f"Verification failed (repairable cycle {self.job.repair_count + 1}): {ver_res.summary}",
                    event_bridge=self.event_bridge,
                )

                # Add repair recommendations to graph
                added_any = False
                if ver_res.repair_recommendations:
                    for rec in ver_res.repair_recommendations:
                        try:
                            node = self.graph.add_task(rec)
                            node.max_attempts = min(node.max_attempts, self.limits.max_task_attempts)
                            self.event_bridge.emit_task_created(node, reason="repair_recommendation")
                            added_any = True
                        except ValueError as e:
                            logger.warning("Duplicate repair task skipped: %s", e)

                # If planner is available, allow planner to generate repair tasks
                if self.planner:
                    await self.request_replan(
                        reason=ReplanReason.VERIFICATION_REPAIR,
                        detail=ver_res.summary,
                    )
                    added_any = True

                # Terminal check after replanning (prevent transition from BLOCKED -> EXECUTING)
                if self.is_terminal:
                    return False

                if not added_any:
                    # Default generic repair task if nothing was specified
                    r_task = TaskNode(
                        task_id=f"repair_task_{self.job.repair_count}",
                        job_id=self.job.job_id,
                        description=f"Address verification issue: {ver_res.summary}",
                        required_capabilities=["implementation"],
                    )
                    r_task.max_attempts = min(r_task.max_attempts, self.limits.max_task_attempts)
                    try:
                        self.graph.add_task(r_task)
                        self.event_bridge.emit_task_created(r_task, reason="default_repair")
                    except ValueError:
                        pass

                if self.is_terminal:
                    return False

                self.job.transition_to(
                    JobState.EXECUTING,
                    reason="Repair tasks scheduled; resuming execution",
                    event_bridge=self.event_bridge,
                )
                return True

            else:
                # Hard failure
                self.event_bridge.emit_verification_failed(self.job.job_id, ver_res)
                self.job.transition_to(
                    JobState.FAILED,
                    reason=f"Verification failed irreversibly: {ver_res.summary}",
                    event_bridge=self.event_bridge,
                )
                return False

        return False

    async def run_until_complete(self, max_steps: int = 100) -> JobRecord:
        """
        Drives the engine in a loop until a terminal state is reached or max_steps is exceeded.
        """
        step_count = 0
        while not self.is_terminal and step_count < max_steps:
            step_count += 1
            should_continue = await self.step()
            if not should_continue:
                break

        if not self.is_terminal:
            self.job.transition_to(
                JobState.BLOCKED,
                reason=f"Execution exceeded maximum step limit ({max_steps})",
                event_bridge=self.event_bridge,
            )

        return self.job
