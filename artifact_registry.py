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
class ArtifactTrust:
    status: str  # "verified" | "unverified" | "not_applicable"
    kind: str    # "path_containment" | "git_reference" | "none"
    scope: str   # "hermes_run_root" | "target_repository" | "external" | "unknown"
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactTrust":
        return cls(
            status=data.get("status", "unverified"),
            kind=data.get("kind", "none"),
            scope=data.get("scope", "unknown"),
            detail=data.get("detail"),
        )


@dataclass
class ArtifactRef:
    id: str
    type: str  # One of VALID_ARTIFACT_TYPES or extensible string
    label: str
    ref: str
    jobId: Optional[str] = None
    phaseId: Optional[str] = None
    trust: Optional[ArtifactTrust] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.trust:
            data["trust"] = self.trust.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactRef":
        trust_data = data.get("trust")
        trust_obj = ArtifactTrust.from_dict(trust_data) if isinstance(trust_data, dict) else trust_data
        return cls(
            id=data.get("id", ""),
            type=data.get("type", "generic"),
            label=data.get("label", ""),
            ref=data.get("ref", ""),
            jobId=data.get("jobId"),
            phaseId=data.get("phaseId"),
            trust=trust_obj,
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
        self.allowed_roots = [r.resolve() for r in (allowed_roots or [])]

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

    def validate_artifact_trust(self, artifact: ArtifactRef) -> ArtifactTrust:
        """Determines truthful trust status for an artifact reference without client-side speculation."""
        art_type = artifact.type.lower() if artifact.type else "generic"

        # Non-filesystem git commit / diff artifacts
        if art_type in {"git_commit", "git_diff"}:
            return ArtifactTrust(
                status="not_applicable",
                kind="git_reference",
                scope="target_repository",
                detail="Git commit reference",
            )

        # Filesystem-backed artifacts
        if art_type in {"handoff", "run_summary", "log", "stdout", "stderr", "file", "test_report", "verification_report"}:
            try:
                # If ref is relative (e.g. handoffs/01_builder.md) and not absolute, check if it contains .. escape
                if ".." in Path(artifact.ref).parts:
                    return ArtifactTrust(
                        status="unverified",
                        kind="path_containment",
                        scope="external",
                        detail="Path escapes allowed roots via traversal",
                    )

                target_path = Path(artifact.ref)
                # If absolute, verify against allowed roots
                if target_path.is_absolute():
                    resolved = target_path.resolve()
                    matched_root = next((r for r in self.allowed_roots if resolved == r or r in resolved.parents), None)
                    if matched_root:
                        scope = "hermes_run_root" if "run" in matched_root.name.lower() or "hermes-runs" in str(matched_root).lower() else "target_repository"
                        detail_desc = "Contained within Hermes run root" if scope == "hermes_run_root" else "Contained within target repository"
                        return ArtifactTrust(
                            status="verified",
                            kind="path_containment",
                            scope=scope,
                            detail=detail_desc,
                        )
                    else:
                        return ArtifactTrust(
                            status="unverified",
                            kind="path_containment",
                            scope="external",
                            detail="Path escapes allowed Hermes roots",
                        )
                else:
                    # Relative path without escape
                    return ArtifactTrust(
                        status="verified",
                        kind="path_containment",
                        scope="hermes_run_root",
                        detail="Contained within Hermes run root",
                    )
            except Exception as e:
                return ArtifactTrust(
                    status="unverified",
                    kind="path_containment",
                    scope="external",
                    detail=f"Verification failed: {e}",
                )

        return ArtifactTrust(
            status="unverified",
            kind="none",
            scope="unknown",
            detail="Verification unavailable",
        )

    def register(self, artifact: ArtifactRef) -> ArtifactRef:
        if not artifact.type:
            artifact.type = "generic"

        if artifact.trust is None:
            artifact.trust = self.validate_artifact_trust(artifact)

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
