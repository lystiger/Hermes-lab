"""D-009 execution visibility: the events backends emit and the sink that receives them.

Backends never touch the runtime event store. They emit `ExecutionEvent` objects through an
optional sink, and the runtime supplies a sink that records them (`HermesActorAdapter`).
Emission never raises: a broken sink must not fail an execution.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

logger = logging.getLogger("hermes.runner.backends.events")

STARTED = "execution.started"
RESOURCE_ACQUIRED = "execution.resource_acquired"
RESOURCE_READY = "execution.resource_ready"
RUNNING = "execution.running"
FINISHED = "execution.finished"
FAILED = "execution.failed"
CANCELLED = "execution.cancelled"
RESOURCE_POOLED = "execution.resource_pooled"
RESOURCE_RELEASED = "execution.resource_released"
RELEASE_FAILED = "execution.release_failed"

EXECUTION_EVENT_KINDS = (
    STARTED, RESOURCE_ACQUIRED, RESOURCE_READY, RUNNING, FINISHED, FAILED, CANCELLED,
    RESOURCE_POOLED, RESOURCE_RELEASED, RELEASE_FAILED,
)

# D-009 metadata names. Python keyword names map to the camelCase wire names.
_WIRE_NAMES = {
    "resource": "resource",
    "reused": "reused",
    "generation": "generation",
    "rig_id": "rigId",
    "session_name": "sessionName",
    "node_id": "nodeId",
    "expires_at": "expiresAt",
    "error_code": "errorCode",
    "error": "error",
    "duration_ms": "durationMs",
}
ERROR_TEXT_LIMIT = 500


@dataclass(frozen=True)
class ExecutionEvent:
    kind: str
    job_id: Optional[str]
    detail: str
    metadata: Mapping[str, Any]
    # Runtime context the backend does not know; the adapter binds it per task (D-009 task_id etc.).
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    actor_id: Optional[str] = None


ExecutionEventSink = Callable[[ExecutionEvent], None]


def new_execution_id():
    return f"exec_{uuid.uuid4().hex[:16]}"


def resource(kind, resource_id, label):
    """A D-009 `resource` object: kind is seat | pane | process."""
    return {"kind": kind, "id": str(resource_id), "label": str(label)}


def execution_metadata(backend, execution_id, **fields):
    """Build D-009 metadata. `None` values are omitted; unknown field names raise TypeError."""
    metadata = {"backend": backend, "executionId": execution_id}
    for key, value in fields.items():
        wire_name = _WIRE_NAMES[key]  # KeyError: an unknown field name is a programming error
        if value is not None:
            metadata[wire_name] = value
    if isinstance(metadata.get("error"), str):
        metadata["error"] = metadata["error"][:ERROR_TEXT_LIMIT]
    return metadata


def send_execution_event(sink, kind, *, backend, execution_id, job_id=None, detail="", **fields):
    """Hand one event to the sink. A no-op without a sink. Never raises."""
    if sink is None:
        return
    try:
        sink(ExecutionEvent(
            kind=kind,
            job_id=job_id,
            detail=detail,
            metadata=execution_metadata(backend, execution_id, **fields),
        ))
    except Exception:  # noqa: BLE001 - observability must never fail an execution
        logger.warning("Execution event %s was dropped", kind, exc_info=True)


class ExecutionTrace:
    """The lifecycle of one execution: a stable executionId, bound context, terminal events once.

    `bind()` sets fields (resource, rigId, generation, ...) that later events carry, so
    each event repeats what is known. `fail()` and `finish()` each emit at most once.
    """

    def __init__(self, backend, sink, job_id=None, *, cancel_codes=(), execution_id=None):
        self.backend = backend
        self.sink = sink
        self.job_id = job_id
        self.execution_id = execution_id or new_execution_id()
        self._cancel_codes = frozenset(cancel_codes)
        self._started = time.monotonic()
        self._context = {}
        self._emitted = set()

    def bind(self, **fields):
        self._context.update(fields)

    def event(self, kind, detail="", **fields):
        send_execution_event(
            self.sink, kind, backend=self.backend, execution_id=self.execution_id,
            job_id=self.job_id, detail=detail, **{**self._context, **fields},
        )

    def started(self, detail=""):
        self.event(STARTED, detail)

    def finish(self, detail=""):
        if FINISHED not in self._emitted:
            self._emitted.add(FINISHED)
            self.event(FINISHED, detail, duration_ms=self.elapsed_ms())

    def fail(self, exc):
        code = getattr(exc, "code", None)
        kind = CANCELLED if code in self._cancel_codes else FAILED
        if kind in self._emitted:
            return
        self._emitted.add(kind)
        message = getattr(exc, "message", None) or str(exc) or type(exc).__name__
        self.event(
            kind, str(message)[:ERROR_TEXT_LIMIT], error_code=code, error=str(message),
            duration_ms=self.elapsed_ms(),
        )

    def elapsed_ms(self):
        return int((time.monotonic() - self._started) * 1000)
