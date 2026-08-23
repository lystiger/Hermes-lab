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
                    node = graph.add_task(mutation.task)
                    affected_task_ids.append(node.task_id)
                    if event_bridge:
                        event_bridge.emit_task_created(node, reason=mutation.reason)

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
                    graph.remove_task(mutation.task_id)
                    affected_task_ids.append(mutation.task_id)

        return affected_task_ids
