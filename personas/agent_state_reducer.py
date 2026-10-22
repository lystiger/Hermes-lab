from typing import Any, Dict, Optional
from capabilities.normalization import normalize_agent_id


class AgentStateReducer:
    """
    Consumes runtime events and deterministically reduces active agent status and tasks.
    """

    def __init__(self, agent_service=None):
        self._agent_service = agent_service
        # Sprint phases an agent is running now, keyed "<job>:<order or phase>". Parallel phase
        # groups can run one agent in several phases; the agent stays RUNNING until all finish.
        self._running_phases: Dict[str, Dict[str, str]] = {}

    def bind_service(self, agent_service):
        self._agent_service = agent_service

    def apply(
        self,
        source_id: str,
        kind: str,
        detail: str,
        metadata: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
    ) -> None:
        if not self._agent_service:
            return

        normalized_id = normalize_agent_id(source_id)
        meta = metadata or {}

        if kind.startswith("phase."):
            phases = self._running_phases.setdefault(normalized_id, {})
            key = f"{job_id or meta.get('jobId') or ''}:{meta.get('order') or meta.get('phase') or detail}"
            if kind == "phase.started":
                phases[key] = str(meta.get("phase") or detail or "Executing phase")
                self._agent_service.set_agent_status(normalized_id, "RUNNING", current_task=phases[key])
            elif kind in ("phase.completed", "phase.failed"):
                phases.pop(key, None)
                if kind == "phase.failed":
                    self._agent_service.set_agent_status(normalized_id, "ERROR", current_task=None)
                elif phases:
                    self._agent_service.set_agent_status(
                        normalized_id, "RUNNING", current_task=next(iter(phases.values()))
                    )
                else:
                    self._agent_service.set_agent_status(normalized_id, "IDLE", current_task=None)
            return

        if kind == "agent.started":
            if "model" in meta:
                from agent_models import model_registry
                model_registry.record(source_id, meta)
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
            # Inside a sprint phase the agent stays RUNNING until phase.completed.
            if not self._running_phases.get(normalized_id):
                self._agent_service.set_agent_status(
                    normalized_id, "IDLE", current_task=None
                )

        elif kind == "agent.cancelled":
            self._running_phases.pop(normalized_id, None)
            self._agent_service.set_agent_status(
                normalized_id, "IDLE", current_task=None
            )

        elif kind in ("agent.failed", "agent.timed_out"):
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
