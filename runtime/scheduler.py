import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.execution import ExecutionManager, TaskExecutionResult
from runtime.limits import RuntimeLimits
from runtime.events import RuntimeEventBridge
from capabilities.capabilities import CapabilityRegistry, default_capability_registry

logger = logging.getLogger("hermes.runtime.scheduler")


@dataclass
class DispatchDecision:
    """Explainable result of scheduler task dispatching."""
    task_id: str
    actor_id: Optional[str]
    dispatched: bool
    reason: str
    required_capabilities: List[str] = field(default_factory=list)
    matched_capabilities: List[str] = field(default_factory=list)
    rejected_candidates: Dict[str, str] = field(default_factory=dict)
    score: float = 0.0


class ReactiveScheduler:
    """
    Event-driven, capability-aware task scheduler.
    Determines newly ready tasks, maps capabilities to registered actors,
    and dispatches eligible tasks concurrently up to configured concurrency limits.
    """

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        limits: Optional[RuntimeLimits] = None,
        event_bridge: Optional[RuntimeEventBridge] = None,
    ):
        self.capability_registry = capability_registry or default_capability_registry
        self.limits = limits or RuntimeLimits()
        self.event_bridge = event_bridge
        self._running_tasks: Set[str] = set()
        self._busy_actors: Set[str] = set()

    @property
    def active_running_count(self) -> int:
        return len(self._running_tasks)

    def can_dispatch_more(self) -> bool:
        return len(self._running_tasks) < self.limits.concurrency_limit

    def match_actor_for_task(
        self,
        task: TaskNode,
        preferred_actors: Optional[List[str]] = None,
        excluded_actors: Optional[List[str]] = None,
    ) -> DispatchDecision:
        """
        Capability-aware actor selection with explainable decision tracking.
        """
        # If task already has an explicit valid assigned_actor specified and available
        if task.assigned_actor:
            satisfies = self.capability_registry.actor_satisfies(task.assigned_actor, task.required_capabilities)
            if satisfies:
                matched = [c for c in task.required_capabilities if c in self.capability_registry.get_actor_capabilities(task.assigned_actor)]
                return DispatchDecision(
                    task_id=task.task_id,
                    actor_id=task.assigned_actor,
                    dispatched=True,
                    reason=f"Explicitly assigned actor '{task.assigned_actor}' satisfies required capabilities",
                    required_capabilities=task.required_capabilities,
                    matched_capabilities=matched,
                    score=10.0,
                )

        # Query capability registry
        ranked_candidates = self.capability_registry.find_actors(
            required_capabilities=task.required_capabilities,
            preferred_actors=preferred_actors,
            excluded_actors=excluded_actors,
        )

        if not ranked_candidates:
            # Check why candidates failed for explainability
            rejected = {}
            for actor in self.capability_registry.list_actors():
                aid = getattr(actor, "id", str(actor))
                caps = set(self.capability_registry.get_actor_capabilities(aid))
                missing = [c for c in task.required_capabilities if c not in caps]
                if missing:
                    rejected[aid] = f"Missing capabilities: {', '.join(missing)}"

            return DispatchDecision(
                task_id=task.task_id,
                actor_id=None,
                dispatched=False,
                reason=f"No actor satisfies required capabilities: {', '.join(task.required_capabilities)}",
                required_capabilities=task.required_capabilities,
                matched_capabilities=[],
                rejected_candidates=rejected,
            )

        best_profile, best_score, match_info = ranked_candidates[0]
        selected_actor_id = getattr(best_profile, "id", str(best_profile))

        # Rejected candidates for explainability
        rejected = {}
        for profile, score, info in ranked_candidates[1:]:
            aid = getattr(profile, "id", str(profile))
            rejected[aid] = f"Lower match score ({score:.2f} < {best_score:.2f})"

        return DispatchDecision(
            task_id=task.task_id,
            actor_id=selected_actor_id,
            dispatched=True,
            reason=f"Selected actor '{selected_actor_id}' satisfying {len(task.required_capabilities)} capabilities (score: {best_score:.2f})",
            required_capabilities=task.required_capabilities,
            matched_capabilities=match_info.get("matchedCapabilities", []),
            rejected_candidates=rejected,
            score=best_score,
        )

    async def schedule_ready_tasks(
        self,
        graph: TaskGraph,
        execution_manager: ExecutionManager,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[asyncio.Task]:
        """
        Inspects graph for ready tasks, matches capabilities, and starts concurrent execution tasks.
        Returns list of newly launched asyncio Tasks.
        """
        ready_tasks = graph.find_ready_tasks()
        launched_async_tasks: List[asyncio.Task] = []

        for task in ready_tasks:
            if not self.can_dispatch_more():
                logger.debug("Concurrency limit (%d) reached; deferring task %s", self.limits.concurrency_limit, task.task_id)
                break

            if task.task_id in self._running_tasks:
                continue

            decision = self.match_actor_for_task(task)
            if not decision.dispatched or not decision.actor_id:
                logger.warning("Task %s cannot be dispatched: %s", task.task_id, decision.reason)
                graph.mark_blocked(task.task_id, reason=decision.reason)
                continue

            actor_id = decision.actor_id

            # Mark task running
            graph.mark_running(task.task_id, actor_id=actor_id)
            self._running_tasks.add(task.task_id)

            if self.event_bridge:
                self.event_bridge.emit_task_assigned(
                    task=task,
                    actor_id=actor_id,
                    decision={
                        "required_capabilities": decision.required_capabilities,
                        "matched_capabilities": decision.matched_capabilities,
                        "rejected_candidates": decision.rejected_candidates,
                        "reason": decision.reason,
                        "score": decision.score,
                    },
                )
                self.event_bridge.emit_task_started(task=task, actor_id=actor_id)

            # Spawn execution worker
            async_task = asyncio.create_task(
                self._execute_task_wrapper(
                    task=task,
                    actor_id=actor_id,
                    decision=decision,
                    graph=graph,
                    execution_manager=execution_manager,
                    context=context,
                ),
                name=f"exec-{task.task_id}-{actor_id}",
            )
            launched_async_tasks.append(async_task)

        return launched_async_tasks

    async def _execute_task_wrapper(
        self,
        task: TaskNode,
        actor_id: str,
        decision: DispatchDecision,
        graph: TaskGraph,
        execution_manager: ExecutionManager,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[TaskNode, TaskExecutionResult]:
        try:
            result = await execution_manager.execute(
                task=task,
                actor_id=actor_id,
                delegation_decision={
                    "required_capabilities": decision.required_capabilities,
                    "matched_capabilities": decision.matched_capabilities,
                    "rejected_candidates": decision.rejected_candidates,
                    "reason": decision.reason,
                    "score": decision.score,
                },
                context=context,
                event_bridge=self.event_bridge,
            )

            if result.status == "succeeded":
                graph.mark_success(task.task_id, artifacts=result.artifact_refs, metadata=result.metadata)
                if self.event_bridge:
                    self.event_bridge.emit_task_completed(task=task, actor_id=actor_id, artifacts=result.artifact_refs)
            else:
                graph.mark_failure(task.task_id, error=result.error, allow_retry=True)
                if self.event_bridge:
                    self.event_bridge.emit_task_failed(task=task, actor_id=actor_id, error=result.error)

            return task, result

        finally:
            self._running_tasks.discard(task.task_id)
