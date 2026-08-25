from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from runtime.task_graph import TaskNode, TaskStatus
from runtime.limits import RuntimeLimits
from runtime.planning.reconnaissance import RepositoryEvidence


@dataclass
class PlannedTask:
    """A structured, evidence-grounded task produced by the initial planner."""
    task_id: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    expected_artifacts: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    verification: List[str] = field(default_factory=list)
    risk: str = "medium"
    evidence_refs: List[str] = field(default_factory=list)
    evidence_status: str = "existing"  # "existing" or "new_component"
    reason: str = ""
    uncertainty: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.risk = str(self.risk).lower()
        if self.risk not in ("low", "medium", "high"):
            self.risk = "medium"
        if not self.evidence_status:
            self.evidence_status = "existing"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlannedTask":
        return cls(
            task_id=str(data.get("task_id") or data.get("taskId") or data.get("id") or ""),
            description=str(data.get("description") or data.get("name") or ""),
            dependencies=list(data.get("dependencies") or []),
            required_capabilities=list(data.get("required_capabilities") or data.get("requiredCapabilities") or []),
            expected_artifacts=list(data.get("expected_artifacts") or data.get("expectedArtifacts") or []),
            acceptance_criteria=list(data.get("acceptance_criteria") or data.get("acceptanceCriteria") or []),
            verification=list(data.get("verification") or []),
            risk=str(data.get("risk", "medium")),
            evidence_refs=list(data.get("evidence_refs") or data.get("evidenceRefs") or []),
            evidence_status=str(data.get("evidence_status") or data.get("evidenceStatus") or "existing"),
            reason=str(data.get("reason", "")),
            uncertainty=list(data.get("uncertainty") or []),
        )

    def to_task_node(self, job_id: str, max_attempts: int = 2) -> TaskNode:
        """Converts structured planned task into executable TaskNode DAG element."""
        meta = {
            "expected_artifacts": self.expected_artifacts,
            "acceptance_criteria": self.acceptance_criteria,
            "verification": self.verification,
            "risk": self.risk,
            "evidence_refs": self.evidence_refs,
            "evidence_status": self.evidence_status,
            "reason": self.reason,
            "uncertainty": self.uncertainty,
        }
        return TaskNode(
            task_id=self.task_id,
            job_id=job_id,
            description=self.description,
            dependencies=list(self.dependencies),
            required_capabilities=list(self.required_capabilities),
            metadata=meta,
            max_attempts=max_attempts,
        )


@dataclass
class StructuredPlan:
    """Complete structured plan generated from repository reconnaissance and goal."""
    job_id: str
    goal: str
    summary: str
    tasks: List[PlannedTask] = field(default_factory=list)
    uncertainty: List[str] = field(default_factory=list)
    risk_assessment: str = "medium"
    evidence_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "goal": self.goal,
            "summary": self.summary,
            "tasks": [t.to_dict() for t in self.tasks],
            "uncertainty": self.uncertainty,
            "risk_assessment": self.risk_assessment,
            "evidence_summary": self.evidence_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredPlan":
        tasks_raw = data.get("tasks") or []
        tasks = [PlannedTask.from_dict(t) if isinstance(t, dict) else t for t in tasks_raw]
        return cls(
            job_id=str(data.get("job_id") or data.get("jobId", "")),
            goal=str(data.get("goal", "")),
            summary=str(data.get("summary", "")),
            tasks=tasks,
            uncertainty=list(data.get("uncertainty") or []),
            risk_assessment=str(data.get("risk_assessment") or data.get("riskAssessment", "medium")),
            evidence_summary=str(data.get("evidence_summary") or data.get("evidenceSummary", "")),
        )


@dataclass
class PlanningRequest:
    """Formal request input for repository-grounded goal-to-graph initial planning."""
    job_id: str
    goal: str
    target_repo: Path
    constraints: List[str] = field(default_factory=list)
    supplied_context: Dict[str, Any] = field(default_factory=dict)
    available_capabilities: List[str] = field(default_factory=list)
    limits: RuntimeLimits = field(default_factory=RuntimeLimits)
    evidence: Optional[RepositoryEvidence] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "goal": self.goal,
            "target_repo": str(self.target_repo),
            "constraints": self.constraints,
            "supplied_context": self.supplied_context,
            "available_capabilities": self.available_capabilities,
            "limits": self.limits.to_dict(),
            "evidence": self.evidence.to_dict() if self.evidence else None,
        }
