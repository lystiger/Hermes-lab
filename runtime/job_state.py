from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger("hermes.runtime.job_state")


class JobState(str, Enum):
    """Explicit lifecycle states for a reactive execution job."""
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_FOR_CAPACITY = "waiting_for_capacity"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


LEGAL_JOB_TRANSITIONS: Dict[JobState, Set[JobState]] = {
    JobState.CREATED: {JobState.PLANNING, JobState.CANCELLED, JobState.FAILED},
    JobState.PLANNING: {JobState.EXECUTING, JobState.WAITING_FOR_CAPACITY, JobState.BLOCKED, JobState.FAILED, JobState.CANCELLED},
    JobState.EXECUTING: {JobState.VERIFYING, JobState.PLANNING, JobState.WAITING_FOR_CAPACITY, JobState.REPAIRING, JobState.BLOCKED, JobState.FAILED, JobState.CANCELLED},
    JobState.WAITING_FOR_CAPACITY: {JobState.EXECUTING, JobState.PLANNING, JobState.BLOCKED, JobState.FAILED, JobState.CANCELLED},
    JobState.VERIFYING: {JobState.COMPLETED, JobState.REPAIRING, JobState.WAITING_FOR_CAPACITY, JobState.BLOCKED, JobState.FAILED, JobState.CANCELLED},
    JobState.REPAIRING: {JobState.EXECUTING, JobState.PLANNING, JobState.WAITING_FOR_CAPACITY, JobState.BLOCKED, JobState.FAILED, JobState.CANCELLED},
    JobState.COMPLETED: set(),
    JobState.BLOCKED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}

TERMINAL_JOB_STATES: Set[JobState] = {
    JobState.COMPLETED,
    JobState.BLOCKED,
    JobState.FAILED,
    JobState.CANCELLED,
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal job state transition is attempted."""

    def __init__(self, current_state: JobState, target_state: JobState, job_id: str, reason: Optional[str] = None):
        msg = f"Illegal transition for job '{job_id}' from '{current_state.value}' to '{target_state.value}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.current_state = current_state
        self.target_state = target_state
        self.job_id = job_id
        self.reason = reason


@dataclass
class JobRecord:
    """Authoritative runtime state representation of a job."""
    job_id: str
    goal: str
    title: Optional[str] = None
    state: JobState = JobState.CREATED
    repository: Optional[str] = None
    branch: Optional[str] = None
    priority: str = "P1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    current_phase: Optional[str] = None
    blocked_reason: Optional[Union[Dict[str, Any], str]] = None
    failure_reason: Optional[Union[Dict[str, Any], str]] = None
    replan_count: int = 0
    repair_count: int = 0
    assigned_agents: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.title:
            self.title = self.goal[:80] if self.goal else f"Job {self.job_id}"
        if isinstance(self.state, str):
            self.state = JobState(self.state.lower())

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_JOB_STATES

    def can_transition_to(self, target_state: Union[JobState, str]) -> bool:
        target = JobState(target_state.lower()) if isinstance(target_state, str) else target_state
        return target in LEGAL_JOB_TRANSITIONS.get(self.state, set())

    def transition_to(
        self,
        target_state: Union[JobState, str],
        reason: Optional[Union[Dict[str, Any], str]] = None,
        event_bridge: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobState:
        """
        Transitions job state centrally according to legal transition rules.
        Emits runtime events upon successful transition.
        """
        target = JobState(target_state.lower()) if isinstance(target_state, str) else target_state
        now_iso = datetime.now(timezone.utc).isoformat()

        if target == self.state:
            # Idempotent no-op
            return self.state

        if not self.can_transition_to(target):
            raise InvalidStateTransitionError(
                current_state=self.state,
                target_state=target,
                job_id=self.job_id,
                reason=str(reason) if reason else None,
            )

        previous_state = self.state
        self.state = target

        if previous_state == JobState.CREATED and target in {JobState.PLANNING, JobState.EXECUTING}:
            if not self.started_at:
                self.started_at = now_iso

        if target in TERMINAL_JOB_STATES:
            if not self.completed_at:
                self.completed_at = now_iso

        if target == JobState.BLOCKED:
            self.blocked_reason = reason
        elif target == JobState.FAILED:
            self.failure_reason = reason
        elif target == JobState.REPAIRING:
            self.repair_count += 1
        elif target == JobState.PLANNING and previous_state in {JobState.EXECUTING, JobState.REPAIRING}:
            self.replan_count += 1

        if metadata:
            self.metadata.update(metadata)

        logger.info("Job %s transitioned %s -> %s (reason: %s)", self.job_id, previous_state.value, target.value, reason)

        if event_bridge and hasattr(event_bridge, "emit_job_state_changed"):
            res = event_bridge.emit_job_state_changed(
                job=self,
                previous_state=previous_state,
                reason=reason,
                metadata=metadata,
            )
            if asyncio.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(res)
                except RuntimeError:
                    pass

        return self.state

    def snapshot(self) -> Dict[str, Any]:
        """Returns a deep snapshot of all mutable job state attributes for atomic rollback."""
        return {
            "state": self.state,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_phase": self.current_phase,
            "blocked_reason": self.blocked_reason,
            "failure_reason": self.failure_reason,
            "replan_count": self.replan_count,
            "repair_count": self.repair_count,
            "assigned_agents": list(self.assigned_agents),
            "metadata": dict(self.metadata),
        }

    def restore(self, snapshot: Dict[str, Any]) -> None:
        """Restores job state from a previous snapshot."""
        self.state = snapshot["state"]
        self.started_at = snapshot["started_at"]
        self.completed_at = snapshot["completed_at"]
        self.current_phase = snapshot["current_phase"]
        self.blocked_reason = snapshot["blocked_reason"]
        self.failure_reason = snapshot["failure_reason"]
        self.replan_count = snapshot["replan_count"]
        self.repair_count = snapshot["repair_count"]
        self.assigned_agents = list(snapshot["assigned_agents"])
        self.metadata = dict(snapshot["metadata"])

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobRecord":
        state_val = data.get("state", "created")
        return cls(
            job_id=data.get("job_id") or data.get("id", ""),
            goal=data.get("goal") or data.get("title", ""),
            title=data.get("title"),
            state=JobState(state_val.lower()) if isinstance(state_val, str) else state_val,
            repository=data.get("repository"),
            branch=data.get("branch"),
            priority=data.get("priority", "P1"),
            created_at=data.get("created_at") or data.get("createdAt", datetime.now(timezone.utc).isoformat()),
            started_at=data.get("started_at") or data.get("startedAt"),
            completed_at=data.get("completed_at") or data.get("completedAt"),
            current_phase=data.get("current_phase") or data.get("currentPhase"),
            blocked_reason=data.get("blocked_reason") or data.get("blockedReason"),
            failure_reason=data.get("failure_reason") or data.get("failureReason"),
            replan_count=int(data.get("replan_count") or data.get("replanCount", 0)),
            repair_count=int(data.get("repair_count") or data.get("repairCount", 0)),
            assigned_agents=data.get("assigned_agents") or data.get("assignedAgentIds", []),
            metadata=data.get("metadata") or {},
        )
