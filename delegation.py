import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

logger = logging.getLogger("hermes.delegation")

LYSSTACK_DELEGATION_START = "--- LYSSTACK DELEGATION OUTPUT ---"
LYSSTACK_DELEGATION_END = "--- END LYSSTACK DELEGATION OUTPUT ---"


@dataclass
class DelegationRequest:
    """A structured request from an agent to delegate a task to a capable actor."""
    task: str
    requiredCapabilities: List[str]
    id: Optional[str] = None
    requester: Optional[Dict[str, Any]] = None
    preferredActors: Optional[List[str]] = None
    excludedActors: Optional[List[str]] = None
    jobId: Optional[str] = None
    threadId: Optional[str] = None
    conversationId: Optional[str] = None
    parentMessageId: Optional[str] = None
    parentTaskId: Optional[str] = None
    allowSubagent: bool = False
    allowTools: bool = False
    maxDepth: int = 1
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.id:
            self.id = f"del_{int(time.time() * 1000)}_{id(self) % 10000:04d}"

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationRequest":
        raw_req_caps = data.get("requiredCapabilities") or data.get("required_capabilities") or []
        req_caps = [str(c).strip() for c in raw_req_caps if str(c).strip()]

        raw_pref = data.get("preferredActors") or data.get("preferred_actors") or []
        pref_actors = [str(p).strip() for p in raw_pref if str(p).strip()] or None

        raw_excl = data.get("excludedActors") or data.get("excluded_actors") or []
        excl_actors = [str(e).strip() for e in raw_excl if str(e).strip()] or None

        raw_requester = data.get("requester")
        requester_dict = raw_requester if isinstance(raw_requester, dict) else None

        return cls(
            id=data.get("id"),
            task=str(data.get("task", "")).strip(),
            requiredCapabilities=req_caps,
            requester=requester_dict,
            preferredActors=pref_actors,
            excludedActors=excl_actors,
            jobId=data.get("jobId") or data.get("job_id"),
            threadId=data.get("threadId") or data.get("thread_id"),
            conversationId=data.get("conversationId") or data.get("conversation_id"),
            parentMessageId=data.get("parentMessageId") or data.get("parent_message_id"),
            parentTaskId=data.get("parentTaskId") or data.get("parent_task_id"),
            allowSubagent=bool(data.get("allowSubagent") or data.get("allow_subagent", False)),
            allowTools=bool(data.get("allowTools") or data.get("allow_tools", False)),
            maxDepth=int(data.get("maxDepth") or data.get("max_depth", 1)),
            metadata=data.get("metadata"),
        )


@dataclass
class DelegationDecision:
    """Result of a capability matching decision for a delegation request."""
    requestId: str
    selectedActorId: Optional[str] = None
    status: str = "no_match"  # "selected", "no_match", "rejected", "limit_reached"
    reason: Optional[str] = None
    rejectedReasons: Optional[Dict[str, str]] = None
    requiredCapabilities: List[str] = field(default_factory=list)
    matchedCapabilities: List[str] = field(default_factory=list)
    missingCapabilities: List[str] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationDecision":
        return cls(
            requestId=data.get("requestId") or data.get("request_id", ""),
            selectedActorId=data.get("selectedActorId") or data.get("selected_actor_id"),
            status=data.get("status", "no_match"),
            reason=data.get("reason"),
            rejectedReasons=data.get("rejectedReasons") or data.get("rejected_reasons"),
            requiredCapabilities=data.get("requiredCapabilities") or data.get("required_capabilities") or [],
            matchedCapabilities=data.get("matchedCapabilities") or data.get("matched_capabilities") or [],
            missingCapabilities=data.get("missingCapabilities") or data.get("missing_capabilities") or [],
            metadata=data.get("metadata"),
        )


@dataclass
class TaskAssignment:
    """Authoritative record of task ownership and lifecycle."""
    taskId: str
    ownerActorId: str
    task: str
    status: str = "queued"  # "queued", "running", "completed", "failed", "cancelled"
    delegatedBy: Optional[str] = None
    parentTaskId: Optional[str] = None
    requiredCapabilities: List[str] = field(default_factory=list)
    jobId: Optional[str] = None
    threadId: Optional[str] = None
    conversationId: Optional[str] = None
    createdAt: str = ""
    completedAt: Optional[str] = None
    artifactRefs: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.createdAt:
            self.createdAt = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskAssignment":
        return cls(
            taskId=data.get("taskId") or data.get("task_id", ""),
            ownerActorId=data.get("ownerActorId") or data.get("owner_actor_id", ""),
            task=data.get("task", ""),
            status=data.get("status", "queued"),
            delegatedBy=data.get("delegatedBy") or data.get("delegated_by"),
            parentTaskId=data.get("parentTaskId") or data.get("parent_task_id"),
            requiredCapabilities=data.get("requiredCapabilities") or data.get("required_capabilities") or [],
            jobId=data.get("jobId") or data.get("job_id"),
            threadId=data.get("threadId") or data.get("thread_id"),
            conversationId=data.get("conversationId") or data.get("conversation_id"),
            createdAt=data.get("createdAt") or data.get("created_at", ""),
            completedAt=data.get("completedAt") or data.get("completed_at"),
            artifactRefs=data.get("artifactRefs") or data.get("artifact_refs"),
            metadata=data.get("metadata"),
        )
