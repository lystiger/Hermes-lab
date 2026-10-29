from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.observations import Observation
from runtime.limits import RuntimeLimits

logger = logging.getLogger("hermes.runtime.replanning")


class GraphMutationType(str, Enum):
    """Type of mutation to apply to the running task graph."""
    ADD_TASK = "ADD_TASK"
    ADD_DEPENDENCY = "ADD_DEPENDENCY"
    SUPERSEDE_TASK = "SUPERSEDE_TASK"
    REMOVE_TASK = "REMOVE_TASK"


@dataclass
class GraphMutation:
    """A discrete incremental change to the task graph."""
    mutation_type: GraphMutationType
    task: Optional[TaskNode] = None
    task_id: Optional[str] = None
    depends_on_task_id: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.mutation_type, str):
            self.mutation_type = GraphMutationType(self.mutation_type.upper())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mutation_type": self.mutation_type.value,
            "task": self.task.to_dict() if self.task else None,
            "task_id": self.task_id or (self.task.task_id if self.task else None),
            "depends_on_task_id": self.depends_on_task_id,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphMutation":
        m_type = data.get("mutation_type") or data.get("mutationType", "ADD_TASK")
        task_data = data.get("task")
        task_node = TaskNode.from_dict(task_data) if task_data else None
        return cls(
            mutation_type=GraphMutationType(m_type.upper()) if isinstance(m_type, str) else m_type,
            task=task_node,
            task_id=data.get("task_id") or data.get("taskId"),
            depends_on_task_id=data.get("depends_on_task_id") or data.get("dependsOnTaskId"),
            reason=data.get("reason"),
        )


class ReplanReason(str, Enum):
    """Trigger reasons for invoking the planner or replanner."""
    INITIAL_PLAN = "initial_plan"
    OBSERVATION_DISCOVERY = "observation_discovery"
    TASK_FAILURE = "task_failure"
    VERIFICATION_REPAIR = "verification_repair"
    RUNTIME_BLOCKED = "runtime_blocked"


@dataclass
class ReplanRequest:
    """Context and facts provided to the planner/replanner."""
    job_id: str
    goal: str
    reason: Union[ReplanReason, str]
    completed_tasks: List[TaskNode]
    failed_tasks: List[TaskNode]
    current_graph: TaskGraph
    new_observations: List[Observation]
    produced_artifacts: List[Dict[str, Any]]
    replan_budget_remaining: int
    detail: Optional[str] = None
    target_repo: Optional[Any] = None
    constraints: List[str] = field(default_factory=list)
    available_capabilities: Optional[List[str]] = None
    # Capabilities per agent: each task runs on one agent, so its capabilities must all belong to one of them.
    agent_capabilities: Optional[Dict[str, List[str]]] = None
    evidence: Optional[Any] = None


@dataclass
class ReplanResult:
    """The result of planning or replanning containing incremental mutations."""
    mutations: List[GraphMutation] = field(default_factory=list)
    explanation: str = "Plan updated"
    should_continue: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mutations": [m.to_dict() for m in self.mutations],
            "explanation": self.explanation,
            "should_continue": self.should_continue,
        }


class PlannerAdapter:
    """Base interface for planning / replanning strategies."""

    async def plan(self, request: ReplanRequest) -> ReplanResult:
        raise NotImplementedError


class CallablePlannerAdapter(PlannerAdapter):
    """Adapter wrapping a callable function."""

    def __init__(self, func: Callable):
        self.func = func

    async def plan(self, request: ReplanRequest) -> ReplanResult:
        import inspect
        if inspect.iscoroutinefunction(self.func):
            res = await self.func(request)
        else:
            res = self.func(request)

        if isinstance(res, ReplanResult):
            return res
        if isinstance(res, dict):
            mutations = [GraphMutation.from_dict(m) for m in res.get("mutations", [])]
            return ReplanResult(
                mutations=mutations,
                explanation=res.get("explanation", "Plan modified"),
                should_continue=res.get("should_continue", True),
            )
        if isinstance(res, list):
            # List of tasks or mutations
            mutations = []
            for item in res:
                if isinstance(item, GraphMutation):
                    mutations.append(item)
                elif isinstance(item, TaskNode):
                    mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=item))
                elif isinstance(item, dict):
                    if "mutation_type" in item or "mutationType" in item:
                        mutations.append(GraphMutation.from_dict(item))
                    else:
                        mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=TaskNode.from_dict(item)))
            return ReplanResult(mutations=mutations, explanation="Incremental mutations planned")
        return ReplanResult(mutations=[], explanation=str(res))


# Per-attempt task metadata new work must not reuse: it gets its own worktree, branch and history.
_PER_ATTEMPT_METADATA = ("worktree_dir", "branch", "observations", "prior_runs", "fallback_for", "repair_for")


def _error_text(error: Any) -> str:
    if isinstance(error, dict):
        return str(error.get("message") or error.get("error") or error)[:500]
    return str(error or "unknown failure")[:500]


def _inherited_metadata(task: TaskNode, drop: tuple = ()) -> Dict[str, Any]:
    """Execution settings (backend, role, prompt, limits, options) new work inherits from `task`."""
    return {
        key: value
        for key, value in (task.metadata or {}).items()
        if key not in _PER_ATTEMPT_METADATA and key not in drop
    }


def _fallback_metadata(failed_task: TaskNode) -> Dict[str, Any]:
    """A fallback is the same work on the same agent and execution path, plus every earlier failure."""
    inherited = _inherited_metadata(failed_task)
    inherited["fallback_for"] = failed_task.task_id
    # Chained fallbacks keep the whole history, so the prompt can explain every earlier failure.
    inherited["fallback_errors"] = list((failed_task.metadata or {}).get("fallback_errors") or []) + [
        {"task_id": failed_task.task_id, "error": _error_text(failed_task.error)}
    ]
    # An agent that changed nothing would likely change nothing again; the scheduler skips it when it can.
    if failed_task.assigned_actor and _error_text(failed_task.error).startswith("FAILED_NO_CHANGES"):
        inherited["avoid_actors"] = sorted(set(inherited.get("avoid_actors") or []) | {failed_task.assigned_actor})
    return inherited


class ProductionPlannerAdapter(PlannerAdapter):
    """
    Authoritative production planning and replanning adapter.
    Translates goals, sprint specifications, verification outcomes, and failure observations
    into concrete TaskNode DAGs and incremental GraphMutation operations.
    """

    # Observation kinds that may justify expanding the graph with follow-up work.
    EXPANDABLE_OBSERVATION_KINDS = ("discovery", "requirement", "gap", "missing_work")
    # Hard ceiling on tasks added by a single observation-driven expansion.
    MAX_DISCOVERY_TASKS_PER_REPLAN = 3

    def __init__(self, limits: Optional[RuntimeLimits] = None):
        self.limits = limits or RuntimeLimits()

    def decompose_goal(
        self,
        goal: str,
        job_id: str,
        spec: Optional[Dict[str, Any]] = None,
    ) -> List[TaskNode]:
        """
        Decomposes a high-level goal or sprint specification into a structured TaskNode DAG.
        """
        if spec and "phases" in spec and isinstance(spec["phases"], list):
            tasks = []
            phases = spec["phases"]
            for idx, p in enumerate(phases, start=1):
                phase_id = p.get("name") or f"phase_{idx}"
                agent_id = p.get("agent")
                req_caps = p.get("required_capabilities") or []
                t = TaskNode(
                    task_id=phase_id,
                    job_id=job_id,
                    description=p.get("prompt_file") or p.get("name") or f"Execute sprint phase {idx}",
                    assigned_actor=agent_id,
                    required_capabilities=req_caps,
                    metadata={"phase": p, "order": idx, "timeout_seconds": p.get("timeout_seconds")},
                )
                if p.get("dependencies"):
                    t.dependencies = list(p["dependencies"])
                elif idx > 1:
                    t.dependencies = [phases[idx - 2].get("name") or f"phase_{idx - 1}"]
                tasks.append(t)
            return tasks

        import time
        scaffold = TaskNode(
            task_id="task_scaffold",
            job_id=job_id,
            description=f"Scaffold project structure and dependencies for: {goal}",
            required_capabilities=["implementation", "code.python"],
            max_attempts=min(2, self.limits.max_task_attempts),
        )
        implement = TaskNode(
            task_id="task_implementation",
            job_id=job_id,
            description=f"Implement core logic and modules for: {goal}",
            dependencies=["task_scaffold"],
            required_capabilities=["implementation", "code.python"],
            max_attempts=min(2, self.limits.max_task_attempts),
        )
        verify = TaskNode(
            task_id="task_verification",
            job_id=job_id,
            description=f"Run unit tests and verification checks for: {goal}",
            dependencies=["task_implementation"],
            required_capabilities=["verification", "testing.unit"],
            max_attempts=min(2, self.limits.max_task_attempts),
        )
        return [scaffold, implement, verify]

    async def plan(self, request: ReplanRequest) -> ReplanResult:
        """
        Analyzes replan context (failed tasks, verification checks, new observations)
        and outputs structured GraphMutation operations.
        """
        import time
        mutations = []
        reason_str = str(request.reason.value if hasattr(request.reason, "value") else request.reason).lower()

        # 0. Observation-driven discovery: one bounded graph expansion.
        if "observation" in reason_str or "discovery" in reason_str:
            return self._plan_observation_discovery(request)

        # 1. Verification Failure / Repair
        if "verification" in reason_str or "repair" in reason_str:
            failed_obs = [o for o in request.new_observations if o.kind in ("verification_failure", "failure_analysis", "test_failure")]
            explanation_parts = []
            
            if failed_obs:
                for idx, obs in enumerate(failed_obs, start=1):
                    repair_task_id = f"repair_check_{int(time.time())}_{idx}"
                    source_task = (
                        request.current_graph.get_task(obs.task_id)
                        if getattr(obs, "task_id", None) and request.current_graph is not None
                        else None
                    )
                    repair_meta: Dict[str, Any] = {}
                    if source_task is not None:
                        # Same agent and execution path as the task the failure belongs to. The repair has its
                        # own instructions (so no inherited prompt file) and must be allowed to change files.
                        repair_meta = _inherited_metadata(source_task, drop=("prompt_file", "expected_handoff"))
                        repair_meta["role"] = "builder"
                        repair_meta["repair_for"] = source_task.task_id
                    repair_meta.update({"observation_ref": obs.id, "error_details": obs.metadata})
                    repair_node = TaskNode(
                        task_id=repair_task_id,
                        job_id=request.job_id,
                        description=f"Fix verification failure: {obs.content[:200]}",
                        # A repair routed to the source task's actor must ask for what that actor has,
                        # or the scheduler re-routes it away from the inherited agent and backend.
                        required_capabilities=(
                            list(source_task.required_capabilities)
                            if source_task is not None and source_task.required_capabilities
                            else ([] if source_task is not None and source_task.assigned_actor
                                  else ["implementation", "testing.unit"])
                        ),
                        assigned_actor=source_task.assigned_actor if source_task is not None else None,
                        parent_task_id=source_task.task_id if source_task is not None else None,
                        metadata=repair_meta,
                        max_attempts=min(2, self.limits.max_task_attempts),
                    )
                    mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=repair_node, reason="Repair verification failure"))
                    explanation_parts.append(f"Added repair task '{repair_task_id}' for {obs.content[:80]}")
            else:
                repair_task_id = f"repair_general_{int(time.time())}"
                repair_node = TaskNode(
                    task_id=repair_task_id,
                    job_id=request.job_id,
                    description=f"Resolve verification issue: {request.detail or 'Fix failing checks'}",
                    required_capabilities=["implementation", "testing.unit"],
                    max_attempts=min(2, self.limits.max_task_attempts),
                )
                mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=repair_node, reason="Repair verification failure"))
                explanation_parts.append(f"Added general repair task '{repair_task_id}'")

            return ReplanResult(
                mutations=mutations,
                explanation="; ".join(explanation_parts) if explanation_parts else "Planned verification repair tasks",
                should_continue=True,
            )

        # 2. Task Failure
        if "task" in reason_str or "failure" in reason_str:
            explanation_parts = []
            for failed_task in request.failed_tasks:
                if failed_task.attempt < failed_task.max_attempts:
                    continue  # Scheduler will retry
                # Exhausted attempts -> generate diagnostic/workaround task
                fix_task_id = f"fix_{failed_task.task_id}_{int(time.time())}"
                fix_node = TaskNode(
                    task_id=fix_task_id,
                    job_id=request.job_id,
                    # The original instructions, not a "diagnostic": success must mean the work was done.
                    # The failure reaches the prompt through metadata["fallback_errors"].
                    description=failed_task.description,
                    # Same requirements as the task it replaces. Inventing "implementation" for a task that
                    # declared none would make the scheduler re-route it away from the inherited actor.
                    required_capabilities=(
                        list(failed_task.required_capabilities)
                        if failed_task.required_capabilities
                        else ([] if failed_task.assigned_actor else ["implementation"])
                    ),
                    dependencies=failed_task.dependencies,
                    # The fallback is the same work on the same agent and execution path: without these
                    # it would be routed by capability alone, on the default backend, with no role guard.
                    assigned_actor=failed_task.assigned_actor,
                    parent_task_id=failed_task.task_id,
                    metadata=_fallback_metadata(failed_task),
                    max_attempts=min(2, self.limits.max_task_attempts),
                )
                mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=fix_node, reason=f"Fallback for {failed_task.task_id}"))
                mutations.append(GraphMutation(mutation_type=GraphMutationType.SUPERSEDE_TASK, task_id=failed_task.task_id, depends_on_task_id=fix_task_id, reason="Superseded by fallback task"))
                explanation_parts.append(f"Superseded failed task '{failed_task.task_id}' with '{fix_task_id}'")

            return ReplanResult(
                mutations=mutations,
                explanation="; ".join(explanation_parts) if explanation_parts else "Handled task failure",
                should_continue=bool(mutations),
            )

        # 3. Blocked / Deadlock
        if "blocked" in reason_str or "deadlock" in reason_str:
            blocked_tasks = request.current_graph.find_dependency_blocked_tasks()
            if blocked_tasks:
                # These tasks wait on prerequisites that failed, were blocked or were cancelled. Adding
                # another dependency can never satisfy those, so an "unblock" task would succeed and leave
                # the graph stalled. Report that automatic recovery cannot proceed; the job blocks.
                blockers = sorted({
                    dep for bt in blocked_tasks for dep in bt.dependencies
                    if (request.current_graph.get_task(dep) is None
                        or request.current_graph.get_task(dep).status in (TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED))
                })
                return ReplanResult(
                    mutations=[],
                    explanation=(
                        f"Automatic recovery cannot proceed: {len(blocked_tasks)} task(s) "
                        f"({', '.join(t.task_id for t in blocked_tasks)}) depend on unsatisfiable prerequisites "
                        f"({', '.join(blockers) or 'unknown'})"
                    ),
                    should_continue=False,
                )

        return ReplanResult(mutations=[], explanation=f"No automatic mutations required for {reason_str}", should_continue=False)

    def _plan_observation_discovery(self, request: ReplanRequest) -> ReplanResult:
        """
        Expands the graph once from observations that explicitly request follow-up work.

        Bounded on four axes so discovery can never drive an unbounded planning loop:
        - the replan budget must not be exhausted;
        - only observations carrying an explicit `requires_follow_up` signal qualify, so the
          routine `discovery` observations every task emits do not generate tasks;
        - at most MAX_DISCOVERY_TASKS_PER_REPLAN tasks are added per expansion;
        - task ids are derived from the observation id, so re-expanding the same observation
          produces a duplicate the graph rejects instead of a second task.
        """
        if request.replan_budget_remaining <= 0:
            return ReplanResult(
                mutations=[],
                explanation="Observation discovery skipped: replan budget exhausted",
                should_continue=False,
            )

        candidates = []
        for obs in request.new_observations:
            if str(obs.kind).lower() not in self.EXPANDABLE_OBSERVATION_KINDS:
                continue
            meta = obs.metadata or {}
            if not meta.get("requires_follow_up"):
                continue
            candidates.append(obs)

        if not candidates:
            return ReplanResult(
                mutations=[],
                explanation="No observations requested follow-up work; graph unchanged",
                should_continue=False,
            )

        mutations: List[GraphMutation] = []
        explanation_parts: List[str] = []
        for obs in candidates[: self.MAX_DISCOVERY_TASKS_PER_REPLAN]:
            meta = obs.metadata or {}
            task_id = f"discover_{obs.id}"
            if request.current_graph.get_task(task_id) is not None:
                continue

            description = str(meta.get("follow_up_task") or obs.content or "Investigate discovered work")
            required_caps = meta.get("required_capabilities") or ["implementation"]
            if isinstance(required_caps, str):
                required_caps = [required_caps]

            node = TaskNode(
                task_id=task_id,
                job_id=request.job_id,
                description=description[:500],
                required_capabilities=list(required_caps),
                metadata={
                    "observation_ref": obs.id,
                    "origin": "observation_discovery",
                    "source_task_id": obs.task_id,
                },
                max_attempts=min(2, self.limits.max_task_attempts),
            )

            # Discovered work depends on the task that surfaced it when that task is still
            # in the graph, so the expansion cannot run ahead of the work that produced it.
            if obs.task_id and request.current_graph.get_task(obs.task_id) is not None:
                node.dependencies = [obs.task_id]

            mutations.append(
                GraphMutation(
                    mutation_type=GraphMutationType.ADD_TASK,
                    task=node,
                    reason=f"Observation {obs.id} requested follow-up work",
                )
            )
            explanation_parts.append(f"Added discovery task '{task_id}' from observation {obs.id}")

        if not mutations:
            return ReplanResult(
                mutations=[],
                explanation="All requested follow-up work is already present in the graph",
                should_continue=False,
            )

        skipped = max(0, len(candidates) - self.MAX_DISCOVERY_TASKS_PER_REPLAN)
        if skipped:
            explanation_parts.append(f"{skipped} further observation(s) deferred by expansion bound")

        return ReplanResult(
            mutations=mutations,
            explanation="; ".join(explanation_parts),
            should_continue=True,
        )


# Alias for production planner adapter
HermesPlannerAdapter = ProductionPlannerAdapter


class BoundedReplanner:
    """
    Applies graph mutations safely with limit enforcement to avoid infinite or unbounded replanning loops.
    """

    def __init__(self, limits: Optional[RuntimeLimits] = None):
        self.limits = limits or RuntimeLimits()

    def apply_mutations(
        self,
        graph: TaskGraph,
        result: ReplanResult,
        job_id: str,
        event_bridge: Any = None,
    ) -> List[str]:
        """
        Applies graph mutations to the given TaskGraph.
        Returns list of newly added or modified task IDs.
        """
        affected_task_ids = []

        for mutation in result.mutations:
            if mutation.mutation_type == GraphMutationType.ADD_TASK:
                if graph.count() >= self.limits.max_tasks_per_job:
                    logger.warning("Max tasks limit (%d) reached for job %s; skipping task addition", self.limits.max_tasks_per_job, job_id)
                    continue

                if mutation.task:
                    # Enforce runtime limits on task attempts
                    mutation.task.max_attempts = min(mutation.task.max_attempts, self.limits.max_task_attempts)
                    try:
                        node = graph.add_task(mutation.task)
                        affected_task_ids.append(node.task_id)
                        if event_bridge and hasattr(event_bridge, "emit_task_created"):
                            res = event_bridge.emit_task_created(node, reason=mutation.reason)
                            if asyncio.iscoroutine(res):
                                try:
                                    loop = asyncio.get_running_loop()
                                    if loop.is_running():
                                        loop.create_task(res)
                                except RuntimeError:
                                    pass
                    except ValueError as e:
                        logger.warning("Rejected duplicate task in replanner: %s", e)

            elif mutation.mutation_type == GraphMutationType.ADD_DEPENDENCY:
                if mutation.task_id and mutation.depends_on_task_id:
                    try:
                        graph.add_dependency(mutation.task_id, mutation.depends_on_task_id)
                        affected_task_ids.append(mutation.task_id)
                    except Exception as e:
                        logger.warning("Failed adding dependency %s -> %s: %s", mutation.task_id, mutation.depends_on_task_id, e)

            elif mutation.mutation_type == GraphMutationType.SUPERSEDE_TASK:
                if mutation.task_id:
                    try:
                        graph.supersede_task(
                            task_id=mutation.task_id,
                            superseded_by=mutation.depends_on_task_id,
                            reason=mutation.reason,
                        )
                        affected_task_ids.append(mutation.task_id)
                        if event_bridge and hasattr(event_bridge, "emit_task_superseded"):
                            res = event_bridge.emit_task_superseded(
                                task_id=mutation.task_id,
                                job_id=job_id,
                                superseded_by=mutation.depends_on_task_id,
                                reason=mutation.reason,
                            )
                            if asyncio.iscoroutine(res):
                                try:
                                    loop = asyncio.get_running_loop()
                                    if loop.is_running():
                                        loop.create_task(res)
                                except RuntimeError:
                                    pass
                    except Exception as e:
                        logger.warning("Failed superseding task %s: %s", mutation.task_id, e)

            elif mutation.mutation_type == GraphMutationType.REMOVE_TASK:
                if mutation.task_id:
                    try:
                        graph.remove_task(mutation.task_id)
                        affected_task_ids.append(mutation.task_id)
                    except Exception as e:
                        logger.warning("Failed removing task %s: %s. Prefer SUPERSEDE_TASK.", mutation.task_id, e)

        return affected_task_ids
