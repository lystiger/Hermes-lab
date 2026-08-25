from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

from runtime.job_state import JobRecord, JobState, TERMINAL_JOB_STATES
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.execution import ExecutionManager, AgentRun, AgentRunStatus
from runtime.observations import Observation
from runtime.verification import VerificationResult
from runtime.limits import RuntimeLimits
from runtime.events import RuntimeEventBridge
from runtime.storage.event_store import RuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector, ReconstructedRuntimeState
from runtime.storage.schema_registry import StoredRuntimeEvent
from runtime.lease import JobLeaseStore, InMemoryJobLeaseStore
from runtime.engine import ReactiveJobEngine
from capabilities.capabilities import CapabilityRegistry, default_capability_registry

logger = logging.getLogger("hermes.runtime.recovery")


class RecoveryDisposition(str, Enum):
    """Disposition decision for a recovered task during runtime rehydration."""
    KEEP_SUCCEEDED = "keep_succeeded"
    RECONCILE_INTERRUPTED = "reconcile_interrupted"
    RETRY_ELIGIBLE = "retry_eligible"
    BLOCK_FATAL = "block_fatal"


@dataclass
class RecoveryMetrics:
    """Measured RTO (Recovery Time Objective) and recovery execution telemetry."""
    job_id: str
    recovery_id: str
    recovery_started_at: str
    failure_detected_at: Optional[str] = None
    execution_resumed_at: Optional[str] = None
    recovery_completed_at: Optional[str] = None
    rto_seconds: float = 0.0
    reconciled_tasks: List[str] = field(default_factory=list)
    requeued_tasks: List[str] = field(default_factory=list)
    preserved_tasks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InterruptedTaskReconciler:
    """
    Inspects execution evidence (Git worktrees, commits, artifacts, runs)
    to classify whether an interrupted RUNNING task can be durably reconciled
    or safely requeued without repeating model work.
    """

    @classmethod
    def evaluate(
        cls,
        task: TaskNode,
        runs: List[AgentRun],
        artifacts: List[Dict[str, Any]],
        events: List[StoredRuntimeEvent],
        repo_path: Optional[Union[str, Path]] = None,
        target_branch: Optional[str] = None,
        job_created_at: Optional[str] = None,
        integration_baseline_sha: Optional[str] = None,
    ) -> Tuple[RecoveryDisposition, Dict[str, Any]]:
        task_runs = [r for r in runs if r.task_id == task.task_id]

        # Check if any run or metadata indicates a completed commit or integration merge
        evidence = {}
        for r in task_runs:
            if r.artifact_refs:
                evidence["artifact_refs"] = list(r.artifact_refs)
            if isinstance(r.metadata, dict):
                if r.metadata.get("commit_sha"):
                    evidence["commit_sha"] = r.metadata["commit_sha"]
                if r.metadata.get("integrated"):
                    evidence["integrated"] = True

        # Check task metadata
        if isinstance(task.metadata, dict):
            if task.metadata.get("commit_sha"):
                evidence["commit_sha"] = task.metadata["commit_sha"]
            if task.metadata.get("integrated"):
                evidence["integrated"] = True
            if task.metadata.get("commit_hash"):
                evidence["commit_sha"] = task.metadata["commit_hash"]
            if task.metadata.get("merged"):
                evidence["integrated"] = True

        # Real Git inspection if repository path is available
        if repo_path and not evidence.get("integrated"):
            try:
                repo_p = Path(repo_path)
                if repo_p.exists() and (repo_p / ".git").exists():
                    import subprocess
                    phase_id = task.task_id
                    expected_msg = (task.metadata or {}).get("commit_message") or f"feat({phase_id})"
                    branch = target_branch or (task.metadata or {}).get("base_branch") or "main"

                    # Format with commit hash, commit ISO timestamp, and commit subject
                    res = subprocess.run(
                        ["git", "log", "-n", "10", f"--grep={expected_msg}", "--format=%H|%cI|%s", branch],
                        cwd=str(repo_p),
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        # Temporal scoping: commit must have occurred during this job/task lifecycle
                        cutoff_iso = task.started_at or job_created_at
                        cutoff_dt = None
                        if cutoff_iso:
                            try:
                                cutoff_dt = datetime.fromisoformat(cutoff_iso)
                                if cutoff_dt.tzinfo is None:
                                    cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
                            except Exception:
                                pass

                        for line in res.stdout.strip().split("\n"):
                            parts = line.split("|", 2)
                            if len(parts) >= 3:
                                sha, c_iso, msg = parts[0], parts[1], parts[2]
                                is_in_scope = True
                                if cutoff_dt:
                                    try:
                                        c_dt = datetime.fromisoformat(c_iso)
                                        if c_dt.tzinfo is None:
                                            c_dt = c_dt.replace(tzinfo=timezone.utc)
                                        if c_dt < (cutoff_dt - timedelta(seconds=60)):
                                            is_in_scope = False
                                    except Exception:
                                        pass
                                if is_in_scope and integration_baseline_sha:
                                    if sha == integration_baseline_sha:
                                        is_in_scope = False
                                    else:
                                        res_anc = subprocess.run(
                                            ["git", "merge-base", "--is-ancestor", integration_baseline_sha, sha],
                                            cwd=str(repo_p),
                                            capture_output=True,
                                            check=False,
                                        )
                                        if res_anc.returncode != 0:
                                            is_in_scope = False
                                if is_in_scope:
                                    evidence["commit_sha"] = sha
                                    evidence["integrated"] = True
                                    evidence["git_log_matched"] = msg
                                    break
            except Exception as e:
                logger.debug("Git inspection error during task %s reconciliation: %s", task.task_id, e)

        # If substantial side effects exist (e.g. integrated commit or verified artifacts)
        if evidence.get("integrated") or (evidence.get("commit_sha") and (evidence.get("artifact_refs") or evidence.get("git_log_matched"))):
            return RecoveryDisposition.RECONCILE_INTERRUPTED, evidence

        # Otherwise no irreversible side-effect acknowledged -> safely requeue
        return RecoveryDisposition.RETRY_ELIGIBLE, {"reason": "no_durable_side_effect"}


class RecoveryManager:
    """
    Authoritative recovery and rehydration coordinator.
    Reconstructs state from the canonical event store, verifies lease exclusivity,
    reconciles interrupted tasks, and rehydrates an executable ReactiveJobEngine.
    """

    def __init__(
        self,
        event_store: RuntimeEventStore,
        lease_store: Optional[JobLeaseStore] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        limits: Optional[RuntimeLimits] = None,
    ):
        self.event_store = event_store
        self.lease_store = lease_store or InMemoryJobLeaseStore()
        self.capability_registry = capability_registry or default_capability_registry
        self.limits = limits or RuntimeLimits()

    async def recover_and_rehydrate(
        self,
        job_id: str,
        owner_id: Optional[str] = None,
        detected_interruption_at: Optional[str] = None,
        event_bridge: Optional[RuntimeEventBridge] = None,
    ) -> Tuple[ReactiveJobEngine, RecoveryMetrics]:
        recovery_start = datetime.now(timezone.utc)
        recovery_id = f"rec_{uuid.uuid4().hex[:8]}"
        owner = owner_id or f"hermes-node-{uuid.uuid4().hex[:8]}"

        # 1. Fetch events from canonical store
        events = await self.event_store.list_events(job_id)
        if not events:
            raise ValueError(f"No events found for job '{job_id}' in event store")

        # 2. Reconstruct state deterministically
        projected = RuntimeStateProjector.project(events)

        # 3. Invariant: Completed or Cancelled jobs must NEVER resume
        if projected.job.is_terminal:
            raise ValueError(f"Cannot resume terminal job '{job_id}' (state: {projected.job.state.value})")

        # 4. Invariant: Single-Active-Executor Job Lease
        lease_acquired = await self.lease_store.acquire_lease(job_id=job_id, owner_id=owner, duration_seconds=60.0)
        if not lease_acquired:
            raise RuntimeError(f"Cannot resume job '{job_id}': active lease held by another executor")

        # 5. Initialize event bridge
        bridge = event_bridge or RuntimeEventBridge(event_store=self.event_store)

        # Emit recovery started
        await bridge.emit_recovery_started(
            job_id=job_id,
            recovery_id=recovery_id,
            detected_interruption_at=detected_interruption_at,
        )

        # 6. Reconcile tasks and graph
        reconciled_tasks: List[str] = []
        requeued_tasks: List[str] = []
        preserved_tasks: List[str] = []

        for task in projected.graph.list_tasks():
            if task.status == TaskStatus.SUCCEEDED:
                preserved_tasks.append(task.task_id)
            elif task.status in (TaskStatus.PENDING, TaskStatus.READY):
                preserved_tasks.append(task.task_id)
            elif task.status == TaskStatus.RUNNING:
                disposition, evidence = InterruptedTaskReconciler.evaluate(
                    task=task,
                    runs=projected.runs,
                    artifacts=projected.artifacts,
                    events=events,
                    repo_path=projected.job.repository,
                    target_branch=projected.job.branch,
                    job_created_at=projected.job.created_at,
                    integration_baseline_sha=(projected.job.metadata or {}).get("integration_baseline_sha"),
                )
                if disposition == RecoveryDisposition.RECONCILE_INTERRUPTED:
                    task.status = TaskStatus.SUCCEEDED
                    task.completed_at = recovery_start.isoformat()
                    if evidence.get("artifact_refs"):
                        for art in evidence["artifact_refs"]:
                            if art not in task.artifact_refs:
                                task.artifact_refs.append(art)
                    reconciled_tasks.append(task.task_id)
                    await bridge.emit_recovery_task_reconciled(task_id=task.task_id, job_id=job_id, evidence=evidence)
                else:
                    task.status = TaskStatus.READY
                    requeued_tasks.append(task.task_id)
                    await bridge.emit_recovery_task_requeued(task_id=task.task_id, job_id=job_id, reason="Interrupted run safely requeued")
            elif task.status == TaskStatus.FAILED:
                if task.attempt < task.max_attempts:
                    task.status = TaskStatus.READY
                    requeued_tasks.append(task.task_id)
                else:
                    preserved_tasks.append(task.task_id)

        # Mark any interrupted in-memory AgentRuns as CANCELLED
        for run in projected.runs:
            if run.status in (AgentRunStatus.RUNNING, AgentRunStatus.INITIALIZING):
                run.status = AgentRunStatus.CANCELLED
                run.finished_at = recovery_start.isoformat()
                run.exit_reason = "process_interrupted"

        # 7. Rehydrate authoritatively into ReactiveJobEngine
        engine = ReactiveJobEngine(
            job_id=job_id,
            goal=projected.job.goal,
            title=projected.job.title,
            priority=projected.job.priority,
            repository=projected.job.repository,
            branch=projected.job.branch,
            capability_registry=self.capability_registry,
            limits=self.limits,
            event_bridge=bridge,
        )

        # Rehydrate internal engine structures
        engine.job = projected.job
        engine.graph = projected.graph
        for run in projected.runs:
            engine.execution_manager._runs[run.run_id] = run
        for obs in projected.observations:
            engine.observation_registry.register(obs)
        engine._artifacts = list(projected.artifacts)
        engine._last_verification_result = projected.last_verification
        engine._job_created_emitted = True

        # If job was in WAITING_FOR_CAPACITY or EXECUTING, maintain valid state
        if engine.job.state in (JobState.PLANNING, JobState.EXECUTING, JobState.WAITING_FOR_CAPACITY, JobState.REPAIRING, JobState.VERIFYING):
            pass

        # 8. Emit rehydrated & completed events
        await bridge.emit_recovery_job_rehydrated(
            job_id=job_id,
            tasks_count=len(projected.graph.list_tasks()),
            runs_count=len(projected.runs),
        )

        recovery_end = datetime.now(timezone.utc)
        rto_seconds = (recovery_end - recovery_start).total_seconds()
        if detected_interruption_at:
            try:
                dt_interrupted = datetime.fromisoformat(detected_interruption_at)
                rto_seconds = (recovery_end - dt_interrupted).total_seconds()
            except Exception:
                pass

        metrics = RecoveryMetrics(
            job_id=job_id,
            recovery_id=recovery_id,
            recovery_started_at=recovery_start.isoformat(),
            failure_detected_at=detected_interruption_at,
            execution_resumed_at=recovery_end.isoformat(),
            recovery_completed_at=recovery_end.isoformat(),
            rto_seconds=rto_seconds,
            reconciled_tasks=reconciled_tasks,
            requeued_tasks=requeued_tasks,
            preserved_tasks=preserved_tasks,
        )

        await bridge.emit_recovery_completed(
            job_id=job_id,
            rto_seconds=rto_seconds,
            summary=metrics.to_dict(),
        )

        return engine, metrics
