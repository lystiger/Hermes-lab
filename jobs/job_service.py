from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from capabilities.normalization import normalize_agent_id
from artifacts.artifact_registry import ArtifactRef, artifact_registry

logger = logging.getLogger("hermes.job_service")


@dataclass
class ArtifactRefDTO:
    id: str
    type: str  # "git_commit" | "run_summary" | "log" | "handoff" | "test_report" | "file"
    label: str
    ref: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobPhaseDTO:
    id: str
    name: str
    order: int
    role: str
    agentId: str
    status: str  # "PENDING" | "PREPARING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "SKIPPED" | "CANCELLED" | "SUPERSEDED" | "BLOCKED"
    attempt: int = 1
    durationMs: Optional[int] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    commitSha: Optional[str] = None
    changedFilesCount: Optional[int] = None
    detail: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    requiredCapabilities: List[str] = field(default_factory=list)


@dataclass
class JobDetailDTO:
    id: str
    sprintId: str
    title: str
    repository: str
    branch: str
    priority: str = "P1"
    status: str = "QUEUED"  # "QUEUED" | "PLANNING" | "PREPARING" | "RUNNING" | "VERIFYING" | "REPAIRING" | "COMPLETED" | "BLOCKED" | "FAILED" | "CANCELLED"
    currentPhase: Optional[str] = None
    assignedAgentIds: List[str] = field(default_factory=list)
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    progress: Optional[float] = None
    phases: List[JobPhaseDTO] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None
    artifacts: List[ArtifactRefDTO] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    retryHistory: List[Dict[str, Any]] = field(default_factory=list)
    blockedReason: Optional[Any] = None
    repairCount: int = 0
    replanCount: int = 0
    observations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sprintId": self.sprintId,
            "title": self.title,
            "repository": self.repository,
            "branch": self.branch,
            "priority": self.priority,
            "status": self.status,
            "currentPhase": self.currentPhase,
            "assignedAgentIds": self.assignedAgentIds,
            "createdAt": self.createdAt,
            "startedAt": self.startedAt,
            "completedAt": self.completedAt,
            "progress": self.progress,
            "blockedReason": self.blockedReason,
            "repairCount": self.repairCount,
            "replanCount": self.replanCount,
        }


class JobService:
    """
    Control-plane service that manages real Hermes sprint execution jobs and reactive runtime engines.
    Reconstructs historical runs from run summaries on startup and maintains live runtime state.
    """

    def __init__(self, runs_root: Optional[Path] = None, sprints_root: Optional[Path] = None, event_store: Optional[Any] = None):
        self._jobs: Dict[str, JobDetailDTO] = {}
        self._engines: Dict[str, Any] = {}
        self._store = event_store
        self.runs_root = runs_root or (Path(__file__).resolve().parent.parent / "hermes-runs")
        self.sprints_root = sprints_root or (Path(__file__).resolve().parent.parent / "sprints")
        artifact_registry.add_allowed_root(self.runs_root)
        self._recover_recent_runs()

    def set_store(self, event_store: Any) -> None:
        self._store = event_store

    def _recover_recent_runs(self) -> None:
        """Scan configured hermes-runs directory to reconstruct recent finished sprint jobs."""
        if not self.runs_root.exists():
            return

        try:
            for run_dir in sorted(self.runs_root.glob("*_*"), reverse=True)[:30]:
                if not run_dir.is_dir():
                    continue
                summary_file = run_dir / "run_summary.json"
                if summary_file.exists():
                    try:
                        with open(summary_file, "r", encoding="utf-8") as f:
                            summary = json.load(f)
                        job = self._build_job_from_run_summary(run_dir.name, summary, run_dir)
                        if job:
                            self._jobs[job.id] = job
                    except Exception as exc:
                        logger.debug("Could not recover run summary from %s: %s", summary_file, exc)
        except Exception as exc:
            logger.warning("Failed during startup run summary recovery: %s", exc)

    def _build_job_from_run_summary(
        self, run_dir_name: str, summary: Dict[str, Any], run_dir: Path
    ) -> Optional[JobDetailDTO]:
        sprint_id = summary.get("sprint_id") or run_dir_name.split("_", 2)[-1]
        job_id = f"run_{run_dir_name}" if not run_dir_name.startswith("run_") else run_dir_name

        raw_status = summary.get("status", "COMPLETED")
        if raw_status in {"READY_FOR_REVIEW", "DRY_RUN_READY"}:
            canonical_status = "COMPLETED"
        elif "FAILED" in str(raw_status).upper():
            canonical_status = "FAILED"
        else:
            canonical_status = "COMPLETED"

        phases: List[JobPhaseDTO] = []
        assigned_agents: List[str] = []
        for idx, p in enumerate(summary.get("phases", []), start=1):
            agent_id = normalize_agent_id(p.get("agent", "unknown"))
            if agent_id not in assigned_agents:
                assigned_agents.append(agent_id)
            phase_status = "SUCCEEDED" if p.get("status") == "SUCCESS" else "FAILED"
            phases.append(
                JobPhaseDTO(
                    id=f"phase-{idx}-{p.get('phase', 'step')}",
                    name=p.get("phase", f"Phase {idx}"),
                    order=idx,
                    role=p.get("role", "builder"),
                    agentId=agent_id,
                    status=phase_status,
                    commitSha=p.get("commit_sha"),
                    changedFilesCount=p.get("changed_files_count"),
                )
            )

        artifacts: List[ArtifactRefDTO] = []

        # Check for artifacts.json in run_dir
        artifacts_file = run_dir / "artifacts.json"
        if artifacts_file.exists():
            try:
                with open(artifacts_file, "r", encoding="utf-8") as af:
                    loaded = json.load(af)
                    for item in loaded:
                        art = ArtifactRef.from_dict(item)
                        artifact_registry.register(art)
                        artifacts.append(
                            ArtifactRefDTO(
                                id=art.id,
                                type=art.type,
                                label=art.label,
                                ref=art.ref,
                                metadata=art.metadata,
                            )
                        )
            except Exception as e:
                logger.debug("Failed loading artifacts.json from %s: %s", artifacts_file, e)

        # Fallback discovery if artifacts.json not present
        if not artifacts:
            commit_sha = summary.get("integration_commit")
            if commit_sha:
                art = ArtifactRefDTO(
                    id="art_commit",
                    type="git_commit",
                    label=f"Integration Commit ({commit_sha[:7]})",
                    ref=commit_sha,
                )
                artifacts.append(art)
                artifact_registry.register(ArtifactRef(id=art.id, type=art.type, label=art.label, ref=art.ref, jobId=job_id))

            summary_path = run_dir / "run_summary.json"
            if summary_path.exists():
                art = ArtifactRefDTO(
                    id="art_summary",
                    type="run_summary",
                    label="Run Summary Report",
                    ref=str(summary_path),
                )
                artifacts.append(art)
                artifact_registry.register(ArtifactRef(id=art.id, type=art.type, label=art.label, ref=art.ref, jobId=job_id))

            log_path = run_dir / "runner.log"
            if log_path.exists():
                art = ArtifactRefDTO(
                    id="art_log",
                    type="log",
                    label="Runner Execution Log",
                    ref=str(log_path),
                )
                artifacts.append(art)
                artifact_registry.register(ArtifactRef(id=art.id, type=art.type, label=art.label, ref=art.ref, jobId=job_id))

            # Scan handoffs directory
            handoffs_dir = run_dir / "handoffs"
            if handoffs_dir.is_dir():
                for hf in sorted(handoffs_dir.glob("*.md")):
                    art = ArtifactRefDTO(
                        id=f"art_handoff_{hf.stem}",
                        type="handoff",
                        label=f"Handoff ({hf.name})",
                        ref=str(hf),
                    )
                    artifacts.append(art)
                    artifact_registry.register(ArtifactRef(id=art.id, type=art.type, label=art.label, ref=art.ref, jobId=job_id))

        if canonical_status == "COMPLETED":
            progress = 1.0
        elif phases:
            progress = round(len([p for p in phases if p.status == "SUCCEEDED"]) / len(phases), 2)
        else:
            progress = 0.0

        repo_name = summary.get("target_repo") or sprint_id
        target_branch = summary.get("target_branch") or f"hermes/{sprint_id}/integration"

        return JobDetailDTO(
            id=job_id,
            sprintId=sprint_id,
            title=f"Hermes Sprint {sprint_id}",
            repository=repo_name,
            branch=target_branch,
            priority="P1",
            status=canonical_status,
            currentPhase=phases[-1].name if phases else None,
            assignedAgentIds=assigned_agents,
            createdAt=summary.get("start_time", datetime.now(timezone.utc).isoformat()),
            startedAt=summary.get("start_time"),
            completedAt=summary.get("end_time"),
            progress=progress,
            phases=phases,
            verification={"status": summary.get("verification_status", "PASSED"), "results": summary.get("verification_results", [])},
            artifacts=artifacts,
            errors=summary.get("errors", []),
        )

    def register_job(self, job: JobDetailDTO) -> None:
        self._jobs[job.id] = job

    def register_engine(self, engine: Any) -> None:
        """Registers an active ReactiveJobEngine and synchronizes its JobDetailDTO."""
        job_id = engine.job.job_id
        self._engines[job_id] = engine

        job_dto = self.get_job(job_id)
        if not job_dto:
            job_dto = JobDetailDTO(
                id=job_id,
                sprintId=job_id,
                title=engine.job.title or engine.job.goal,
                repository=engine.job.repository or "Local Workspace",
                branch=engine.job.branch or "main",
                priority=engine.job.priority,
                status=engine.job.state.value.upper(),
                createdAt=engine.job.created_at,
                startedAt=engine.job.started_at,
                completedAt=engine.job.completed_at,
                blockedReason=engine.job.blocked_reason,
                repairCount=engine.job.repair_count,
                replanCount=engine.job.replan_count,
            )
            self.register_job(job_dto)
        else:
            job_dto.status = engine.job.state.value.upper()
            job_dto.blockedReason = engine.job.blocked_reason
            job_dto.repairCount = engine.job.repair_count
            job_dto.replanCount = engine.job.replan_count

    def get_engine(self, job_id: str) -> Optional[Any]:
        return self._engines.get(job_id)

    def get_job(self, job_id: str) -> Optional[JobDetailDTO]:
        job = self._jobs.get(job_id)
        if not job:
            return None

        # Synchronize live engine state if present
        engine = self._engines.get(job_id)
        if engine:
            job.status = engine.job.state.value.upper()
            job.startedAt = engine.job.started_at or job.startedAt
            job.completedAt = engine.job.completed_at or job.completedAt
            job.blockedReason = engine.job.blocked_reason
            job.repairCount = engine.job.repair_count
            job.replanCount = engine.job.replan_count

            # Map tasks
            task_nodes = engine.graph.list_tasks()
            job.tasks = [t.to_dict() for t in task_nodes]
            if task_nodes:
                phases = []
                for idx, t in enumerate(task_nodes, start=1):
                    phases.append(
                        JobPhaseDTO(
                            id=t.task_id,
                            name=t.description,
                            order=idx,
                            role=t.assigned_actor or "builder",
                            agentId=t.assigned_actor or "unknown",
                            status=t.status.value,
                            attempt=t.attempt,
                            startedAt=t.started_at,
                            completedAt=t.completed_at,
                            dependencies=t.dependencies,
                            requiredCapabilities=t.required_capabilities,
                        )
                    )
                job.phases = phases
                succeeded_count = len([t for t in task_nodes if t.status.value == "SUCCEEDED"])
                job.progress = round(succeeded_count / max(len(task_nodes), 1), 2)
                if job.status == "COMPLETED":
                    job.progress = 1.0

        return job

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        # Refresh registered engines
        for jid in list(self._engines.keys()):
            self.get_job(jid)

        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status.upper() == status.upper()]
        jobs.sort(key=lambda j: j.createdAt or j.startedAt or "", reverse=True)
        return [j.to_summary_dict() for j in jobs[:limit]]

    def get_job_tasks(self, job_id: str) -> List[Dict[str, Any]]:
        engine = self._engines.get(job_id)
        if engine:
            return [t.to_dict() for t in engine.graph.list_tasks()]
        job = self.get_job(job_id)
        if job and job.tasks:
            return job.tasks
        return []

    def get_job_runs(self, job_id: str) -> List[Dict[str, Any]]:
        engine = self._engines.get(job_id)
        if engine:
            runs = engine.execution_manager.list_runs_for_job(job_id)
            return [r.to_dict() for r in runs]
        return []

    def get_job_observations(self, job_id: str) -> List[Dict[str, Any]]:
        engine = self._engines.get(job_id)
        if engine:
            obs = engine.observation_registry.list_for_job(job_id)
            return [o.to_dict() for o in obs]
        job = self.get_job(job_id)
        if job and job.observations:
            return job.observations
        return []

    async def get_job_async(self, job_id: str) -> Optional[JobDetailDTO]:
        # 1. Check in-memory state first
        job = self.get_job(job_id)
        if job:
            return job

        # 2. Reconstruct from durable event store if available
        from runtime.storage.config import get_global_event_store
        store = self._store or get_global_event_store()
        if store:
            try:
                events = await store.list_events(job_id)
                if events:
                    from runtime.storage.projector import RuntimeStateProjector
                    state = RuntimeStateProjector.project(events)
                    task_nodes = state.graph.list_tasks()
                    phases = []
                    for idx, t in enumerate(task_nodes, start=1):
                        phases.append(
                            JobPhaseDTO(
                                id=t.task_id,
                                name=t.description,
                                order=idx,
                                role=t.assigned_actor or "builder",
                                agentId=t.assigned_actor or "unknown",
                                status=t.status.value,
                                attempt=t.attempt,
                                startedAt=t.started_at,
                                completedAt=t.completed_at,
                                dependencies=t.dependencies,
                                requiredCapabilities=t.required_capabilities,
                            )
                        )
                    succeeded_count = len([t for t in task_nodes if t.status.value == "SUCCEEDED"])
                    progress = 1.0 if state.job.state.value.upper() == "COMPLETED" else round(succeeded_count / max(len(task_nodes), 1), 2)
                    job_dto = JobDetailDTO(
                        id=job_id,
                        sprintId=job_id,
                        title=state.job.title or state.job.goal,
                        repository=state.job.repository or "—",
                        branch=state.job.branch or "main",
                        priority=state.job.priority,
                        status=state.job.state.value.upper(),
                        createdAt=state.job.created_at,
                        startedAt=state.job.started_at,
                        completedAt=state.job.completed_at,
                        progress=progress,
                        phases=phases,
                        tasks=[t.to_dict() for t in task_nodes],
                        blockedReason=state.job.blocked_reason,
                        repairCount=state.job.repair_count,
                        replanCount=state.job.replan_count,
                        observations=[o.to_dict() for o in state.observations],
                    )
                    self._jobs[job_id] = job_dto
                    return job_dto
            except Exception as exc:
                logger.warning("Error reconstructing job %s from event store: %s", job_id, exc)

        return None

    async def get_job_tasks_async(self, job_id: str) -> List[Dict[str, Any]]:
        tasks = self.get_job_tasks(job_id)
        if tasks:
            return tasks
        job = await self.get_job_async(job_id)
        return job.tasks if job else []

    async def get_job_runs_async(self, job_id: str) -> List[Dict[str, Any]]:
        runs = self.get_job_runs(job_id)
        if runs:
            return runs
        from runtime.storage.config import get_global_event_store
        store = self._store or get_global_event_store()
        if store:
            try:
                events = await store.list_events(job_id)
                if events:
                    from runtime.storage.projector import RuntimeStateProjector
                    state = RuntimeStateProjector.project(events)
                    return [r.to_dict() for r in state.runs]
            except Exception as exc:
                logger.warning("Error reconstructing runs for job %s: %s", job_id, exc)
        return []

    async def get_job_observations_async(self, job_id: str) -> List[Dict[str, Any]]:
        obs = self.get_job_observations(job_id)
        if obs:
            return obs
        from runtime.storage.config import get_global_event_store
        store = self._store or get_global_event_store()
        if store:
            try:
                events = await store.list_events(job_id)
                if events:
                    from runtime.storage.projector import RuntimeStateProjector
                    state = RuntimeStateProjector.project(events)
                    return [o.to_dict() for o in state.observations]
            except Exception as exc:
                logger.warning("Error reconstructing observations for job %s: %s", job_id, exc)
        return []


job_service = JobService()
