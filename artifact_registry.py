from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("hermes.artifact_registry")

VALID_ARTIFACT_TYPES: Set[str] = {
    "git_commit",
    "git_diff",
    "file",
    "handoff",
    "run_summary",
    "test_report",
    "verification_report",
    "log",
    "stdout",
    "stderr",
    "generic",
}


@dataclass
class ArtifactRef:
    id: str
    type: str  # One of VALID_ARTIFACT_TYPES or extensible string
    label: str
    ref: str
    jobId: Optional[str] = None
    phaseId: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactRef":
        return cls(
            id=data.get("id", ""),
            type=data.get("type", "generic"),
            label=data.get("label", ""),
            ref=data.get("ref", ""),
            jobId=data.get("jobId"),
            phaseId=data.get("phaseId"),
            metadata=data.get("metadata") or {},
            createdAt=data.get("createdAt") or datetime.now(timezone.utc).isoformat(),
        )


class ArtifactRegistry:
    """
    Registry for operational artifacts generated during job and phase execution.
    Provides validation, indexing, and containment checks against allowed filesystem roots.
    """

    def __init__(self, allowed_roots: Optional[List[Path]] = None):
        self._artifacts: Dict[str, ArtifactRef] = {}
        self._job_index: Dict[str, List[str]] = {}
        self.allowed_roots = allowed_roots or []

    def add_allowed_root(self, root: Path) -> None:
        resolved = root.resolve()
        if resolved not in self.allowed_roots:
            self.allowed_roots.append(resolved)

    def is_safe_path(self, path_str: str) -> bool:
        """Validates that a file path is contained within configured allowed roots and prevents traversal."""
        try:
            target = Path(path_str).resolve()
            if not self.allowed_roots:
                return True
            return any(target == root or root in target.parents for root in self.allowed_roots)
        except Exception:
            return False

    def register(self, artifact: ArtifactRef) -> ArtifactRef:
        if not artifact.type:
            artifact.type = "generic"

        self._artifacts[artifact.id] = artifact
        if artifact.jobId:
            if artifact.jobId not in self._job_index:
                self._job_index[artifact.jobId] = []
            if artifact.id not in self._job_index[artifact.jobId]:
                self._job_index[artifact.jobId].append(artifact.id)

        return artifact

    def get(self, artifact_id: str) -> Optional[ArtifactRef]:
        return self._artifacts.get(artifact_id)

    def list_for_job(self, job_id: str) -> List[ArtifactRef]:
        art_ids = self._job_index.get(job_id, [])
        return [self._artifacts[aid] for aid in art_ids if aid in self._artifacts]

    def list_all(self, limit: int = 100) -> List[ArtifactRef]:
        return list(self._artifacts.values())[:limit]


artifact_registry = ArtifactRegistry()
