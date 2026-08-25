import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set
import uuid

from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.storage.event_store import RuntimeEventStore

logger = logging.getLogger("hermes.runtime.events")


class RuntimeEventBridge:
    """
    Bridge connecting reactive execution runtime state transitions to the canonical RuntimeEventBus (SSE/UI)
    and the durable RuntimeEventStore (append-only event store).
    """

    def __init__(self, event_bus: Any = None, event_store: Optional[RuntimeEventStore] = None):
        self._bus = event_bus
        self._store = event_store
        self._captured_events: List[Dict[str, Any]] = []
        self._stored_events: List[StoredRuntimeEvent] = []
        self._pending_persists: Set[asyncio.Task] = set()
        self._last_persistence_error: Optional[Exception] = None

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

    async def flush(self) -> None:
        """
        Awaits completion of all in-flight persistence tasks.
        Raises any exception encountered during store append to ensure fail-closed durability.
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

    def _persist_background(self, event: StoredRuntimeEvent) -> None:
        if not self._store:
            return

        async def _do_append():
            try:
                stored = await self._store.append(event)
                self._stored_events.append(stored)
            except Exception as exc:
                logger.error("Failed to append event %s to event store: %s", event.event_id, exc)
                self._last_persistence_error = exc
                raise

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_do_append(), name=f"persist-event-{event.event_id}")
            self._pending_persists.add(task)
            task.add_done_callback(self._pending_persists.discard)
        except RuntimeError:
            # No running event loop in current thread
            pass

    def _publish(
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
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> StoredRuntimeEvent:
        meta = dict(metadata or {})
        event_dict = {
            "source_id": source_id,
            "source_kind": source_kind,
            "kind": kind,
            "detail": detail,
            "job_id": job_id,
            "duration": duration,
            "metadata": meta,
        }
        self._captured_events.append(event_dict)

        # 1. Publish to live SSE bus
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
                logger.debug("Failed publishing event to event_bus: %s", exc)

        # 2. Construct canonical StoredRuntimeEvent envelope
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
            causation_id=causation_id,
            correlation_id=correlation_id,
            payload=meta,
        )

        # 3. Persist to durable RuntimeEventStore
        self._persist_background(stored_event)

        return stored_event

    def emit_job_created(self, job: Any) -> StoredRuntimeEvent:
        payload = {
            "goal": job.goal,
            "priority": job.priority,
            "title": job.title,
            "repository": job.repository,
            "branch": job.branch,
            "createdAt": job.created_at,
            "metadata": job.metadata,
        }
        return self._publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="job.created",
            detail=f"Job {job.job_id} created: {job.goal[:80]}",
            job_id=job.job_id,
            metadata=payload,
            accent_color="#CBA35C",
        )

    def emit_job_state_changed(
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

        evt = self._publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="job.state_changed",
            detail=f"Job {job.job_id} transitioned from {meta['previous_state']} to {meta['new_state']}",
            job_id=job.job_id,
            metadata=meta,
            accent_color="#CBA35C",
        )

        # Also emit specialized terminal events
        state_str = meta["new_state"].lower()
        if state_str == "completed":
            self._publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.completed",
                detail=f"Job {job.job_id} completed successfully",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#4ADE80",
            )
        elif state_str == "blocked":
            self._publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.blocked",
                detail=f"Job {job.job_id} blocked: {reason or 'no reason given'}",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#F87171",
            )
        elif state_str == "failed":
            self._publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.failed",
                detail=f"Job {job.job_id} failed: {reason or 'failure'}",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#EF4444",
            )
        elif state_str == "cancelled":
            self._publish(
                source_id="lysstack.scheduler",
                source_kind="runtime",
                kind="job.cancelled",
                detail=f"Job {job.job_id} cancelled: {reason or 'cancelled'}",
                job_id=job.job_id,
                metadata=meta,
                accent_color="#F87171",
            )

        return evt

    def emit_task_created(self, task: Any, reason: Optional[str] = None) -> StoredRuntimeEvent:
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
        return self._publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="task.created",
            detail=f"Task {task.task_id} added: {task.description[:80]}",
            job_id=task.job_id,
            task_id=task.task_id,
            metadata=payload,
        )

    def emit_task_ready(self, task: Any) -> StoredRuntimeEvent:
        return self._publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="task.ready",
            detail=f"Task {task.task_id} is ready for dispatch",
            job_id=task.job_id,
            task_id=task.task_id,
            metadata={"taskId": task.task_id, "requiredCapabilities": task.required_capabilities},
        )

    def emit_task_assigned(self, task: Any, actor_id: str, decision: Optional[Dict[str, Any]] = None) -> StoredRuntimeEvent:
        return self._publish(
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

    def emit_task_started(self, task: Any, actor_id: str) -> StoredRuntimeEvent:
        return self._publish(
            source_id=actor_id,
            source_kind="agent",
            kind="task.started",
            detail=f"Task {task.task_id} started on actor '{actor_id}' (attempt {task.attempt})",
            job_id=task.job_id,
            task_id=task.task_id,
            actor_id=actor_id,
            metadata={"taskId": task.task_id, "actorId": actor_id, "attempt": task.attempt},
        )

    def emit_task_completed(self, task: Any, actor_id: str, artifacts: Optional[List[Dict[str, Any]]] = None) -> StoredRuntimeEvent:
        return self._publish(
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

    def emit_task_failed(self, task: Any, actor_id: str, error: Optional[Any] = None, allow_retry: bool = True) -> StoredRuntimeEvent:
        return self._publish(
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

    def emit_task_superseded(self, task_id: str, job_id: str, superseded_by: Optional[str] = None, reason: Optional[str] = None) -> StoredRuntimeEvent:
        return self._publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="task.superseded",
            detail=f"Task {task_id} superseded (by {superseded_by or 'plan change'}): {reason or 'no reason'}",
            job_id=job_id,
            task_id=task_id,
            metadata={"taskId": task_id, "supersededBy": superseded_by, "reason": reason},
        )

    def emit_agent_started(self, run: Any, task: Any) -> StoredRuntimeEvent:
        return self._publish(
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

    def emit_agent_finished(self, run: Any, task: Any, result: Any) -> StoredRuntimeEvent:
        return self._publish(
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

    def emit_agent_failed(self, run: Any, task: Any, error: str) -> StoredRuntimeEvent:
        return self._publish(
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

    def emit_agent_timed_out(self, run: Any, task: Any, timeout_seconds: Optional[float] = None) -> StoredRuntimeEvent:
        return self._publish(
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

    def emit_observation_created(self, observation: Any) -> StoredRuntimeEvent:
        meta = observation.to_dict() if hasattr(observation, "to_dict") else dict(observation)
        return self._publish(
            source_id=observation.actor_id or "lysstack.runtime",
            source_kind="agent" if observation.actor_id else "runtime",
            kind="observation.created",
            detail=f"Observation ({observation.kind}): {observation.content[:80]}",
            job_id=observation.job_id,
            task_id=observation.task_id,
            actor_id=observation.actor_id,
            metadata=meta,
        )

    def emit_artifact_created(self, artifact: Any, job_id: Optional[str] = None) -> StoredRuntimeEvent:
        meta = artifact.to_dict() if hasattr(artifact, "to_dict") else dict(artifact)
        jid = job_id or meta.get("job_id") or meta.get("jobId")
        return self._publish(
            source_id="lysstack.artifacts",
            source_kind="runtime",
            kind="artifact.created",
            detail=f"Artifact created: {meta.get('label') or meta.get('id')}",
            job_id=jid,
            task_id=meta.get("task_id") or meta.get("taskId"),
            metadata=meta,
        )

    def emit_verification_started(self, job_id: str, verifier_id: str) -> StoredRuntimeEvent:
        return self._publish(
            source_id="lysstack.verifier",
            source_kind="runtime",
            kind="verification.started",
            detail=f"Verification started for job {job_id} using '{verifier_id}'",
            job_id=job_id,
            metadata={"verifierId": verifier_id},
        )

    def emit_verification_passed(self, job_id: str, result: Any) -> StoredRuntimeEvent:
        return self._publish(
            source_id="lysstack.verifier",
            source_kind="runtime",
            kind="verification.passed",
            detail=f"Verification passed for job {job_id}: {result.summary}",
            job_id=job_id,
            metadata=result.to_dict() if hasattr(result, "to_dict") else {},
            accent_color="#4ADE80",
        )

    def emit_verification_failed(self, job_id: str, result: Any) -> StoredRuntimeEvent:
        return self._publish(
            source_id="lysstack.verifier",
            source_kind="runtime",
            kind="verification.failed",
            detail=f"Verification failed for job {job_id} (repairable={getattr(result, 'is_repairable', False)}): {result.summary}",
            job_id=job_id,
            metadata=result.to_dict() if hasattr(result, "to_dict") else {},
            accent_color="#EF4444",
        )

    def emit_replan_requested(self, job_id: str, reason: str, remaining_budget: int) -> StoredRuntimeEvent:
        return self._publish(
            source_id="lysstack.scheduler",
            source_kind="runtime",
            kind="replan.requested",
            detail=f"Replanning requested for job {job_id} (reason: {reason}, budget remaining: {remaining_budget})",
            job_id=job_id,
            metadata={"reason": reason, "remainingBudget": remaining_budget},
        )

    def emit_replan_completed(self, job_id: str, mutations_count: int, explanation: str) -> StoredRuntimeEvent:
        return self._publish(
            source_id="lysstack.planner",
            source_kind="runtime",
            kind="replan.completed",
            detail=f"Replanning completed for job {job_id} with {mutations_count} mutations: {explanation}",
            job_id=job_id,
            metadata={"mutationsCount": mutations_count, "explanation": explanation},
        )
