import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger("hermes.subagents")


@dataclass
class SubagentProfile:
    """Ephemeral, bounded subagent actor profile."""
    id: str
    parentAgentId: str
    capabilities: List[str]
    task: str
    displayName: Optional[str] = None
    depth: int = 1
    ephemeral: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.displayName:
            self.displayName = f"Subagent ({self.id})"

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubagentProfile":
        raw_id = str(data.get("id", "")).strip()
        parent_id = str(data.get("parentAgentId") or data.get("parent_agent_id", "")).strip()
        return cls(
            id=raw_id,
            parentAgentId=parent_id,
            capabilities=data.get("capabilities") or [],
            task=data.get("task", ""),
            displayName=data.get("displayName") or data.get("display_name"),
            depth=int(data.get("depth", 1)),
            ephemeral=bool(data.get("ephemeral", True)),
            metadata=data.get("metadata") or {},
        )


class SubagentManager:
    """
    Controller-owned manager for bounded ephemeral subagent lifecycle.
    Prevents unauthorized spawning, capability escalation, and recursive explosion.
    """

    def __init__(
        self,
        allow_subagents: bool = False,
        max_subagents_per_job: int = 3,
        max_depth: int = 1,
    ):
        self.allow_subagents = allow_subagents
        self.max_subagents_per_job = max_subagents_per_job
        self.max_depth = max_depth
        self._created_subagents: Dict[str, SubagentProfile] = {}
        self._counter: int = 0

    def can_create_subagent(
        self,
        parent_agent_id: str,
        requested_depth: int = 1,
        publisher: Any = None,
        job_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validates whether a subagent creation request is permitted."""
        if not self.allow_subagents:
            err = "Subagents are disabled by default for this job policy."
            logger.info(err)
            if publisher:
                publisher.publish(
                    source_id="subagent_manager",
                    source_kind="runtime",
                    kind="delegation.rejected",
                    detail=err,
                    job_id=job_id,
                    metadata={"reason": "subagents_disabled", "parentAgentId": parent_agent_id},
                )
            return False, err

        if len(self._created_subagents) >= self.max_subagents_per_job:
            err = f"Subagent limit reached for job ({len(self._created_subagents)}/{self.max_subagents_per_job})."
            logger.warning(err)
            if publisher:
                publisher.publish(
                    source_id="subagent_manager",
                    source_kind="runtime",
                    kind="delegation.limit_reached",
                    detail=err,
                    job_id=job_id,
                    metadata={"reason": "max_subagents_reached", "count": len(self._created_subagents)},
                )
            return False, err

        if requested_depth > self.max_depth:
            err = f"Subagent depth ({requested_depth}) exceeds maximum permitted depth ({self.max_depth})."
            logger.warning(err)
            if publisher:
                publisher.publish(
                    source_id="subagent_manager",
                    source_kind="runtime",
                    kind="delegation.limit_reached",
                    detail=err,
                    job_id=job_id,
                    metadata={"reason": "max_depth_exceeded", "requestedDepth": requested_depth, "maxDepth": self.max_depth},
                )
            return False, err

        return True, None

    def create_subagent(
        self,
        parent_agent_id: str,
        task: str,
        capabilities: Optional[Sequence[str]] = None,
        parent_depth: int = 0,
        publisher: Any = None,
        job_id: Optional[str] = None,
    ) -> Optional[SubagentProfile]:
        """
        Creates and registers a bounded ephemeral subagent.
        """
        target_depth = parent_depth + 1
        allowed, reason = self.can_create_subagent(
            parent_agent_id=parent_agent_id,
            requested_depth=target_depth,
            publisher=publisher,
            job_id=job_id,
        )
        if not allowed:
            return None

        self._counter += 1
        clean_parent = str(parent_agent_id).lower().replace("subagent_", "")
        subagent_id = f"subagent_{clean_parent}_{self._counter}"
        caps = list(capabilities or ["general-execution"])

        profile = SubagentProfile(
            id=subagent_id,
            parentAgentId=parent_agent_id,
            capabilities=caps,
            task=task,
            displayName=f"Subagent {self._counter} ({clean_parent})",
            depth=target_depth,
            ephemeral=True,
            metadata={"created_order": self._counter},
        )

        self._created_subagents[subagent_id] = profile

        if publisher:
            publisher.publish(
                source_id="subagent_manager",
                source_kind="runtime",
                kind="subagent.created",
                detail=f"Created ephemeral subagent {subagent_id} for task: {task[:100]}",
                job_id=job_id,
                metadata={
                    "subagentId": subagent_id,
                    "parentAgentId": parent_agent_id,
                    "depth": target_depth,
                    "capabilities": caps,
                },
            )

        return profile

    def get_subagent(self, subagent_id: str) -> Optional[SubagentProfile]:
        return self._created_subagents.get(subagent_id)

    def list_subagents(self) -> List[SubagentProfile]:
        return list(self._created_subagents.values())
