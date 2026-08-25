import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from runtime.job_state import JobRecord, JobState, TERMINAL_JOB_STATES
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.observations import Observation, ObservationRegistry, default_observation_registry
from runtime.execution import ExecutionManager, ActorAdapter, AgentRunStatus
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

    Enforces strict durable commit semantics:
    Every state change, task transition, and execution outcome is persisted
    to the canonical event store before advancing runtime orchestration.
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
        capacity_registry: Optional[Any] = None,
        circuit_registry: Optional[Any] = None,
        reroute_policy: Optional[Any] = None,
        event_bridge: Optional[RuntimeEventBridge] = None,
        event_store: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.limits = limits or RuntimeLimits()
        self.event_bridge = event_bridge or RuntimeEventBridge()
        if event_store is not None:
            self.event_bridge.set_store(event_store)

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
        self.capacity_registry = capacity_registry
        self.circuit_registry = circuit_registry
        self.reroute_policy = reroute_policy
        self.scheduler = ReactiveScheduler(
            capability_registry=self.capability_registry,
            capacity_registry=self.capacity_registry,
            circuit_registry=self.circuit_registry,
            reroute_policy=self.reroute_policy,
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
        self._discovery_triggered: Set[str] = set()
        self._job_created_emitted = False
        self._job_cancel_persisted = False
        self._durable_cancel_completed = False
        self._pre_cancel_state: Optional[JobState] = None
        self._pending_initial_tasks: List[Any] = []

    @property
    def state(self) -> JobState:
        return self.job.state

    @property
    def actor_adapter(self) -> Optional[ActorAdapter]:
        return self.execution_manager.default_adapter if self.execution_manager else None

    @property
    def default_execution_adapter(self) -> Optional[ActorAdapter]:
        return self.actor_adapter

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

    async def _ensure_job_created_emitted(self) -> None:
        if not self._job_created_emitted:
            await self.event_bridge.emit_job_created(self.job)
            self._job_created_emitted = True

        while self._pending_initial_tasks:
            t = self._pending_initial_tasks[0]
            task_id = t.task_id if hasattr(t, "task_id") else (t.get("task_id") if isinstance(t, dict) else None)
            node = self.graph.get_task(task_id) if task_id else None
            if not node:
                try:
                    node = self.graph.add_task(t)
                except ValueError:
                    node = self.graph.get_task(task_id)
            if node:
                await self.event_bridge.emit_task_created(node, reason="initial_task")
            # Pop task only after successful persistence
            self._pending_initial_tasks.pop(0)

    async def _transition_job(
        self,
        target_state: Union[JobState, str],
        reason: Optional[Union[Dict[str, Any], str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobState:
        """
        Durable job state transition helper.
        Transitions the JobRecord state machine and immediately awaits durable emission of job.state_changed.
        Rolls back in-memory state from full snapshot if persistence fails.
        """
        await self._ensure_job_created_emitted()
        prev_state = self.job.state
        snapshot = self.job.snapshot()
        new_state = self.job.transition_to(target_state, reason=reason, metadata=metadata)
        if prev_state != new_state:
            try:
                await self.event_bridge.emit_job_state_changed(
                    job=self.job,
                    previous_state=prev_state,
                    reason=reason,
                    metadata=metadata,
                )
            except Exception:
                # Restore full JobRecord snapshot on persistence failure
                self.job.restore(snapshot)
                raise
        return new_state

    async def initialize_and_plan(
        self,
        initial_tasks: Optional[List[Union[TaskNode, Dict[str, Any]]]] = None,
    ) -> None:
        """
        Initial decomposition phase: transitions job CREATED -> PLANNING -> EXECUTING.
        """
        await self._ensure_job_created_emitted()
        if self.job.state != JobState.CREATED:
            logger.warning("Job %s is not in CREATED state; skipping initialize_and_plan", self.job.job_id)
            return

        await self._transition_job(JobState.PLANNING, reason="Starting initial plan decomposition")

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
                    await self.event_bridge.emit_task_created(added_node, reason="initial_task")
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
            self.bounded_replanner.apply_mutations(self.graph, plan_res, self.job.job_id)
            for mutation in plan_res.mutations:
                if mutation.mutation_type == GraphMutationType.ADD_TASK and mutation.task:
                    if self.graph.get_task(mutation.task.task_id):
                        await self.event_bridge.emit_task_created(mutation.task, reason=mutation.reason)
                elif mutation.mutation_type == GraphMutationType.SUPERSEDE_TASK and mutation.task_id:
                    await self.event_bridge.emit_task_superseded(
                        task_id=mutation.task_id,
                        job_id=self.job.job_id,
                        superseded_by=mutation.depends_on_task_id,
                        reason=mutation.reason,
                    )
            await self.event_bridge.emit_replan_completed(self.job.job_id, len(plan_res.mutations), plan_res.explanation)

        if self.graph.count() == 0:
            await self._transition_job(
                JobState.BLOCKED,
                reason="Initial planning produced zero executable tasks",
            )
            await self.event_bridge.flush()
            return

        await self._transition_job(JobState.EXECUTING, reason="Initial plan decomposition completed")
        await self.event_bridge.flush()

    async def request_replan(
        self,
        reason: Union[ReplanReason, str],
        detail: Optional[str] = None,
        block_on_no_progress: bool = True,
    ) -> bool:
        """
        Bounded replan trigger. Invokes planner with current state and observations.
        """
        if self.job.replan_count >= self.limits.max_replans_per_job:
            logger.warning("Replan limit reached for job %s (%d/%d)", self.job.job_id, self.job.replan_count, self.limits.max_replans_per_job)
            await self._transition_job(
                JobState.BLOCKED,
                reason=f"Exhausted maximum allowed replans ({self.limits.max_replans_per_job}): {detail or reason}",
            )
            return False

        if not self.planner:
            logger.info("No planner configured for job %s; cannot replan", self.job.job_id)
            return False

        # Transition to PLANNING
        if self.job.can_transition_to(JobState.PLANNING):
            await self._transition_job(
                JobState.PLANNING,
                reason=f"Replanning triggered: {reason}",
                metadata={"replan_reason": str(reason), "replan_detail": detail},
            )

        budget_remaining = max(0, self.limits.max_replans_per_job - self.job.replan_count)
        await self.event_bridge.emit_replan_requested(self.job.job_id, str(reason), budget_remaining)

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
        self.bounded_replanner.apply_mutations(self.graph, plan_res, self.job.job_id)
        for mutation in plan_res.mutations:
            if mutation.mutation_type == GraphMutationType.ADD_TASK and mutation.task:
                if self.graph.get_task(mutation.task.task_id):
                    await self.event_bridge.emit_task_created(mutation.task, reason=mutation.reason)
            elif mutation.mutation_type == GraphMutationType.SUPERSEDE_TASK and mutation.task_id:
                await self.event_bridge.emit_task_superseded(
                    task_id=mutation.task_id,
                    job_id=self.job.job_id,
                    superseded_by=mutation.depends_on_task_id,
                    reason=mutation.reason,
                )
        await self.event_bridge.emit_replan_completed(self.job.job_id, len(plan_res.mutations), plan_res.explanation)

        made_no_progress = not plan_res.should_continue or (
            not self.graph.has_active_tasks() and not self.graph.is_all_completed()
        )
        if made_no_progress and block_on_no_progress:
            await self._transition_job(
                JobState.BLOCKED,
                reason=f"Planner concluded execution cannot proceed: {plan_res.explanation}",
            )
            return False

        # Transition back to EXECUTING
        if self.job.can_transition_to(JobState.EXECUTING):
            await self._transition_job(
                JobState.EXECUTING,
                reason="Applying replanned task graph",
            )
        await self.event_bridge.flush()
        return not made_no_progress

    async def _cancel_active_tasks(self, reason: str) -> int:
        """
        Cancels every in-flight execution task and waits for the cancellations to settle.
        """
        pending = {t for t in self._active_async_tasks if not t.done()}
        self._active_async_tasks = set()
        if not pending:
            return 0

        logger.info("Cancelling %d in-flight task(s) for job %s: %s", len(pending), self.job.job_id, reason)
        for t in pending:
            t.cancel()

        results = await asyncio.gather(*pending, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception) and not isinstance(res, asyncio.CancelledError):
                logger.error("Exception occurred during task cancellation worker drain: %s", res)
                from runtime.storage.event_store import EventStoreError
                if isinstance(res, EventStoreError):
                    raise res
        return len(pending)

    def request_cancel(self, reason: str = "Job cancelled by operator") -> bool:
        """
        Synchronously cancels the job: transitions to CANCELLED, marks unfinished tasks
        cancelled, and signals every in-flight execution task to stop.
        """
        if self._durable_cancel_completed:
            return False

        if not self._pre_cancel_state and self.job.state != JobState.CANCELLED:
            self._pre_cancel_state = self.job.state

        self.job.transition_to(JobState.CANCELLED, reason=reason)
        for task in self.graph.list_tasks():
            if task.status in (TaskStatus.RUNNING, TaskStatus.READY, TaskStatus.PENDING):
                self.graph.mark_cancelled(task.task_id, reason=reason)

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        for t in list(self._active_async_tasks):
            if t.done():
                continue
            task_loop = t.get_loop()
            if task_loop is current_loop or not task_loop.is_running():
                t.cancel()
            else:
                task_loop.call_soon_threadsafe(t.cancel)
        return True

    async def cancel(self, reason: str = "Job cancelled by operator") -> bool:
        """
        Cancels the job and waits for in-flight execution to settle, emitting canonical cancellation events.
        """
        if self._durable_cancel_completed:
            return False

        # Milestone 1: Persist job.cancelled event once
        if not self._job_cancel_persisted:
            if self.job.state != JobState.CANCELLED:
                await self._transition_job(JobState.CANCELLED, reason=reason)
            else:
                prev_state = self._pre_cancel_state or JobState.EXECUTING
                await self.event_bridge.emit_job_state_changed(
                    job=self.job,
                    previous_state=prev_state,
                    reason=reason,
                )
            self._job_cancel_persisted = True

        # Milestone 2: Persist task.cancelled events for unfinished tasks
        for task in self.graph.list_tasks():
            if task.status in (TaskStatus.RUNNING, TaskStatus.READY, TaskStatus.PENDING, TaskStatus.CANCELLED):
                self.graph.mark_cancelled(task.task_id, reason=reason)
                await self.event_bridge.emit_task_cancelled(
                    task_id=task.task_id,
                    job_id=self.job.job_id,
                    reason=reason,
                    attempt=task.attempt,
                    assigned_actor=task.assigned_actor,
                )

        # Milestone 3: Drain active tasks and ensure no durability failures occurred during worker cancel
        await self._cancel_active_tasks(reason)

        # Milestone 4: Reconcile cancelled agent runs durably
        if hasattr(self, "execution_manager") and self.execution_manager:
            for run in self.execution_manager.list_runs_for_job(self.job.job_id):
                if run.status == AgentRunStatus.CANCELLED:
                    task = self.graph.get_task(run.task_id)
                    if task:
                        await self.event_bridge.emit_agent_cancelled(run=run, task=task, reason=reason)

        self._durable_cancel_completed = True
        return True

    async def fence(self, reason: str = "Execution lease lost") -> bool:
        """
        Immediately fences the engine from further progression due to lost execution exclusivity.
        Cancels active task workers, halts orchestration, and transitions state to BLOCKED.
        """
        self._fenced = True
        logger.warning("Fencing ReactiveJobEngine for job %s: %s", self.job.job_id, reason)
        await self._cancel_active_tasks(reason)
        if not self.is_terminal:
            try:
                await self._transition_job(JobState.BLOCKED, reason=reason)
            except Exception as exc:
                logger.debug("Failed to transition fenced job %s to BLOCKED: %s", self.job.job_id, exc)
        return True

    async def step(self) -> bool:
        """
        Executes a single reactive progression cycle.
        Returns True if the engine should continue cycling, False if job reached terminal state.
        """
        if self.is_terminal or getattr(self, "_fenced", False):
            return False

        # 1. State: CREATED -> trigger initialize_and_plan
        if self.job.state == JobState.CREATED:
            await self.initialize_and_plan()
            return not self.is_terminal

        # State: WAITING_FOR_CAPACITY
        if self.job.state == JobState.WAITING_FOR_CAPACITY:
            ready = self.graph.find_ready_tasks()
            can_run = False
            for rt in ready:
                dec = self.scheduler.match_actor_for_task(rt)
                if dec.dispatched and dec.actor_id:
                    can_run = True
                    break
            if can_run:
                logger.info("Provider capacity restored for job %s; transitioning back to EXECUTING", self.job.job_id)
                await self._transition_job(JobState.EXECUTING, reason="Provider capacity restored")
                await self.event_bridge.emit_job_capacity_restored(self.job, reason="Provider capacity restored")
                return True
            # Briefly yield
            await asyncio.sleep(0.01)
            return True

        # 2. State: EXECUTING
        if self.job.state == JobState.EXECUTING:
            # Check if all tasks in graph are already succeeded
            if self.graph.is_all_completed():
                await self._transition_job(JobState.VERIFYING, reason="All tasks succeeded; entering verification")
                return True

            # Schedule and launch any newly ready tasks
            new_async_tasks = await self.scheduler.schedule_ready_tasks(
                graph=self.graph,
                execution_manager=self.execution_manager,
                context={"job": self.job.to_dict()},
            )
            for t in new_async_tasks:
                self._active_async_tasks.add(t)

            # Check if tasks are deferred due to capacity/throttling and no worker is active
            if not self._active_async_tasks and not new_async_tasks:
                ready = self.graph.find_ready_tasks()
                if ready:
                    capacity_reasons = []
                    for rt in ready:
                        dec = self.scheduler.match_actor_for_task(rt)
                        if dec.reason != "no_capable_actor":
                            capacity_reasons.append(dec.reason)
                    if capacity_reasons:
                        logger.info("Tasks deferred due to provider capacity (%s); entering WAITING_FOR_CAPACITY", capacity_reasons[0])
                        await self._transition_job(
                            JobState.WAITING_FOR_CAPACITY,
                            reason=f"Waiting for provider capacity: {capacity_reasons[0]}",
                        )
                        await self.event_bridge.emit_job_waiting_for_capacity(
                            self.job,
                            reason=f"Waiting for provider capacity: {capacity_reasons[0]}",
                        )
                        return True

            if self._active_async_tasks:
                done, pending = await asyncio.wait(
                    self._active_async_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                self._active_async_tasks = pending

                follow_up_observations: List[Observation] = []
                explicit_replan_details: List[str] = []

                for completed_task in done:
                    try:
                        if completed_task.cancelled():
                            continue
                        res = completed_task.result()
                        if isinstance(res, tuple) and len(res) == 2:
                            task_node, exec_res = res
                            # Ingest observations
                            for obs in exec_res.observations:
                                if isinstance(obs, Observation):
                                    self.observation_registry.register(obs)
                                    await self.event_bridge.emit_observation_created(obs)
                                    registered = obs
                                elif isinstance(obs, dict):
                                    registered = self.observation_registry.add_observation(
                                        job_id=self.job.job_id,
                                        kind=obs.get("kind", "discovery"),
                                        content=obs.get("content", ""),
                                        task_id=task_node.task_id,
                                        actor_id=task_node.assigned_actor,
                                        metadata=obs.get("metadata", {}),
                                    )
                                    await self.event_bridge.emit_observation_created(registered)
                                else:
                                    continue

                                if (registered.metadata or {}).get("requires_follow_up"):
                                    follow_up_observations.append(registered)

                            # Check if execution result explicitly requests replan
                            if exec_res.metadata.get("trigger_replan"):
                                explicit_replan_details.append(
                                    exec_res.metadata.get("replan_reason", "Observation triggered dynamic plan expansion")
                                )
                    except asyncio.CancelledError:
                        continue
                    except Exception as exc:
                        logger.error("Error processing completed task: %s", exc)
                        raise

                new_follow_ups = [o for o in follow_up_observations if o.id not in self._discovery_triggered]
                if new_follow_ups or explicit_replan_details:
                    for obs in new_follow_ups:
                        self._discovery_triggered.add(obs.id)
                    detail = "; ".join(explicit_replan_details) or (
                        f"{len(new_follow_ups)} observation(s) requested follow-up work"
                    )
                    await self.request_replan(
                        reason=ReplanReason.OBSERVATION_DISCOVERY,
                        detail=detail,
                        block_on_no_progress=False,
                    )
                    if self.is_terminal:
                        await self._cancel_active_tasks("Job reached a terminal state during replanning")
                        return False

            if self.is_terminal:
                await self._cancel_active_tasks("Job reached a terminal state during execution")
                return False

            # Check after execution batch
            if self.graph.is_all_completed():
                await self._transition_job(JobState.VERIFYING, reason="All tasks succeeded; entering verification")
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
                    await self._transition_job(
                        JobState.BLOCKED,
                        reason=f"Task failure exhausted retries and replan failed: {failed_desc}",
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
                    await self._transition_job(
                        JobState.BLOCKED,
                        reason="Task graph blocked: no tasks are ready and all paths are exhausted",
                    )
                return not self.is_terminal

            return not self.is_terminal

        # 3. State: VERIFYING
        if self.job.state == JobState.VERIFYING:
            verifier_id = getattr(self.verifier, "verifier_id", "verifier")
            await self.event_bridge.emit_verification_started(self.job.job_id, verifier_id)

            artifacts = self.get_artifacts()
            ver_res = await self.verifier.verify(
                job=self.job,
                graph=self.graph,
                artifacts=artifacts,
                context={"job": self.job.to_dict()},
            )
            self._last_verification_result = ver_res

            if ver_res.is_passed:
                await self.event_bridge.emit_verification_passed(self.job.job_id, ver_res)
                await self._transition_job(
                    JobState.COMPLETED,
                    reason=f"Verification passed: {ver_res.summary}",
                )
                return False

            elif ver_res.is_repairable:
                await self.event_bridge.emit_verification_failed(self.job.job_id, ver_res)

                if self.job.repair_count >= self.limits.max_repairs_per_job:
                    await self._transition_job(
                        JobState.BLOCKED,
                        reason=f"Verification failed after {self.limits.max_repairs_per_job} repair cycles: {ver_res.summary}",
                    )
                    return False

                await self._transition_job(
                    JobState.REPAIRING,
                    reason=f"Verification failed (repairable cycle {self.job.repair_count + 1}): {ver_res.summary}",
                )

                # Add repair recommendations to graph
                added_any = False
                if ver_res.repair_recommendations:
                    for rec in ver_res.repair_recommendations:
                        try:
                            node = self.graph.add_task(rec)
                            node.max_attempts = min(node.max_attempts, self.limits.max_task_attempts)
                            await self.event_bridge.emit_task_created(node, reason="repair_recommendation")
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
                        await self.event_bridge.emit_task_created(r_task, reason="default_repair")
                    except ValueError:
                        pass

                if self.is_terminal:
                    return False

                await self._transition_job(
                    JobState.EXECUTING,
                    reason="Repair tasks scheduled; resuming execution",
                )
                return True

            else:
                # Hard failure
                await self.event_bridge.emit_verification_failed(self.job.job_id, ver_res)
                await self._transition_job(
                    JobState.FAILED,
                    reason=f"Verification failed irreversibly: {ver_res.summary}",
                )
                return False

        return False

    async def run_until_complete(self, max_steps: int = 100) -> JobRecord:
        """
        Drives the engine in a loop until a terminal state is reached or max_steps is exceeded.
        Fails closed on storage/persistence failures: halts orchestration and cancels workers.
        """
        step_count = 0
        try:
            while not self.is_terminal and step_count < max_steps:
                was_waiting_capacity = (self.job.state == JobState.WAITING_FOR_CAPACITY)
                should_continue = await self.step()
                if not was_waiting_capacity:
                    step_count += 1
                if not should_continue:
                    break

            if not self.is_terminal:
                await self._transition_job(
                    JobState.BLOCKED,
                    reason=f"Execution exceeded maximum step limit ({max_steps})",
                )
        except asyncio.CancelledError:
            await self._cancel_active_tasks("Engine run cancelled")
            if not self.is_terminal:
                try:
                    await self._transition_job(
                        JobState.CANCELLED,
                        reason="Engine run cancelled",
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            # Storage or execution error: halt immediately, cancel workers, do not acknowledge success
            logger.error("Engine execution halted due to failure: %s", exc)
            await self._cancel_active_tasks(f"Execution halted: {exc}")
            raise
        finally:
            await self._cancel_active_tasks("Engine run finished")
            await self.event_bridge.flush()

        return self.job

    @classmethod
    async def resume(
        cls,
        job_id: str,
        event_store: Any,
        lease_store: Optional[Any] = None,
        owner_id: Optional[str] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        limits: Optional[RuntimeLimits] = None,
        event_bridge: Optional[RuntimeEventBridge] = None,
        detected_interruption_at: Optional[str] = None,
    ) -> Tuple["ReactiveJobEngine", Any]:
        """
        Durable crash recovery and engine rehydration from canonical event ledger.
        """
        from runtime.recovery import RecoveryManager
        manager = RecoveryManager(
            event_store=event_store,
            lease_store=lease_store,
            capability_registry=capability_registry,
            limits=limits,
        )
        return await manager.recover_and_rehydrate(
            job_id=job_id,
            owner_id=owner_id,
            detected_interruption_at=detected_interruption_at,
            event_bridge=event_bridge,
        )
