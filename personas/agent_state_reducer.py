from typing import Any, Dict, Optional
from capabilities.normalization import normalize_agent_id


class AgentStateReducer:
    """
    Consumes runtime events and deterministically reduces active agent status and tasks.
    """

    def __init__(self, agent_service=None):
        self._agent_service = agent_service

    def bind_service(self, agent_service):
        self._agent_service = agent_service

    def apply(
        self,
        source_id: str,
        kind: str,
        detail: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._agent_service:
            return

        normalized_id = normalize_agent_id(source_id)
        meta = metadata or {}

        if kind == "agent.started":
            task_description = (
                meta.get("task")
                or meta.get("phase")
                or detail
                or "Executing assigned task"
            )
            self._agent_service.set_agent_status(
                normalized_id, "RUNNING", current_task=str(task_description)
            )

        elif kind == "agent.finished":
            self._agent_service.set_agent_status(
                normalized_id, "IDLE", current_task=None
            )

        elif kind == "agent.failed":
            self._agent_service.set_agent_status(
                normalized_id, "ERROR", current_task=None
            )

        elif kind == "agent.waiting":
            task_description = meta.get("task") or detail
            self._agent_service.set_agent_status(
                normalized_id, "WAITING", current_task=str(task_description)
            )

        elif kind == "agent.busy":
            task_description = meta.get("task") or detail
            self._agent_service.set_agent_status(
                normalized_id, "BUSY", current_task=str(task_description)
            )


agent_state_reducer = AgentStateReducer()
