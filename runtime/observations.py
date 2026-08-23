from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes.runtime.observations")


@dataclass
class Observation:
    """A discrete piece of structured knowledge discovered during execution."""
    observation_id: str
    job_id: str
    kind: str
    content: str
    task_id: Optional[str] = None
    actor_id: Optional[str] = None
    confidence: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        obs_id = data.get("observation_id") or data.get("observationId") or data.get("id")
        if not obs_id:
            obs_id = f"obs_{int(time.time() * 1000)}_{id(data) % 10000:04d}"
        return cls(
            observation_id=str(obs_id),
            job_id=str(data.get("job_id") or data.get("jobId", "")),
            kind=str(data.get("kind", "discovery")),
            content=str(data.get("content", "")),
            task_id=data.get("task_id") or data.get("taskId"),
            actor_id=data.get("actor_id") or data.get("actorId"),
            confidence=float(data.get("confidence", 1.0)),
            created_at=data.get("created_at") or data.get("createdAt", datetime.now(timezone.utc).isoformat()),
            metadata=dict(data.get("metadata") or {}),
        )


class ObservationRegistry:
    """Central store for execution observations across jobs."""

    def __init__(self):
        self._observations: Dict[str, Observation] = {}

    def add_observation(
        self,
        job_id: str,
        kind: str,
        content: str,
        task_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        observation_id: Optional[str] = None,
    ) -> Observation:
        obs_id = observation_id or f"obs_{int(time.time() * 1000)}_{len(self._observations) + 1:04d}"
        obs = Observation(
            observation_id=obs_id,
            job_id=job_id,
            kind=kind,
            content=content,
            task_id=task_id,
            actor_id=actor_id,
            confidence=confidence,
            metadata=metadata or {},
        )
        self._observations[obs.observation_id] = obs
        logger.info("Recorded observation %s (%s) for job %s: %s", obs.observation_id, obs.kind, job_id, obs.content[:80])
        return obs

    def register(self, observation: Observation) -> Observation:
        self._observations[observation.observation_id] = observation
        return observation

    def get_observation(self, observation_id: str) -> Optional[Observation]:
        return self._observations.get(observation_id)

    def list_for_job(self, job_id: str, kind: Optional[str] = None) -> List[Observation]:
        obs = [o for o in self._observations.values() if o.job_id == job_id]
        if kind:
            obs = [o for o in obs if o.kind.lower() == kind.lower()]
        obs.sort(key=lambda o: o.created_at)
        return obs

    def list_for_task(self, task_id: str) -> List[Observation]:
        obs = [o for o in self._observations.values() if o.task_id == task_id]
        obs.sort(key=lambda o: o.created_at)
        return obs

    def clear(self) -> None:
        self._observations.clear()


default_observation_registry = ObservationRegistry()
