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


class ProductionPlannerAdapter(PlannerAdapter):
    """
    Authoritative production planning and replanning adapter.
    Translates goals, sprint specifications, verification outcomes, and failure observations
    into concrete TaskNode DAGs and incremental GraphMutation operations.
    """

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

        # 1. Verification Failure / Repair
        if "verification" in reason_str or "repair" in reason_str:
            failed_obs = [o for o in request.new_observations if o.kind in ("verification_failure", "failure_analysis", "test_failure")]
            explanation_parts = []
            
            if failed_obs:
                for idx, obs in enumerate(failed_obs, start=1):
                    repair_task_id = f"repair_check_{int(time.time())}_{idx}"
                    repair_node = TaskNode(
                        task_id=repair_task_id,
                        job_id=request.job_id,
                        description=f"Fix verification failure: {obs.content[:200]}",
                        required_capabilities=["implementation", "testing.unit"],
                        metadata={"observation_ref": obs.id, "error_details": obs.metadata},
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
                    description=f"Diagnostic & fallback for failed task '{failed_task.task_id}': {failed_task.error or failed_task.description}",
                    required_capabilities=failed_task.required_capabilities or ["implementation"],
                    dependencies=failed_task.dependencies,
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
                unblock_task_id = f"unblock_deadlock_{int(time.time())}"
                unblock_node = TaskNode(
                    task_id=unblock_task_id,
                    job_id=request.job_id,
                    description=f"Resolve dependency deadlock for blocked tasks: {', '.join([t.task_id for t in blocked_tasks])}",
                    required_capabilities=["implementation"],
                    max_attempts=min(2, self.limits.max_task_attempts),
                )
                mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_TASK, task=unblock_node, reason="Resolve graph deadlock"))
                for bt in blocked_tasks:
                    mutations.append(GraphMutation(mutation_type=GraphMutationType.ADD_DEPENDENCY, task_id=bt.task_id, depends_on_task_id=unblock_task_id))
                return ReplanResult(
                    mutations=mutations,
                    explanation=f"Planned unblock task '{unblock_task_id}' for {len(blocked_tasks)} deadlocked tasks",
                    should_continue=True,
                )

        return ReplanResult(mutations=[], explanation=f"No automatic mutations required for {reason_str}", should_continue=False)


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
                        if event_bridge:
                            event_bridge.emit_task_created(node, reason=mutation.reason)
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
                        if event_bridge:
                            event_bridge.emit_task_superseded(
                                task_id=mutation.task_id,
                                job_id=job_id,
                                superseded_by=mutation.depends_on_task_id,
                                reason=mutation.reason,
                            )
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
