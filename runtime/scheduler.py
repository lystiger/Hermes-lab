import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.execution import ExecutionManager, TaskExecutionResult
from runtime.limits import RuntimeLimits
from runtime.events import RuntimeEventBridge
from capabilities.capabilities import CapabilityRegistry, default_capability_registry
from runtime.capacity import (
    CapacityRegistry,
    default_capacity_registry,
    ProviderStatus,
    ProviderFailureClassifier,
    ProviderFailureClass,
    TaskBudgetEstimate,
)
from runtime.circuit_breaker import CircuitBreakerRegistry, default_circuit_registry
from runtime.routing import ReroutePolicy, default_reroute_policy

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
    checks provider capacity and circuit breakers, and dispatches eligible tasks.
    """

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        capacity_registry: Optional[CapacityRegistry] = None,
        circuit_registry: Optional[CircuitBreakerRegistry] = None,
        reroute_policy: Optional[ReroutePolicy] = None,
        limits: Optional[RuntimeLimits] = None,
        event_bridge: Optional[RuntimeEventBridge] = None,
        default_actor_concurrency: int = 1,
    ):
        self.capability_registry = capability_registry or default_capability_registry
        self.capacity_registry = capacity_registry or default_capacity_registry
        self.circuit_registry = circuit_registry or default_circuit_registry
        self.reroute_policy = reroute_policy or ReroutePolicy(
            capability_registry=self.capability_registry,
            capacity_registry=self.capacity_registry,
            circuit_registry=self.circuit_registry,
        )
        self.limits = limits or RuntimeLimits()
        self.event_bridge = event_bridge
        self.default_actor_concurrency = default_actor_concurrency
        self.actor_concurrency_limits: Dict[str, int] = {}
        self._running_tasks: Set[str] = set()
        self._busy_actors: Dict[str, int] = {}

    @property
    def active_running_count(self) -> int:
        return len(self._running_tasks)

    def set_actor_concurrency(self, actor_id: str, concurrency_limit: int) -> None:
        """Configures maximum concurrent tasks for a specific actor."""
        self.actor_concurrency_limits[actor_id] = max(1, concurrency_limit)

    def get_actor_concurrency_limit(self, actor_id: str) -> int:
        return self.actor_concurrency_limits.get(actor_id, self.default_actor_concurrency)

    def is_actor_available(self, actor_id: str) -> bool:
        current_load = self._busy_actors.get(actor_id, 0)
        if current_load >= self.get_actor_concurrency_limit(actor_id):
            return False
        if not self.circuit_registry.allow_request(actor_id):
            return False
        if not self.capacity_registry.is_actor_available(actor_id):
            return False
        return True

    def get_actor_rejection_reason(self, actor_id: str) -> str:
        current_load = self._busy_actors.get(actor_id, 0)
        if current_load >= self.get_actor_concurrency_limit(actor_id):
            return "Actor currently at max concurrency capacity"
        if not self.circuit_registry.allow_request(actor_id):
            return "Actor circuit breaker is OPEN"
        if not self.capacity_registry.is_actor_available(actor_id):
            provider_id = self.capacity_registry.get_provider_for_actor(actor_id)
            status = self.capacity_registry.get_provider_status(provider_id)
            return f"Provider '{provider_id}' is {status.value}"
        return "Unknown rejection"

    def acquire_actor(self, actor_id: str) -> None:
        self._busy_actors[actor_id] = self._busy_actors.get(actor_id, 0) + 1

    def release_actor(self, actor_id: str) -> None:
        if actor_id in self._busy_actors:
            self._busy_actors[actor_id] = max(0, self._busy_actors[actor_id] - 1)
            if self._busy_actors[actor_id] == 0:
                self._busy_actors.pop(actor_id, None)

    @staticmethod
    def _resolve_actor_id(profile: Any) -> str:
        if isinstance(profile, dict):
            return str(profile.get("id", ""))
        return str(getattr(profile, "id", profile))

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
        Distinguishes NO_CAPABLE_ACTOR from ACTOR_BUSY, CIRCUIT_OPEN, QUOTA_EXHAUSTED,
        and PROACTIVE_SOFT_CAPACITY_FAILOVER.
        """
        # Parse TaskBudgetEstimate if present in task metadata
        task_budget = None
        if isinstance(task.metadata, dict):
            if "budget_estimate" in task.metadata and isinstance(task.metadata["budget_estimate"], dict):
                be = task.metadata["budget_estimate"]
                task_budget = TaskBudgetEstimate(
                    expected_input_tokens=be.get("expected_input_tokens", 0),
                    expected_output_tokens=be.get("expected_output_tokens", 0),
                    expected_turns=be.get("expected_turns", 1),
                )
            elif "expected_input_tokens" in task.metadata or "expected_output_tokens" in task.metadata:
                task_budget = TaskBudgetEstimate(
                    expected_input_tokens=task.metadata.get("expected_input_tokens", 0),
                    expected_output_tokens=task.metadata.get("expected_output_tokens", 0),
                )

        # If task already has an explicit valid assigned_actor specified
        if task.assigned_actor:
            if not task.required_capabilities or self.capability_registry.actor_satisfies(task.assigned_actor, task.required_capabilities):
                if not self.is_actor_available(task.assigned_actor):
                    rejection = self.get_actor_rejection_reason(task.assigned_actor)
                    # Pre-dispatch capability reroute if unavailable due to circuit/quota/rate-limit/outage
                    if any(k in rejection.lower() for k in ("circuit", "quota", "throttled", "unavailable", "auth", "outage")):
                        alt_actor = self.reroute_policy.find_alternative_actor(task, failed_actor=task.assigned_actor)
                        if alt_actor:
                            orig_actor = task.assigned_actor
                            matched = [c for c in task.required_capabilities if c in self.capability_registry.get_actor_capabilities(alt_actor)]
                            return DispatchDecision(
                                task_id=task.task_id,
                                actor_id=alt_actor,
                                dispatched=True,
                                reason=f"Pre-dispatch rerouted from unavailable '{orig_actor}' ({rejection}) to capable alternative '{alt_actor}'",
                                required_capabilities=task.required_capabilities,
                                matched_capabilities=matched,
                                score=9.0,
                            )
                    return DispatchDecision(
                        task_id=task.task_id,
                        actor_id=None,
                        dispatched=False,
                        reason=rejection,
                        required_capabilities=task.required_capabilities,
                    )

                # Check soft-capacity thresholds BEFORE dispatch
                is_healthy, soft_reason = self.capacity_registry.check_soft_capacity(task.assigned_actor, task_budget=task_budget)
                if not is_healthy:
                    alt_actor = self.reroute_policy.find_alternative_actor(task, failed_actor=task.assigned_actor)
                    if alt_actor:
                        is_alt_healthy, _ = self.capacity_registry.check_soft_capacity(alt_actor, task_budget=task_budget)
                        if is_alt_healthy:
                            orig_actor = task.assigned_actor
                            matched = [c for c in task.required_capabilities if c in self.capability_registry.get_actor_capabilities(alt_actor)]
                            return DispatchDecision(
                                task_id=task.task_id,
                                actor_id=alt_actor,
                                dispatched=True,
                                reason=f"Proactive capacity reroute from '{orig_actor}' ({soft_reason}) to healthier capable alternative '{alt_actor}'",
                                required_capabilities=task.required_capabilities,
                                matched_capabilities=matched,
                                score=9.0,
                            )

                matched = [c for c in task.required_capabilities if c in self.capability_registry.get_actor_capabilities(task.assigned_actor)]
                return DispatchDecision(
                    task_id=task.task_id,
                    actor_id=task.assigned_actor,
                    dispatched=True,
                    reason=f"Explicitly assigned actor '{task.assigned_actor}' satisfies task requirements",
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
            rejected = {}
            for actor in self.capability_registry.list_actors():
                aid = self._resolve_actor_id(actor)
                caps = set(self.capability_registry.get_actor_capabilities(aid))
                missing = [c for c in task.required_capabilities if c not in caps]
                if missing:
                    rejected[aid] = f"Missing capabilities: {', '.join(missing)}"

            return DispatchDecision(
                task_id=task.task_id,
                actor_id=None,
                dispatched=False,
                reason="no_capable_actor",
                required_capabilities=task.required_capabilities,
                matched_capabilities=[],
                rejected_candidates=rejected,
            )

        # Filter for available candidates (hard availability)
        available_candidates = [
            c for c in ranked_candidates
            if self.is_actor_available(self._resolve_actor_id(c[0]))
        ]

        if not available_candidates:
            # Capable actors exist, but none currently available
            rejection_reasons = {
                self._resolve_actor_id(c[0]): self.get_actor_rejection_reason(self._resolve_actor_id(c[0]))
                for c in ranked_candidates
            }
            primary_reason = next(iter(rejection_reasons.values()), "actor_busy")
            return DispatchDecision(
                task_id=task.task_id,
                actor_id=None,
                dispatched=False,
                reason=primary_reason,
                required_capabilities=task.required_capabilities,
                matched_capabilities=ranked_candidates[0][2].get("matchedCapabilities", []),
                rejected_candidates=rejection_reasons,
            )

        # Apply soft-capacity filtering across candidates: healthy actors prioritized over degraded ones
        healthy_candidates = []
        soft_degraded_reasons = {}
        for c in available_candidates:
            aid = self._resolve_actor_id(c[0])
            is_healthy, soft_reason = self.capacity_registry.check_soft_capacity(aid, task_budget=task_budget)
            if is_healthy:
                healthy_candidates.append(c)
            else:
                soft_degraded_reasons[aid] = soft_reason or "low_soft_capacity"

        if healthy_candidates:
            best_profile, best_score, match_info = healthy_candidates[0]
        else:
            best_profile, best_score, match_info = available_candidates[0]

        selected_actor_id = self._resolve_actor_id(best_profile)

        # Rejected candidates for explainability
        rejected = {}
        for profile, score, info in ranked_candidates:
            aid = self._resolve_actor_id(profile)
            if aid == selected_actor_id:
                continue
            if not self.is_actor_available(aid):
                rejected[aid] = self.get_actor_rejection_reason(aid)
            elif aid in soft_degraded_reasons and healthy_candidates:
                rejected[aid] = f"Soft capacity degraded: {soft_degraded_reasons[aid]}"
            else:
                rejected[aid] = f"Lower match score ({score:.2f} < {best_score:.2f})"

        selection_reason = f"Selected actor '{selected_actor_id}' satisfying {len(task.required_capabilities)} capabilities (score: {best_score:.2f})"
        if soft_degraded_reasons and healthy_candidates:
            selection_reason = f"Selected healthy actor '{selected_actor_id}' over degraded candidates (score: {best_score:.2f})"

        return DispatchDecision(
            task_id=task.task_id,
            actor_id=selected_actor_id,
            dispatched=True,
            reason=selection_reason,
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
                if decision.reason != "no_capable_actor":
                    # Temporarily unavailable: task remains READY / deferred
                    logger.debug("Task %s deferred: %s", task.task_id, decision.reason)
                    continue
                else:
                    # No capable actor exists: mark blocked
                    logger.warning("Task %s cannot be dispatched: %s", task.task_id, decision.reason)
                    graph.mark_blocked(task.task_id, reason=decision.reason)
                    continue

            actor_id = decision.actor_id

            if decision.reason.startswith("Pre-dispatch rerouted") and task.assigned_actor != actor_id:
                orig_actor = task.assigned_actor
                task.assigned_actor = actor_id
                if self.event_bridge:
                    await self.event_bridge.emit_task_rerouted(
                        task_id=task.task_id,
                        job_id=task.job_id,
                        from_actor=orig_actor,
                        to_actor=actor_id,
                        reason=decision.reason,
                    )
                    await self.event_bridge.emit_task_ready(task)

            # Mark task running and acquire actor
            graph.mark_running(task.task_id, actor_id=actor_id)
            self._running_tasks.add(task.task_id)
            self.acquire_actor(actor_id)

            if self.event_bridge:
                await self.event_bridge.emit_task_assigned(
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
                await self.event_bridge.emit_task_started(task=task, actor_id=actor_id)

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
        provider_id = self.capacity_registry.get_provider_for_actor(actor_id)
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

            # Record telemetry usage if available in metadata
            if isinstance(result.metadata, dict):
                input_tok = int(result.metadata.get("input_tokens") or result.metadata.get("prompt_tokens") or 0)
                output_tok = int(result.metadata.get("output_tokens") or result.metadata.get("completion_tokens") or 0)
                cached_tok = int(result.metadata.get("cached_tokens") or 0)
                if input_tok or output_tok or cached_tok:
                    self.capacity_registry.record_usage(
                        provider_id=provider_id,
                        job_id=task.job_id,
                        actor_id=actor_id,
                        input_tokens=input_tok,
                        output_tokens=output_tok,
                        cached_tokens=cached_tok,
                    )

            if result.status == "succeeded":
                self.circuit_registry.record_success(actor_id)
                self.capacity_registry.record_provider_success(provider_id)
                if self.event_bridge:
                    await self.event_bridge.emit_task_completed(task=task, actor_id=actor_id, artifacts=result.artifact_refs)
                graph.mark_success(task.task_id, artifacts=result.artifact_refs, metadata=result.metadata)
            else:
                # Classify failure
                status_code = getattr(result, "status_code", None) or (result.metadata.get("status_code") if isinstance(result.metadata, dict) else None)
                headers = result.metadata.get("headers") if isinstance(result.metadata, dict) else None
                failure_class, retry_after = ProviderFailureClassifier.classify(
                    error=result.error or result.exit_reason,
                    status_code=status_code,
                    headers=headers,
                )

                if failure_class in (
                    ProviderFailureClass.RATE_LIMITED,
                    ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED,
                    ProviderFailureClass.PROVIDER_OUTAGE,
                    ProviderFailureClass.BILLING,
                    ProviderFailureClass.AUTHENTICATION,
                    ProviderFailureClass.NETWORK,
                    ProviderFailureClass.MODEL_UNAVAILABLE,
                    ProviderFailureClass.CONTEXT_TOO_LARGE,
                ):
                    # Provider/capacity failure -> update registries
                    self.circuit_registry.record_failure(actor_id)
                    self.capacity_registry.record_provider_failure(
                        provider_id=provider_id,
                        failure_class=failure_class,
                        retry_after_seconds=retry_after,
                        reason=str(result.error),
                    )

                    if self.event_bridge:
                        if failure_class == ProviderFailureClass.RATE_LIMITED:
                            await self.event_bridge.emit_provider_rate_limited(provider_id, retry_after=retry_after, job_id=task.job_id)
                        elif failure_class in (ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED, ProviderFailureClass.BILLING):
                            await self.event_bridge.emit_provider_quota_exhausted(provider_id, reason=str(result.error), job_id=task.job_id)

                    # Attempt capability-based rerouting
                    alt_actor = self.reroute_policy.find_alternative_actor(task, failed_actor=actor_id)
                    if alt_actor:
                        task.assigned_actor = alt_actor
                        task.status = TaskStatus.READY
                        if self.event_bridge:
                            await self.event_bridge.emit_task_rerouted(
                                task_id=task.task_id,
                                job_id=task.job_id,
                                from_actor=actor_id,
                                to_actor=alt_actor,
                                reason=f"Provider {failure_class.value}: rerouted to capable alternative",
                            )
                            await self.event_bridge.emit_task_ready(task)
                        return task, result
                    else:
                        if failure_class in (
                            ProviderFailureClass.RATE_LIMITED,
                            ProviderFailureClass.PROVIDER_OUTAGE,
                            ProviderFailureClass.NETWORK,
                        ):
                            if self.event_bridge:
                                await self.event_bridge.emit_task_reroute_failed(
                                    task_id=task.task_id,
                                    job_id=task.job_id,
                                    reason=f"Provider {failure_class.value} and no healthy capable alternative available",
                                )
                            task.status = TaskStatus.READY
                            return task, result

                # Standard task logic failure or un-reroutable fatal provider failure
                if self.event_bridge:
                    await self.event_bridge.emit_task_failed(task=task, actor_id=actor_id, error=result.error)
                graph.mark_failure(task.task_id, error=result.error, allow_retry=True)

            return task, result

        except asyncio.CancelledError:
            # Record the cancellation on the graph so a cancelled job does not report its
            # in-flight work as still RUNNING, then propagate so the awaiting engine sees it.
            if graph.get_task(task.task_id) is not None and task.status in (TaskStatus.RUNNING, TaskStatus.READY):
                graph.mark_cancelled(task.task_id, reason="Execution cancelled")
            if self.event_bridge:
                await self.event_bridge.emit_task_cancelled(
                    task_id=task.task_id,
                    job_id=task.job_id,
                    reason="Execution cancelled",
                    attempt=task.attempt,
                    assigned_actor=actor_id,
                )
            raise

        finally:
            self._running_tasks.discard(task.task_id)
            self.release_actor(actor_id)


Scheduler = ReactiveScheduler
