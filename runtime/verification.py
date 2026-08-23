from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from runtime.job_state import JobRecord
from runtime.task_graph import TaskGraph

logger = logging.getLogger("hermes.runtime.verification")


class VerificationStatus(str, Enum):
    """Structured outcome of the job verification stage."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    REPAIRABLE = "REPAIRABLE"


@dataclass
class VerificationCheck:
    """Individual verification check result."""
    name: str
    passed: bool
    detail: Optional[str] = None
    error: Optional[str] = None
    repairable: bool = False
    repair_recommendation: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    """Structured result of the job verification stage."""
    status: VerificationStatus = VerificationStatus.PASSED
    verifier_id: str = "default_verifier"
    summary: str = "All verification checks passed."
    checks: List[VerificationCheck] = field(default_factory=list)
    repair_recommendations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = VerificationStatus(self.status.upper())

    @property
    def is_passed(self) -> bool:
        return self.status == VerificationStatus.PASSED

    @property
    def is_repairable(self) -> bool:
        return self.status == VerificationStatus.REPAIRABLE

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["checks"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.checks]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        st = data.get("status", "PASSED")
        raw_checks = data.get("checks", [])
        checks = []
        for c in raw_checks:
            if isinstance(c, dict):
                checks.append(VerificationCheck(**c))
            elif isinstance(c, VerificationCheck):
                checks.append(c)

        return cls(
            status=VerificationStatus(st.upper()) if isinstance(st, str) else st,
            verifier_id=str(data.get("verifier_id", "verifier")),
            summary=str(data.get("summary", "")),
            checks=checks,
            repair_recommendations=list(data.get("repair_recommendations", [])),
            metadata=dict(data.get("metadata", {})),
        )


class VerifierAdapter:
    """Base interface for executing verification strategies."""

    async def verify(
        self,
        job: JobRecord,
        graph: TaskGraph,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        raise NotImplementedError


class CallableVerifierAdapter(VerifierAdapter):
    """Adapter wrapping a custom callable verification function."""

    def __init__(self, func: Callable):
        self.func = func

    async def verify(
        self,
        job: JobRecord,
        graph: TaskGraph,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        import inspect
        ctx = context or {}
        arts = artifacts or []
        if inspect.iscoroutinefunction(self.func):
            res = await self.func(job, graph, arts, ctx)
        else:
            res = self.func(job, graph, arts, ctx)

        if isinstance(res, VerificationResult):
            return res
        if isinstance(res, dict):
            return VerificationResult.from_dict(res)
        if isinstance(res, bool):
            if res:
                return VerificationResult(status=VerificationStatus.PASSED, summary="Verification passed")
            else:
                return VerificationResult(status=VerificationStatus.FAILED, summary="Verification check failed")
        return VerificationResult(status=VerificationStatus.PASSED, summary=str(res))


class DefaultPassVerifierAdapter(VerifierAdapter):
    """Default verifier that passes when all graph tasks are succeeded."""

    async def verify(
        self,
        job: JobRecord,
        graph: TaskGraph,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        if graph.is_all_completed():
            return VerificationResult(
                status=VerificationStatus.PASSED,
                summary="Default verification passed: all task nodes succeeded.",
            )
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary="Default verification failed: incomplete tasks exist in graph.",
        )
