import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set
import uuid

from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.storage.event_store import RuntimeEventStore, StorageUnavailableError, EventPersistenceError

logger = logging.getLogger("hermes.runtime.events")

def _make_json_safe(obj: Any) -> Any:
    from pathlib import Path
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_make_json_safe(x) for x in obj]
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _make_json_safe(obj.to_dict())
    return obj


class RuntimeEventBridge:
    """
    Bridge connecting reactive execution runtime state transitions to the canonical RuntimeEventBus (SSE/UI)
    and the durable RuntimeEventStore (append-only event store).

    Guarantees strict durable commit semantics:
    1. Canonical StoredRuntimeEvent is created.
    2. Event is persisted to RuntimeEventStore.
    3. Live SSE / EventBus notification is dispatched only AFTER successful persistence.
    4. Storage failures fail fast and prevent uncommitted transitions from being acknowledged.
    """

    def __init__(self, event_bus: Any = None, event_store: Optional[RuntimeEventStore] = None):
        self._bus = event_bus
        self._store = event_store
        self._captured_events: List[Dict[str, Any]] = []
        self._stored_events: List[StoredRuntimeEvent] = []
        self._pending_persists: Set[asyncio.Task] = set()
        self._last_persistence_error: Optional[Exception] = None
        self._cancelled_tasks: Dict[str, Set[str]] = {}
        self._cancelled_runs: Dict[str, Set[str]] = {}

    def set_bus(self, event_bus: Any) -> None:
        self._bus = event_bus

    def set_store(self, event_store: RuntimeEventStore) -> None:
        self._store = event_store

    def get_store(self) -> Optional[RuntimeEventStore]:
        return self._store

    @property
    def captured_events(self) -> List[Dict[str, Any]]:
        return list(self._captured_events)

    @property
    def stored_events(self) -> List[StoredRuntimeEvent]:
        return list(self._stored_events)

    def clear(self) -> None:
        self._captured_events.clear()
        self._stored_events.clear()
        self._last_persistence_error = None
        self._cancelled_tasks.clear()
        self._cancelled_runs.clear()

    async def flush(self) -> None:
        """
        Awaits completion of all in-flight persistence tasks and raises any stored persistence errors.
        """
        if self._pending_persists:
            pending = list(self._pending_persists)
            results = await asyncio.gather(*pending, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    self._last_persistence_error = res
                    raise res
        if self._last_persistence_error:
            err = self._last_persistence_error
            self._last_persistence_error = None
            raise err

    async def persist_and_publish(
        self,
        source_id: str,
        source_kind: str,
        kind: str,
        detail: str,
        job_id: Optional[str] = None,
        duration: Optional[str] = "—",
        metadata: Optional[Dict[str, Any]] = None,
        accent_color: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> StoredRuntimeEvent:
        """
        Core durable emission path:
        1. Construct canonical StoredRuntimeEvent.
        2. Await append to durable event store.
        3. Only after successful persistence, record captured event and publish to live SSE/event_bus.
        4. If persistence fails, fail-closed without publishing live event.
        """
        meta = _make_json_safe(dict(metadata or {}))
        event_dict = {
            "source_id": source_id,
            "source_kind": source_kind,
            "kind": kind,
            "detail": detail,
            "job_id": job_id,
            "duration": duration,
            "metadata": meta,
        }

        # 1. Construct canonical StoredRuntimeEvent envelope
        stored_event = StoredRuntimeEvent(
            event_id=str(uuid.uuid4()),
            job_id=job_id or "job_unspecified",
            sequence=0,  # Allocated atomically by event store
            event_type=kind,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            schema_version=1,
            task_id=task_id,
            run_id=run_id,
            actor_id=actor_id,
            parent_event_id=parent_event_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            payload=meta,
        )

        # 2. Persist to durable RuntimeEventStore (await directly)
        if self._store:
            try:
                persisted = await self._store.append(stored_event)
                self._stored_events.append(persisted)
                stored_event = persisted
            except Exception as exc:
                logger.error("Failed to append event %s (%s) to event store: %s", stored_event.event_id, kind, exc)
                self._last_persistence_error = exc
                raise
        else:
            self._stored_events.append(stored_event)

        # 3. Only after successful persistence, record captured event and publish to live SSE bus
        self._captured_events.append(event_dict)

        if self._bus and hasattr(self._bus, "publish"):
            try:
                self._bus.publish(
                    source_id=source_id,
                    source_kind=source_kind,
                    kind=kind,
                    detail=detail,
                    job_id=job_id,
                    duration=duration or "—",
                    metadata=meta,
                    accent_color=accent_color,
                )
            except Exception as exc:
                logger.debug("Failed publishing event to live event_bus: %s", exc)

        return stored_event

    async def emit_job_created(self, job: Any) -> StoredRuntimeEvent:
        payload = {
            "goal": job.goal,
            "priority": job.priority,
            "title": job.title,
            "repository": job.repository,
            "branch": job.branch,
            "createdAt": job.created_at,
            "metadata": job.metadata,
        }
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="job.created",
            detail=f"Job {job.job_id} created: {job.goal[:80]}",
            job_id=job.job_id,
            metadata=payload,
            accent_color="#CBA35C",
        )

    async def emit_job_state_changed(
        self,
        job: Any,
        previous_state: Any,
        reason: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StoredRuntimeEvent:
        meta = dict(metadata or {})
        meta["previous_state"] = previous_state.value if hasattr(previous_state, "value") else str(previous_state)
        meta["new_state"] = job.state.value if hasattr(job.state, "value") else str(job.state)
        if reason:
            meta["reason"] = reason

        state_str = meta["new_state"].lower()
        if state_str == "completed":
            return await self.persist_and_publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.completed",
                detail=f"Job {job.job_id} completed successfully",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#4ADE80",
            )
        elif state_str == "blocked":
            return await self.persist_and_publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.blocked",
                detail=f"Job {job.job_id} blocked: {reason or 'no reason given'}",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#F87171",
            )
        elif state_str == "failed":
            return await self.persist_and_publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.failed",
                detail=f"Job {job.job_id} failed: {reason or 'failure'}",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#EF4444",
            )
        elif state_str == "cancelled":
            return await self.persist_and_publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.cancelled",
                detail=f"Job {job.job_id} cancelled: {reason or 'cancelled'}",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#F87171",
            )
        else:
            return await self.persist_and_publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.state_changed",
                detail=f"Job {job.job_id} transitioned from {meta['previous_state']} to {meta['new_state']}",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#CBA35C",
            )

    async def emit_task_created(self, task: Any, reason: Optional[str] = None) -> StoredRuntimeEvent:
        payload = {
            "taskId": task.task_id,
            "description": task.description,
            "dependencies": list(task.dependencies),
            "requiredCapabilities": list(task.required_capabilities),
            "assignedActor": task.assigned_actor,
            "maxAttempts": task.max_attempts,
            "reason": reason,
            "metadata": task.metadata,
        }
        return await self.persist_and_publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="task.created",
            detail=f"Task {task.task_id} added: {task.description[:80]}",
            job_id=task.job_id,
            task_id=task.task_id,
            metadata=payload,
        )

    async def emit_task_ready(self, task: Any) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="task.ready",
            detail=f"Task {task.task_id} is ready for dispatch",
            job_id=task.job_id,
            task_id=task.task_id,
            metadata={"taskId": task.task_id, "requiredCapabilities": task.required_capabilities},
        )

    async def emit_task_assigned(self, task: Any, actor_id: str, decision: Optional[Dict[str, Any]] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="task.assigned",
            detail=f"Task {task.task_id} assigned to actor '{actor_id}'",
            job_id=task.job_id,
            task_id=task.task_id,
            actor_id=actor_id,
            metadata={
                "taskId": task.task_id,
                "assignedActor": actor_id,
                "delegationDecision": decision,
            },
        )

    async def emit_task_started(self, task: Any, actor_id: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=actor_id,
            source_kind="agent",
            kind="task.started",
            detail=f"Task {task.task_id} started on actor '{actor_id}' (attempt {task.attempt})",
            job_id=task.job_id,
            task_id=task.task_id,
            actor_id=actor_id,
            metadata={"taskId": task.task_id, "actorId": actor_id, "attempt": task.attempt},
        )

    async def emit_task_completed(self, task: Any, actor_id: str, artifacts: Optional[List[Dict[str, Any]]] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=actor_id,
            source_kind="agent",
            kind="task.completed",
            detail=f"Task {task.task_id} completed successfully by actor '{actor_id}'",
            job_id=task.job_id,
            task_id=task.task_id,
            actor_id=actor_id,
            metadata={
                "taskId": task.task_id,
                "actorId": actor_id,
                "artifactsCount": len(artifacts or []),
                "artifact_refs": artifacts or [],
            },
        )

    async def emit_task_failed(self, task: Any, actor_id: str, error: Optional[Any] = None, allow_retry: bool = True) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=actor_id,
            source_kind="agent",
            kind="task.failed",
            detail=f"Task {task.task_id} failed on actor '{actor_id}' (attempt {task.attempt}): {error}",
            job_id=task.job_id,
            task_id=task.task_id,
            actor_id=actor_id,
            metadata={
                "taskId": task.task_id,
                "actorId": actor_id,
                "attempt": task.attempt,
                "error": str(error),
                "allow_retry": allow_retry,
            },
        )

    async def emit_task_superseded(self, task_id: str, job_id: str, superseded_by: Optional[str] = None, reason: Optional[str] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="task.superseded",
            detail=f"Task {task_id} superseded (by {superseded_by or 'plan change'}): {reason or 'no reason'}",
            job_id=job_id,
            task_id=task_id,
            metadata={"taskId": task_id, "supersededBy": superseded_by, "reason": reason},
        )

    async def emit_task_cancelled(
        self,
        task_id: str,
        job_id: str,
        reason: Optional[str] = None,
        attempt: int = 0,
        assigned_actor: Optional[str] = None,
    ) -> Optional[StoredRuntimeEvent]:
        cancelled_set = self._cancelled_tasks.setdefault(job_id, set())
        if task_id in cancelled_set:
            logger.debug("task.cancelled already emitted for task %s (skipping duplicate)", task_id)
            return None

        res = await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="task.cancelled",
            detail=f"Task {task_id} cancelled: {reason or 'no reason'}",
            job_id=job_id,
            task_id=task_id,
            actor_id=assigned_actor,
            metadata={
                "taskId": task_id,
                "reason": reason or "cancelled",
                "attempt": attempt,
                "assignedActor": assigned_actor,
            },
            accent_color="#F87171",
        )
        cancelled_set.add(task_id)
        return res

    async def emit_agent_started(self, run: Any, task: Any) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=run.actor_id,
            source_kind="agent",
            kind="agent.started",
            detail=f"Agent '{run.actor_id}' started run {run.run_id} for task {task.task_id}",
            job_id=run.job_id,
            task_id=task.task_id,
            run_id=run.run_id,
            actor_id=run.actor_id,
            metadata={"runId": run.run_id, "taskId": task.task_id, "actorId": run.actor_id, "attempt": run.attempt, "metadata": run.metadata},
        )

    async def emit_agent_finished(self, run: Any, task: Any, result: Any) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=run.actor_id,
            source_kind="agent",
            kind="agent.finished",
            detail=f"Agent '{run.actor_id}' finished run {run.run_id} (status: {result.status})",
            job_id=run.job_id,
            task_id=task.task_id,
            run_id=run.run_id,
            actor_id=run.actor_id,
            metadata={"runId": run.run_id, "taskId": task.task_id, "actorId": run.actor_id, "exitReason": result.exit_reason, "artifact_refs": result.artifact_refs},
        )

    async def emit_agent_failed(self, run: Any, task: Any, error: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=run.actor_id,
            source_kind="agent",
            kind="agent.failed",
            detail=f"Agent '{run.actor_id}' failed run {run.run_id}: {error}",
            job_id=run.job_id,
            task_id=task.task_id,
            run_id=run.run_id,
            actor_id=run.actor_id,
            metadata={"runId": run.run_id, "taskId": task.task_id, "actorId": run.actor_id, "error": error},
        )

    async def emit_agent_timed_out(self, run: Any, task: Any, timeout_seconds: Optional[float] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=run.actor_id,
            source_kind="agent",
            kind="agent.timed_out",
            detail=f"Agent '{run.actor_id}' timed out after {timeout_seconds}s for task {task.task_id}",
            job_id=run.job_id,
            task_id=task.task_id,
            run_id=run.run_id,
            actor_id=run.actor_id,
            metadata={"runId": run.run_id, "taskId": task.task_id, "actorId": run.actor_id, "attempt": run.attempt, "timeoutSeconds": timeout_seconds},
        )

    async def emit_agent_cancelled(self, run: Any, task: Any, reason: Optional[str] = None) -> Optional[StoredRuntimeEvent]:
        job_id = getattr(task, "job_id", None) or getattr(run, "job_id", "")
        run_id = getattr(run, "run_id", "")
        if job_id and run_id:
            cancelled_runs_set = self._cancelled_runs.setdefault(job_id, set())
            if run_id in cancelled_runs_set:
                logger.debug("agent.cancelled already emitted for run %s (skipping duplicate)", run_id)
                return None

        res = await self.persist_and_publish(
            source_id=run.actor_id,
            source_kind="agent",
            kind="agent.cancelled",
            detail=f"Agent '{run.actor_id}' cancelled run {run.run_id} for task {task.task_id}: {reason or 'cancelled'}",
            job_id=run.job_id,
            task_id=task.task_id,
            run_id=run.run_id,
            actor_id=run.actor_id,
            metadata={"runId": run.run_id, "taskId": task.task_id, "actorId": run.actor_id, "attempt": run.attempt, "reason": reason or "cancelled"},
            accent_color="#F87171",
        )
        if job_id and run_id:
            self._cancelled_runs.setdefault(job_id, set()).add(run_id)
        return res

    async def emit_observation_created(self, observation: Any) -> StoredRuntimeEvent:
        meta = observation.to_dict() if hasattr(observation, "to_dict") else dict(observation)
        return await self.persist_and_publish(
            source_id=observation.actor_id or "lysstack.runtime",
            source_kind="agent" if observation.actor_id else "runtime",
            kind="observation.created",
            detail=f"Observation ({observation.kind}): {observation.content[:80]}",
            job_id=observation.job_id,
            task_id=observation.task_id,
            actor_id=observation.actor_id,
            metadata=meta,
        )

    async def emit_artifact_created(self, artifact: Any, job_id: Optional[str] = None) -> StoredRuntimeEvent:
        meta = artifact.to_dict() if hasattr(artifact, "to_dict") else dict(artifact)
        jid = job_id or meta.get("job_id") or meta.get("jobId")
        return await self.persist_and_publish(
            source_id="lysstack.artifacts",
            source_kind="runtime",
            kind="artifact.created",
            detail=f"Artifact created: {meta.get('label') or meta.get('id')}",
            job_id=jid,
            task_id=meta.get("task_id") or meta.get("taskId"),
            metadata=meta,
        )

    async def emit_verification_started(self, job_id: str, verifier_id: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.verifier",
            source_kind="runtime",
            kind="verification.started",
            detail=f"Verification started for job {job_id} using '{verifier_id}'",
            job_id=job_id,
            metadata={"verifierId": verifier_id},
        )

    async def emit_verification_passed(self, job_id: str, result: Any) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.verifier",
            source_kind="runtime",
            kind="verification.passed",
            detail=f"Verification passed for job {job_id}: {result.summary}",
            job_id=job_id,
            metadata=result.to_dict() if hasattr(result, "to_dict") else {},
            accent_color="#4ADE80",
        )

    async def emit_verification_failed(self, job_id: str, result: Any) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.verifier",
            source_kind="runtime",
            kind="verification.failed",
            detail=f"Verification failed for job {job_id} (repairable={getattr(result, 'is_repairable', False)}): {result.summary}",
            job_id=job_id,
            metadata=result.to_dict() if hasattr(result, "to_dict") else {},
            accent_color="#EF4444",
        )

    async def emit_replan_requested(self, job_id: str, reason: str, remaining_budget: int) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="replan.requested",
            detail=f"Replanning requested for job {job_id} (reason: {reason}, budget remaining: {remaining_budget})",
            job_id=job_id,
            metadata={"reason": reason, "remainingBudget": remaining_budget},
        )

    async def emit_replan_completed(self, job_id: str, mutations_count: int, explanation: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="replan.completed",
            detail=f"Replanning completed for job {job_id} with {mutations_count} mutations: {explanation}",
            job_id=job_id,
            metadata={"mutationsCount": mutations_count, "explanation": explanation},
        )

    # --- Phase 11.1: Initial Planning Events ---
    async def emit_planning_started(
        self,
        job_id: str,
        goal: str,
        constraints: Optional[List[str]] = None,
        repo_dir: Optional[str] = None,
    ) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="planning.started",
            detail=f"Initial planning started for goal: {goal[:80]}",
            job_id=job_id,
            metadata={"goal": goal, "constraints": constraints or [], "repoDir": repo_dir},
            accent_color="#6366F1",
        )

    async def emit_repository_evidence_collected(
        self,
        job_id: str,
        file_count: int,
        summary: str,
        uncertainty: Optional[List[str]] = None,
    ) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.reconnaissance",
            source_kind="runtime",
            kind="repository.evidence_collected",
            detail=f"Collected {file_count} evidence files from repository",
            job_id=job_id,
            metadata={"fileCount": file_count, "summary": summary, "uncertainty": uncertainty or []},
            accent_color="#8B5CF6",
        )

    async def emit_planning_generated(
        self,
        job_id: str,
        task_count: int,
        summary: str,
        plan_dict: Optional[Dict[str, Any]] = None,
        planning_mode: str = "model_generated",
    ) -> StoredRuntimeEvent:
        mode = (plan_dict.get("planning_mode") if plan_dict else None) or planning_mode or "model_generated"
        return await self.persist_and_publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="planning.generated",
            detail=f"Generated structured plan ({mode}) with {task_count} tasks: {summary[:80]}",
            job_id=job_id,
            metadata={"taskCount": task_count, "summary": summary, "plan": plan_dict or {}, "planning_mode": mode, "planningMode": mode},
            accent_color="#3B82F6",
        )

    async def emit_planning_validated(
        self,
        job_id: str,
        task_count: int,
        valid: bool = True,
    ) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="planning.validated",
            detail=f"Plan validation passed for {task_count} tasks",
            job_id=job_id,
            metadata={"taskCount": task_count, "valid": valid},
            accent_color="#10B981",
        )

    async def emit_planning_failed(
        self,
        job_id: str,
        error: str,
        reasons: Optional[List[str]] = None,
    ) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="planning.failed",
            detail=f"Planning failed for job {job_id}: {error}",
            job_id=job_id,
            metadata={"error": error, "reasons": reasons or []},
            accent_color="#EF4444",
        )

    # --- Phase 10: Recovery Events ---
    async def emit_recovery_started(self, job_id: str, recovery_id: str, detected_interruption_at: Optional[str] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.started",
            detail=f"Recovery started for job {job_id} (session {recovery_id})",
            job_id=job_id,
            metadata={"recoveryId": recovery_id, "detectedInterruptionAt": detected_interruption_at},
            accent_color="#38BDF8",
        )

    async def emit_recovery_job_rehydrated(self, job_id: str, tasks_count: int, runs_count: int) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.job_rehydrated",
            detail=f"Job {job_id} state rehydrated from event store ({tasks_count} tasks, {runs_count} runs)",
            job_id=job_id,
            metadata={"tasksCount": tasks_count, "runsCount": runs_count},
        )

    async def emit_recovery_task_interrupted(self, task_id: str, job_id: str, reason: str = "Process interrupted") -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.task_interrupted",
            detail=f"Task {task_id} in job {job_id} was interrupted: {reason}",
            job_id=job_id,
            task_id=task_id,
            metadata={"taskId": task_id, "reason": reason},
            accent_color="#F59E0B",
        )

    async def emit_recovery_task_reconciled(self, task_id: str, job_id: str, evidence: Dict[str, Any]) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.task_reconciled",
            detail=f"Task {task_id} in job {job_id} reconciled from durable side-effect evidence",
            job_id=job_id,
            task_id=task_id,
            metadata={"taskId": task_id, "evidence": evidence},
            accent_color="#10B981",
        )

    async def emit_recovery_task_requeued(self, task_id: str, job_id: str, reason: str = "Safely requeued") -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.task_requeued",
            detail=f"Task {task_id} in job {job_id} requeued for safe execution: {reason}",
            job_id=job_id,
            task_id=task_id,
            metadata={"taskId": task_id, "reason": reason},
            accent_color="#60A5FA",
        )

    async def emit_recovery_completed(self, job_id: str, rto_seconds: float, summary: Dict[str, Any]) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.completed",
            detail=f"Recovery completed for job {job_id} in {rto_seconds:.2f}s (RTO)",
            job_id=job_id,
            metadata={"rtoSeconds": rto_seconds, "summary": summary},
            accent_color="#22C55E",
        )

    async def emit_recovery_execution_resumed(self, job_id: str, rto_seconds: float, summary: Dict[str, Any]) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.execution_resumed",
            detail=f"Execution resumed for job {job_id} in {rto_seconds:.2f}s (True RTO)",
            job_id=job_id,
            metadata={"rtoSeconds": rto_seconds, "summary": summary},
            accent_color="#22C55E",
        )

    async def emit_recovery_failed(self, job_id: str, error: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.recovery",
            source_kind="runtime",
            kind="recovery.failed",
            detail=f"Recovery failed for job {job_id}: {error}",
            job_id=job_id,
            metadata={"error": error},
            accent_color="#EF4444",
        )

    # --- Phase 10: Rerouting Events ---
    async def emit_task_reroute_requested(self, task_id: str, job_id: str, from_actor: str, reason: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="task.reroute_requested",
            detail=f"Reroute requested for task {task_id} from '{from_actor}': {reason}",
            job_id=job_id,
            task_id=task_id,
            metadata={"taskId": task_id, "fromActor": from_actor, "reason": reason},
            accent_color="#FB923C",
        )

    async def emit_task_rerouted(
        self,
        task_id: str,
        job_id: str,
        from_actor: str,
        to_actor: str,
        reason: str,
        previous_run_id: Optional[str] = None,
    ) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="task.rerouted",
            detail=f"Task {task_id} rerouted from '{from_actor}' to '{to_actor}': {reason}",
            job_id=job_id,
            task_id=task_id,
            actor_id=to_actor,
            metadata={
                "taskId": task_id,
                "fromActor": from_actor,
                "toActor": to_actor,
                "reason": reason,
                "previousRunId": previous_run_id,
            },
            accent_color="#A855F7",
        )

    async def emit_task_reroute_failed(self, task_id: str, job_id: str, reason: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="task.reroute_failed",
            detail=f"Reroute failed for task {task_id}: {reason}",
            job_id=job_id,
            task_id=task_id,
            metadata={"taskId": task_id, "reason": reason},
            accent_color="#EF4444",
        )

    # --- Phase 10: Capacity Waiting Events ---
    async def emit_job_waiting_for_capacity(self, job: Any, reason: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="job.waiting_for_capacity",
            detail=f"Job {job.job_id} waiting for provider capacity: {reason}",
            job_id=job.job_id,
            metadata={"reason": reason},
            accent_color="#F59E0B",
        )

    async def emit_job_capacity_restored(self, job: Any, reason: str = "Capacity restored") -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="job.capacity_restored",
            detail=f"Provider capacity restored for job {job.job_id}: {reason}",
            job_id=job.job_id,
            metadata={"reason": reason},
            accent_color="#34D399",
        )

    # --- Phase 10: Provider & Circuit Events ---
    async def emit_provider_rate_limited(self, provider_id: str, retry_after: Optional[float] = None, job_id: Optional[str] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=f"provider.{provider_id}",
            source_kind="provider",
            kind="provider.rate_limited",
            detail=f"Provider '{provider_id}' rate limited (retry-after: {retry_after}s)",
            job_id=job_id or "system",
            metadata={"providerId": provider_id, "retryAfter": retry_after},
            accent_color="#F97316",
        )

    async def emit_provider_quota_exhausted(self, provider_id: str, reason: str = "Quota exhausted", job_id: Optional[str] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=f"provider.{provider_id}",
            source_kind="provider",
            kind="provider.quota_exhausted",
            detail=f"Provider '{provider_id}' quota exhausted: {reason}",
            job_id=job_id or "system",
            metadata={"providerId": provider_id, "reason": reason},
            accent_color="#DC2626",
        )

    async def emit_circuit_opened(self, target_id: str, cooldown_seconds: float, job_id: Optional[str] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=f"circuit.{target_id}",
            source_kind="runtime",
            kind="circuit.opened",
            detail=f"Circuit opened for '{target_id}' (cooldown: {cooldown_seconds}s)",
            job_id=job_id or "system",
            metadata={"targetId": target_id, "cooldownSeconds": cooldown_seconds},
            accent_color="#DC2626",
        )

    async def emit_circuit_half_opened(self, target_id: str, job_id: Optional[str] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=f"circuit.{target_id}",
            source_kind="runtime",
            kind="circuit.half_opened",
            detail=f"Circuit half-opened for '{target_id}' (probing recovery)",
            job_id=job_id or "system",
            metadata={"targetId": target_id},
            accent_color="#FBBF24",
        )

    async def emit_circuit_closed(self, target_id: str, job_id: Optional[str] = None) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=f"circuit.{target_id}",
            source_kind="runtime",
            kind="circuit.closed",
            detail=f"Circuit closed for '{target_id}' (healthy)",
            job_id=job_id or "system",
            metadata={"targetId": target_id},
            accent_color="#10B981",
        )

    async def emit_model_call_started(self, provider: str, model: str, actor_id: str, task_id: str, run_id: str, job_id: str) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=actor_id,
            source_kind="agent",
            kind="model.call_started",
            detail=f"Model call started ({provider}/{model}) for task {task_id}",
            job_id=job_id,
            task_id=task_id,
            run_id=run_id,
            actor_id=actor_id,
            metadata={"provider": provider, "model": model, "actorId": actor_id, "taskId": task_id, "runId": run_id},
        )

    async def emit_model_call_completed(
        self,
        provider: str,
        model: str,
        actor_id: str,
        task_id: str,
        run_id: str,
        job_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency: float = 0.0,
    ) -> StoredRuntimeEvent:
        return await self.persist_and_publish(
            source_id=actor_id,
            source_kind="agent",
            kind="model.call_completed",
            detail=f"Model call completed ({provider}/{model}): {input_tokens} in / {output_tokens} out in {latency:.2f}s",
            job_id=job_id,
            task_id=task_id,
            run_id=run_id,
            actor_id=actor_id,
            metadata={
                "provider": provider,
                "model": model,
                "actorId": actor_id,
                "taskId": task_id,
                "runId": run_id,
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "latency": latency,
            },
        )
