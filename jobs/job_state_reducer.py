from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from jobs.job_service import JobDetailDTO, JobPhaseDTO, ArtifactRefDTO, job_service
from capabilities.normalization import normalize_agent_id

logger = logging.getLogger("hermes.job_state_reducer")


class JobStateReducer:
    """
    Deterministic state reducer that projects incoming runtime events onto canonical Job domain objects.
    Supports both legacy runner phase telemetry and reactive runtime graph events.
    """

    def __init__(self, service=None):
        self._service = service or job_service

    def bind_service(self, service):
        self._service = service

    def apply(
        self,
        kind: str,
        detail: str,
        job_id: Optional[str] = None,
        source_id: Optional[str] = None,
        duration: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        meta = metadata or {}
        jid = job_id or meta.get("jobId") or meta.get("job_id")
        if not jid:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        job = self._service.get_job(jid)

        if kind == "job.created":
            sprint_id = meta.get("sprintId") or meta.get("sprint_id") or jid
            title = meta.get("title") or meta.get("goal") or f"Hermes Sprint {sprint_id}"
            repository = meta.get("repository") or meta.get("target_repo") or "Target Repository"
            branch = meta.get("branch") or meta.get("target_branch") or f"hermes/{sprint_id}/integration"
            priority = meta.get("priority", "P1")

            phases_meta = meta.get("phases", [])
            phases: List[JobPhaseDTO] = []
            assigned_agents: List[str] = []

            for idx, pm in enumerate(phases_meta, start=1):
                agent_id = normalize_agent_id(pm.get("agent") or pm.get("agentId") or "unknown")
                if agent_id not in assigned_agents:
                    assigned_agents.append(agent_id)
                phases.append(
                    JobPhaseDTO(
                        id=f"phase-{idx}-{pm.get('name', pm.get('role', 'step'))}",
                        name=pm.get("name", f"Phase {idx}"),
                        order=idx,
                        role=pm.get("role", "builder"),
                        agentId=agent_id,
                        status="PENDING",
                    )
                )

            new_job = JobDetailDTO(
                id=jid,
                sprintId=sprint_id,
                title=title,
                repository=repository,
                branch=branch,
                priority=priority,
                status="PREPARING",
                assignedAgentIds=assigned_agents or ["gemini", "claude", "codex"],
                createdAt=now_iso,
                startedAt=now_iso,
                phases=phases,
            )
            self._service.register_job(new_job)

        elif kind == "job.state_changed":
            new_state = meta.get("new_state", "").upper()
            if not job:
                job = JobDetailDTO(
                    id=jid,
                    sprintId=jid,
                    title=f"Hermes Sprint {jid}",
                    repository="Managed Repo",
                    branch=f"hermes/{jid}",
                    status=new_state or "RUNNING",
                    createdAt=now_iso,
                    startedAt=now_iso,
                )
                self._service.register_job(job)
            else:
                if new_state:
                    job.status = new_state
                if meta.get("reason"):
                    if new_state == "BLOCKED":
                        job.blockedReason = meta.get("reason")
                    elif new_state == "FAILED":
                        job.errors.append({"error": str(meta.get("reason"))})

        elif kind == "job.started":
            if not job:
                sprint_id = meta.get("sprintId") or meta.get("sprint_id") or jid
                job = JobDetailDTO(
                    id=jid,
                    sprintId=sprint_id,
                    title=meta.get("title") or f"Hermes Sprint {sprint_id}",
                    repository=meta.get("repository", "Hermes Managed Repo"),
                    branch=meta.get("branch", f"hermes/{sprint_id}/integration"),
                    status="RUNNING",
                    createdAt=now_iso,
                    startedAt=now_iso,
                )
                self._service.register_job(job)
            else:
                job.status = "RUNNING"
                job.startedAt = job.startedAt or now_iso

        elif kind == "task.created":
            if job:
                task_id = meta.get("taskId") or meta.get("task_id") or detail
                desc = meta.get("description") or detail
                existing_phase = next((p for p in job.phases if p.id == task_id or p.name == desc), None)
                if not existing_phase:
                    idx = len(job.phases) + 1
                    job.phases.append(
                        JobPhaseDTO(
                            id=task_id,
                            name=desc,
                            order=idx,
                            role="builder",
                            agentId="unknown",
                            status="PENDING",
                            dependencies=meta.get("dependencies", []),
                            requiredCapabilities=meta.get("requiredCapabilities", []),
                        )
                    )

        elif kind == "task.assigned":
            if job:
                task_id = meta.get("taskId") or meta.get("task_id")
                actor_id = normalize_agent_id(meta.get("assignedActor") or meta.get("assigned_actor") or source_id or "unknown")
                if actor_id not in job.assignedAgentIds:
                    job.assignedAgentIds.append(actor_id)
                target_phase = next((p for p in job.phases if p.id == task_id), None)
                if target_phase:
                    target_phase.agentId = actor_id
                    target_phase.role = actor_id

        elif kind == "task.started" or kind == "phase.started":
            if not job:
                job = JobDetailDTO(
                    id=jid,
                    sprintId=jid,
                    title=f"Hermes Sprint {jid}",
                    repository="Target Repo",
                    branch=f"hermes/{jid}",
                    status="RUNNING",
                    createdAt=now_iso,
                    startedAt=now_iso,
                )
                self._service.register_job(job)

            phase_name = meta.get("phase") or meta.get("name") or meta.get("taskId") or detail
            phase_role = meta.get("role", "builder")
            agent_id = normalize_agent_id(meta.get("agent") or meta.get("actorId") or source_id or "unknown")

            if agent_id not in job.assignedAgentIds:
                job.assignedAgentIds.append(agent_id)

            target_phase = next((p for p in job.phases if p.id == phase_name or p.name == phase_name or p.role == phase_role), None)
            if not target_phase:
                idx = len(job.phases) + 1
                target_phase = JobPhaseDTO(
                    id=f"phase-{idx}-{phase_name}",
                    name=phase_name,
                    order=idx,
                    role=phase_role,
                    agentId=agent_id,
                    status="RUNNING",
                    startedAt=now_iso,
                )
                job.phases.append(target_phase)
            else:
                target_phase.status = "RUNNING"
                target_phase.startedAt = target_phase.startedAt or now_iso
                if agent_id != "unknown":
                    target_phase.agentId = agent_id

            job.status = "RUNNING"
            job.currentPhase = phase_name
            total_phases = max(len(job.phases), 1)
            job.progress = round(target_phase.order / (total_phases + 1), 2)

        elif kind == "task.completed" or kind == "phase.completed":
            if job:
                phase_name = meta.get("phase") or meta.get("name") or meta.get("taskId") or detail
                target_phase = next((p for p in job.phases if p.id == phase_name or p.name == phase_name or phase_name in p.name), None)
                if target_phase:
                    target_phase.status = "SUCCEEDED"
                    target_phase.completedAt = now_iso
                    if meta.get("commitSha") or meta.get("commit_sha"):
                        target_phase.commitSha = meta.get("commitSha") or meta.get("commit_sha")
                    if meta.get("changedFilesCount") is not None:
                        target_phase.changedFilesCount = meta.get("changedFilesCount")
                    if meta.get("durationMs"):
                        target_phase.durationMs = int(meta["durationMs"])
                succeeded = len([p for p in job.phases if p.status == "SUCCEEDED"])
                job.progress = round(succeeded / max(len(job.phases), 1), 2)

        elif kind == "task.failed" or kind == "phase.failed":
            if job:
                phase_name = meta.get("phase") or meta.get("name") or meta.get("taskId") or detail
                target_phase = next((p for p in job.phases if p.id == phase_name or p.name == phase_name or phase_name in p.name), None)
                if target_phase:
                    target_phase.status = "FAILED"
                    target_phase.completedAt = now_iso
                if meta.get("error"):
                    job.errors.append({"phase": phase_name, "error": str(meta["error"])})

        elif kind == "task.superseded":
            if job:
                task_id = meta.get("taskId") or meta.get("task_id")
                target_phase = next((p for p in job.phases if p.id == task_id), None)
                if target_phase:
                    target_phase.status = "SUPERSEDED"
                    target_phase.completedAt = now_iso

        elif kind == "observation.created":
            if job:
                job.observations.append(dict(meta))

        elif kind == "verification.passed":
            if job:
                job.verification = {"status": "PASSED", "summary": detail, "results": meta}

        elif kind == "verification.failed":
            if job:
                job.verification = {"status": "FAILED", "summary": detail, "results": meta}

        elif kind == "job.completed":
            if job:
                job.status = "COMPLETED"
                job.completedAt = now_iso
                job.progress = 1.0
                commit_sha = meta.get("integrationCommit") or meta.get("commit_sha")
                if commit_sha:
                    job.artifacts.append(
                        ArtifactRefDTO(
                            id=f"art_commit_{commit_sha[:7]}",
                            type="git_commit",
                            label=f"Integration Commit ({commit_sha[:7]})",
                            ref=commit_sha,
                        )
                    )

        elif kind == "job.blocked":
            if job:
                job.status = "BLOCKED"
                job.completedAt = now_iso
                job.blockedReason = meta.get("reason") or detail

        elif kind == "job.failed":
            if job:
                job.status = "FAILED"
                job.completedAt = now_iso
                for p in job.phases:
                    if p.status == "RUNNING":
                        p.status = "FAILED"
                        p.completedAt = now_iso
                if meta.get("error"):
                    job.errors.append({"error": str(meta.get("error"))})

        elif kind == "job.cancelled":
            if job:
                job.status = "CANCELLED"
                job.completedAt = now_iso
                for p in job.phases:
                    if p.status in {"PENDING", "PREPARING", "RUNNING"}:
                        p.status = "CANCELLED"


job_state_reducer = JobStateReducer()
