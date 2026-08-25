import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
import uuid

logger = logging.getLogger("hermes.runtime.storage.schema")

CURRENT_SCHEMA_VERSION = 1


class SchemaError(ValueError):
    """Base error for schema validation issues."""
    pass


class UnsupportedSchemaVersionError(SchemaError):
    """Raised when an event has an unknown or unsupported schema version."""
    pass


class InvalidEventEnvelopeError(SchemaError):
    """Raised when an event envelope violates structural constraints."""
    pass


@dataclass(frozen=True)
class StoredRuntimeEvent:
    """
    Canonical immutable event envelope for all runtime events.
    """
    event_id: str
    job_id: str
    sequence: int
    event_type: str
    occurred_at: str
    schema_version: int = 1
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    actor_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_id:
            raise InvalidEventEnvelopeError("event_id cannot be empty")
        if not self.job_id:
            raise InvalidEventEnvelopeError("job_id cannot be empty")
        if not self.event_type:
            raise InvalidEventEnvelopeError("event_type cannot be empty")
        if self.schema_version < 1:
            raise UnsupportedSchemaVersionError(f"schema_version must be >= 1, got {self.schema_version}")
        if self.schema_version > CURRENT_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"schema_version {self.schema_version} exceeds maximum supported version {CURRENT_SCHEMA_VERSION}"
            )
        # Ensure payload is JSON-serializable
        try:
            json.dumps(self.payload)
        except (TypeError, OverflowError) as exc:
            raise InvalidEventEnvelopeError(f"payload must be JSON-serializable: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "id": self.event_id,
            "job_id": self.job_id,
            "jobId": self.job_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "eventType": self.event_type,
            "kind": self.event_type,
            "occurred_at": self.occurred_at,
            "ts": self.occurred_at,
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "taskId": self.task_id,
            "run_id": self.run_id,
            "runId": self.run_id,
            "actor_id": self.actor_id,
            "actorId": self.actor_id,
            "parent_event_id": self.parent_event_id,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "payload": dict(self.payload),
            "detail": self.payload.get("detail") or self.payload.get("reason") or self.event_type,
            "metadata": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredRuntimeEvent":
        try:
            return cls(
                event_id=str(data["event_id"]),
                job_id=str(data["job_id"]),
                sequence=int(data.get("sequence", 0)),
                event_type=str(data["event_type"]),
                occurred_at=str(data.get("occurred_at") or datetime.now(timezone.utc).isoformat()),
                schema_version=int(data.get("schema_version", 1)),
                task_id=str(data["task_id"]) if data.get("task_id") is not None else None,
                run_id=str(data["run_id"]) if data.get("run_id") is not None else None,
                actor_id=str(data["actor_id"]) if data.get("actor_id") is not None else None,
                parent_event_id=str(data["parent_event_id"]) if data.get("parent_event_id") is not None else None,
                causation_id=str(data["causation_id"]) if data.get("causation_id") is not None else None,
                correlation_id=str(data["correlation_id"]) if data.get("correlation_id") is not None else None,
                payload=dict(data.get("payload") or {}),
            )
        except KeyError as exc:
            raise InvalidEventEnvelopeError(f"Missing required field in event data: {exc}") from exc


def create_event(
    job_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
    sequence: int = 0,
    occurred_at: Optional[str] = None,
    schema_version: int = 1,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> StoredRuntimeEvent:
    """Helper factory for constructing validated StoredRuntimeEvent instances."""
    return StoredRuntimeEvent(
        event_id=event_id or str(uuid.uuid4()),
        job_id=job_id,
        sequence=sequence,
        event_type=event_type,
        occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(),
        schema_version=schema_version,
        task_id=task_id,
        run_id=run_id,
        actor_id=actor_id,
        parent_event_id=parent_event_id,
        causation_id=causation_id,
        correlation_id=correlation_id,
        payload=payload or {},
    )


class EventSchemaRegistry:
    """
    Registry for event version validation and upcasting migrations.
    """

    def __init__(self):
        self._upcasters: Dict[int, Callable[[StoredRuntimeEvent], StoredRuntimeEvent]] = {}

    def register_upcaster(self, from_version: int, upcaster: Callable[[StoredRuntimeEvent], StoredRuntimeEvent]) -> None:
        self._upcasters[from_version] = upcaster

    def upcast(self, event: StoredRuntimeEvent) -> StoredRuntimeEvent:
        current = event
        while current.schema_version < CURRENT_SCHEMA_VERSION:
            if current.schema_version not in self._upcasters:
                raise UnsupportedSchemaVersionError(
                    f"No upcaster registered to upgrade event from schema version {current.schema_version}"
                )
            upcaster = self._upcasters[current.schema_version]
            current = upcaster(current)
        return current


schema_registry = EventSchemaRegistry()
