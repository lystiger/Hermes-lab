from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.execution import AgentRun, AgentRunStatus
from runtime.observations import Observation
from runtime.verification import VerificationResult, VerificationStatus
from runtime.storage.schema_registry import StoredRuntimeEvent, schema_registry

logger = logging.getLogger("hermes.runtime.storage.projector")


@dataclass
class ReconstructedRuntimeState:
    """
    Complete state reconstructed deterministically from a job's event history.
    """
    job: JobRecord
    graph: TaskGraph
    runs: List[AgentRun] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    last_verification: Optional[VerificationResult] = None

    def get_run(self, run_id: str) -> Optional[AgentRun]:
        for r in self.runs:
            if r.run_id == run_id:
                return r
        return None

    def get_observation(self, observation_id: str) -> Optional[Observation]:
        for o in self.observations:
            if o.observation_id == observation_id:
                return o
        return None


class RuntimeStateProjector:
    """
    Deterministic reducer/projector that folds an ordered sequence of canonical
    StoredRuntimeEvents into an authoritative ReconstructedRuntimeState.
    """

    @classmethod
    def project(cls, events: List[StoredRuntimeEvent]) -> ReconstructedRuntimeState:
        if not events:
            raise ValueError("Cannot project state from an empty event list")

        # Sort strictly by sequence
        sorted_events = sorted(events, key=lambda e: e.sequence)

        # Ensure events are upcasted
        upcasted_events = [schema_registry.upcast(e) for e in sorted_events]

        job_id = upcasted_events[0].job_id
        job = JobRecord(job_id=job_id, goal="")
        graph = TaskGraph(job_id=job_id)
        runs_map: Dict[str, AgentRun] = {}
        observations_map: Dict[str, Observation] = {}
        artifacts: List[Dict[str, Any]] = []
        last_verification: Optional[VerificationResult] = None

        for event in upcasted_events:
            event_type = event.event_type
            payload = event.payload or {}

            # --- Job Lifecycle Events ---
            if event_type == "job.created":
                goal = payload.get("goal") or payload.get("title") or ""
                job.goal = goal
                job.title = payload.get("title") or (goal[:80] if goal else f"Job {job.job_id}")
                job.priority = payload.get("priority", "P1")
                job.repository = payload.get("repository")
                job.branch = payload.get("branch")
                job.created_at = payload.get("createdAt") or event.occurred_at
                job.state = JobState.CREATED
                if payload.get("metadata"):
                    job.metadata.update(payload.get("metadata"))

            elif event_type == "job.state_changed":
                prev_state_str = (payload.get("previous_state") or "").lower()
                new_state_str = (payload.get("new_state") or "").lower()
                reason = payload.get("reason")

                try:
                    target_state = JobState(new_state_str)
                    job.state = target_state
                except ValueError:
                    logger.warning("Unknown JobState: %s", new_state_str)

                if job.state in {JobState.PLANNING, JobState.EXECUTING} and not job.started_at:
                    job.started_at = event.occurred_at

                if job.is_terminal and not job.completed_at:
                    job.completed_at = event.occurred_at

                if job.state == JobState.BLOCKED:
                    job.blocked_reason = reason
                elif job.state == JobState.FAILED:
                    job.failure_reason = reason
                elif job.state == JobState.REPAIRING:
                    job.repair_count += 1
                elif job.state == JobState.PLANNING and prev_state_str in {"executing", "repairing"}:
                    job.replan_count += 1

                if payload.get("metadata"):
                    job.metadata.update(payload["metadata"])

            elif event_type == "job.completed":
                job.state = JobState.COMPLETED
                job.completed_at = job.completed_at or event.occurred_at

            elif event_type == "job.blocked":
                job.state = JobState.BLOCKED
                job.blocked_reason = payload.get("reason") or payload.get("detail")
                job.completed_at = job.completed_at or event.occurred_at

            elif event_type == "job.failed":
                job.state = JobState.FAILED
                job.failure_reason = payload.get("reason") or payload.get("detail")
                job.completed_at = job.completed_at or event.occurred_at

            elif event_type == "job.cancelled":
                job.state = JobState.CANCELLED
                job.completed_at = job.completed_at or event.occurred_at

            # --- Task Graph Events ---
            elif event_type == "task.created":
                task_id = payload.get("taskId") or payload.get("task_id") or event.task_id or ""
                description = payload.get("description") or payload.get("name") or ""
                dependencies = payload.get("dependencies") or []
                required_caps = payload.get("requiredCapabilities") or payload.get("required_capabilities") or []
                assigned_actor = payload.get("assignedActor") or payload.get("assigned_actor")
                max_attempts = payload.get("max_attempts") or payload.get("maxAttempts") or 2

                existing_task = graph.get_task(task_id)
                if not existing_task:
                    node = TaskNode(
                        task_id=task_id,
                        job_id=job_id,
                        description=description,
                        status=TaskStatus.PENDING,
                        dependencies=list(dependencies),
                        required_capabilities=list(required_caps),
                        assigned_actor=assigned_actor,
                        created_at=event.occurred_at,
                        max_attempts=int(max_attempts),
                        metadata=dict(payload.get("metadata") or {}),
                    )
                    try:
                        graph.add_task(node)
                    except ValueError:
                        pass
                else:
                    if dependencies:
                        for d in dependencies:
                            if d not in existing_task.dependencies:
                                existing_task.dependencies.append(d)

            elif event_type == "task.ready":
                task_id = payload.get("taskId") or event.task_id or ""
                task = graph.get_task(task_id)
                if task and task.status not in {TaskStatus.SUCCEEDED, TaskStatus.SUPERSEDED, TaskStatus.CANCELLED}:
                    task.status = TaskStatus.READY

            elif event_type == "task.assigned":
                task_id = payload.get("taskId") or event.task_id or ""
                actor_id = payload.get("assignedActor") or payload.get("actorId") or event.actor_id
                task = graph.get_task(task_id)
                if task:
                    task.assigned_actor = actor_id

            elif event_type == "task.started":
                task_id = payload.get("taskId") or event.task_id or ""
                actor_id = payload.get("actorId") or event.actor_id
                task = graph.get_task(task_id)
                if task:
                    task.status = TaskStatus.RUNNING
                    task.started_at = task.started_at or event.occurred_at
                    if actor_id:
                        task.assigned_actor = actor_id
                    if "attempt" in payload:
                        task.attempt = int(payload["attempt"])
                    else:
                        task.attempt += 1

            elif event_type == "task.completed":
                task_id = payload.get("taskId") or event.task_id or ""
                actor_id = payload.get("actorId") or event.actor_id
                task = graph.get_task(task_id)
                if task:
                    task.status = TaskStatus.SUCCEEDED
                    task.completed_at = event.occurred_at
                    task.error = None
                    if actor_id:
                        task.assigned_actor = actor_id
                    if payload.get("artifact_refs"):
                        task.artifact_refs.extend(payload["artifact_refs"])

            elif event_type == "task.failed":
                task_id = payload.get("taskId") or event.task_id or ""
                error = payload.get("error")
                task = graph.get_task(task_id)
                if task:
                    task.error = error
                    if "attempt" in payload:
                        task.attempt = int(payload["attempt"])
                    allow_retry = payload.get("allow_retry", task.attempt < task.max_attempts)
                    if allow_retry and task.attempt < task.max_attempts:
                        task.status = TaskStatus.READY
                    else:
                        task.status = TaskStatus.FAILED
                        task.completed_at = event.occurred_at

            elif event_type == "task.superseded":
                task_id = payload.get("taskId") or event.task_id or ""
                superseded_by = payload.get("supersededBy") or payload.get("superseded_by")
                reason = payload.get("reason")
                task = graph.get_task(task_id)
                if task:
                    task.status = TaskStatus.SUPERSEDED
                    task.superseded_by = superseded_by
                    task.supersede_reason = reason
                    task.completed_at = event.occurred_at

            elif event_type == "task.cancelled":
                task_id = payload.get("taskId") or payload.get("task_id") or event.task_id or ""
                reason = payload.get("reason")
                task = graph.get_task(task_id)
                if task and task.status not in {TaskStatus.SUCCEEDED, TaskStatus.SUPERSEDED, TaskStatus.FAILED}:
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = event.occurred_at
                    if reason:
                        task.metadata["cancelled_reason"] = reason

            # --- Agent Run Events ---
            elif event_type == "agent.started":
                run_id = payload.get("runId") or event.run_id or f"run_{event.event_id}"
                task_id = payload.get("taskId") or event.task_id or ""
                actor_id = payload.get("actorId") or event.actor_id or ""
                attempt = int(payload.get("attempt", 1))

                run = AgentRun(
                    run_id=run_id,
                    job_id=job_id,
                    task_id=task_id,
                    actor_id=actor_id,
                    status=AgentRunStatus.RUNNING,
                    attempt=attempt,
                    started_at=event.occurred_at,
                    metadata=dict(payload.get("metadata") or {}),
                )
                runs_map[run_id] = run

            elif event_type == "agent.finished":
                run_id = payload.get("runId") or event.run_id
                if run_id and run_id in runs_map:
                    run = runs_map[run_id]
                    run.status = AgentRunStatus.SUCCEEDED
                    run.finished_at = event.occurred_at
                    run.exit_reason = payload.get("exitReason") or "succeeded"
                    if payload.get("artifact_refs"):
                        run.artifact_refs.extend(payload["artifact_refs"])

            elif event_type == "agent.failed":
                run_id = payload.get("runId") or event.run_id
                if run_id and run_id in runs_map:
                    run = runs_map[run_id]
                    run.status = AgentRunStatus.FAILED
                    run.finished_at = event.occurred_at
                    run.error = payload.get("error")
                    run.exit_reason = payload.get("exitReason") or "failed"

            elif event_type == "agent.timed_out":
                run_id = payload.get("runId") or event.run_id
                if run_id and run_id in runs_map:
                    run = runs_map[run_id]
                    run.status = AgentRunStatus.TIMED_OUT
                    run.finished_at = event.occurred_at
                    timeout_sec = payload.get("timeoutSeconds")
                    run.error = f"Timed out after {timeout_sec}s" if timeout_sec else "Timed out"
                    run.exit_reason = "timeout"

            elif event_type == "agent.cancelled":
                run_id = payload.get("runId") or event.run_id
                if run_id and run_id in runs_map:
                    run = runs_map[run_id]
                    run.status = AgentRunStatus.CANCELLED
                    run.finished_at = event.occurred_at
                    run.exit_reason = payload.get("reason") or "cancelled"
                    run.error = payload.get("error") or "cancelled"

            # --- Observations ---
            elif event_type == "observation.created":
                obs_id = payload.get("observation_id") or payload.get("observationId") or payload.get("id") or f"obs_{event.event_id}"
                obs = Observation(
                    observation_id=obs_id,
                    job_id=job_id,
                    kind=payload.get("kind", "discovery"),
                    content=payload.get("content", ""),
                    task_id=payload.get("task_id") or payload.get("taskId") or event.task_id,
                    actor_id=payload.get("actor_id") or payload.get("actorId") or event.actor_id,
                    confidence=float(payload.get("confidence", 1.0)),
                    created_at=payload.get("created_at") or payload.get("createdAt") or event.occurred_at,
                    metadata=dict(payload.get("metadata") or {}),
                )
                observations_map[obs.observation_id] = obs

            # --- Artifacts ---
            elif event_type == "artifact.created":
                artifacts.append(dict(payload))

            # --- Verification ---
            elif event_type == "verification.started":
                verifier_id = payload.get("verifierId") or "verifier"
                last_verification = VerificationResult(
                    status=VerificationStatus.PASSED,
                    verifier_id=verifier_id,
                    summary="Verification in progress",
                )

            elif event_type in {"verification.passed", "verification.failed"}:
                last_verification = VerificationResult.from_dict(payload)

            elif event_type == "job.waiting_for_capacity":
                job.state = JobState.WAITING_FOR_CAPACITY
                if payload.get("reason"):
                    job.metadata["waiting_for_capacity_reason"] = payload["reason"]

            elif event_type == "job.capacity_restored":
                job.state = JobState.EXECUTING
                job.metadata.pop("waiting_for_capacity_reason", None)

            # --- Replanning ---
            elif event_type == "replan.requested":
                pass

            elif event_type == "replan.completed":
                pass

            # --- Task Rerouting ---
            elif event_type == "task.rerouted":
                task_id = payload.get("taskId") or payload.get("task_id") or event.task_id or ""
                to_actor = payload.get("toActor") or payload.get("to_actor")
                from_actor = payload.get("fromActor") or payload.get("from_actor")
                reason = payload.get("reason")
                task = graph.get_task(task_id)
                if task and to_actor:
                    task.assigned_actor = to_actor
                    if task.status not in {TaskStatus.SUCCEEDED, TaskStatus.SUPERSEDED, TaskStatus.CANCELLED}:
                        task.status = TaskStatus.READY
                    if reason:
                        task.metadata["last_reroute_reason"] = reason
                    if from_actor:
                        task.metadata["previous_actor"] = from_actor

            # --- Recovery Events ---
            elif event_type == "recovery.job_rehydrated":
                job.metadata["last_rehydrated_at"] = event.occurred_at

            elif event_type == "recovery.task_reconciled":
                task_id = payload.get("taskId") or payload.get("task_id") or event.task_id or ""
                task = graph.get_task(task_id)
                if task:
                    task.status = TaskStatus.SUCCEEDED
                    task.completed_at = event.occurred_at

            elif event_type == "recovery.task_requeued":
                task_id = payload.get("taskId") or payload.get("task_id") or event.task_id or ""
                task = graph.get_task(task_id)
                if task:
                    task.status = TaskStatus.READY

        # If the job is in CANCELLED terminal state, guarantee no task or run remains RUNNING/READY/PENDING
        if job.state == JobState.CANCELLED:
            for t in graph.list_tasks():
                if t.status in {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING}:
                    t.status = TaskStatus.CANCELLED
                    t.completed_at = t.completed_at or job.completed_at
            for r in runs_map.values():
                if r.status in {AgentRunStatus.INITIALIZING, AgentRunStatus.RUNNING}:
                    r.status = AgentRunStatus.CANCELLED
                    r.finished_at = r.finished_at or job.completed_at
                    r.exit_reason = r.exit_reason or "cancelled"

        # Deterministically aggregate and deduplicate artifacts across artifact.created, tasks, and runs
        deduped_artifacts_map: Dict[str, Dict[str, Any]] = {}
        # 1. From artifact.created events
        for art in artifacts:
            art_key = str(art.get("id") or art.get("ref") or f"art_{len(deduped_artifacts_map)}")
            deduped_artifacts_map[art_key] = dict(art)
        # 2. From task completed artifact_refs
        for t in graph.list_tasks():
            for art in t.artifact_refs:
                art_key = str(art.get("id") or art.get("ref") or f"art_{len(deduped_artifacts_map)}")
                if art_key not in deduped_artifacts_map:
                    deduped_artifacts_map[art_key] = dict(art)
        # 3. From agent finished artifact_refs
        for r in runs_map.values():
            for art in r.artifact_refs:
                art_key = str(art.get("id") or art.get("ref") or f"art_{len(deduped_artifacts_map)}")
                if art_key not in deduped_artifacts_map:
                    deduped_artifacts_map[art_key] = dict(art)

        final_artifacts = list(deduped_artifacts_map.values())

        # Sort runs and observations chronologically
        runs_list = list(runs_map.values())
        runs_list.sort(key=lambda r: r.started_at or "")

        obs_list = list(observations_map.values())
        obs_list.sort(key=lambda o: o.created_at or "")

        return ReconstructedRuntimeState(
            job=job,
            graph=graph,
            runs=runs_list,
            observations=obs_list,
            artifacts=final_artifacts,
            last_verification=last_verification,
        )
