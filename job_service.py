from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from normalization import normalize_agent_id

logger = logging.getLogger("hermes.job_service")


@dataclass
class ArtifactRefDTO:
    id: str
    type: str  # "git_commit" | "run_summary" | "log" | "handoff" | "test_report" | "file"
    label: str
    ref: str


@dataclass
class JobPhaseDTO:
    id: str
    name: str
    order: int
    role: str
    agentId: str
    status: str  # "PENDING" | "PREPARING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "SKIPPED" | "CANCELLED"
    attempt: int = 1
    durationMs: Optional[int] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    commitSha: Optional[str] = None
    changedFilesCount: Optional[int] = None
    detail: Optional[str] = None


@dataclass
class JobDetailDTO:
    id: str
    sprintId: str
    title: str
    repository: str
    branch: str
    priority: str = "P1"
    status: str = "QUEUED"  # "QUEUED" | "PREPARING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED"
    currentPhase: Optional[str] = None
    assignedAgentIds: List[str] = field(default_factory=list)
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    progress: Optional[float] = None
    phases: List[JobPhaseDTO] = field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None
    artifacts: List[ArtifactRefDTO] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    retryHistory: List[Dict[str, Any]] = field(default_factory=list)

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
        }


class JobService:
    """
    Control-plane service that manages real Hermes sprint execution jobs.
    Reconstructs historical runs from run summaries on startup and maintains live runtime state.
    """

    def __init__(self, runs_root: Optional[Path] = None, sprints_root: Optional[Path] = None):
        self._jobs: Dict[str, JobDetailDTO] = {}
        self.runs_root = runs_root or (Path(__file__).resolve().parent.parent / "hermes-runs")
        self.sprints_root = sprints_root or (Path(__file__).resolve().parent / "sprints")
        self._recover_recent_runs()

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
        commit_sha = summary.get("integration_commit")
        if commit_sha:
            artifacts.append(
                ArtifactRefDTO(
                    id="art_commit",
                    type="git_commit",
                    label=f"Integration Commit ({commit_sha[:7]})",
                    ref=commit_sha,
                )
            )
        summary_path = run_dir / "run_summary.json"
        if summary_path.exists():
            artifacts.append(
                ArtifactRefDTO(
                    id="art_summary",
                    type="run_summary",
                    label="Run Summary Report",
                    ref=str(summary_path),
                )
            )
        log_path = run_dir / "runner.log"
        if log_path.exists():
            artifacts.append(
                ArtifactRefDTO(
                    id="art_log",
                    type="log",
                    label="Runner Execution Log",
                    ref=str(log_path),
                )
            )

        return JobDetailDTO(
            id=job_id,
            sprintId=sprint_id,
            title=f"Hermes Sprint {sprint_id}",
            repository="Hermes Managed Repo",
            branch=f"hermes/{sprint_id}/integration",
            priority="P1",
            status=canonical_status,
            currentPhase=phases[-1].name if phases else None,
            assignedAgentIds=assigned_agents or ["gemini", "claude", "codex"],
            createdAt=summary.get("start_time", datetime.now(timezone.utc).isoformat()),
            startedAt=summary.get("start_time"),
            completedAt=summary.get("end_time"),
            progress=1.0 if canonical_status == "COMPLETED" else 0.8,
            phases=phases,
            verification={"status": summary.get("verification_status", "PASSED"), "results": summary.get("verification_results", [])},
            artifacts=artifacts,
            errors=summary.get("errors", []),
        )

    def register_job(self, job: JobDetailDTO) -> None:
        self._jobs[job.id] = job

    def get_job(self, job_id: str) -> Optional[JobDetailDTO]:
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status.upper() == status.upper()]
        # Sort newest first by createdAt or startedAt
        jobs.sort(key=lambda j: j.createdAt or j.startedAt or "", reverse=True)
        return [j.to_summary_dict() for j in jobs[:limit]]


job_service = JobService()
