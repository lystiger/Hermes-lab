import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class ActorRef:
    id: str
    kind: str  # "agent" | "system" | "runtime" | "tool"
    displayName: str
    accentColor: Optional[str] = None


@dataclass(frozen=True)
class RuntimeEvent:
    id: str
    ts: str
    rawTs: float
    source: ActorRef
    kind: str
    detail: str
    dur: str = "—"
    jobId: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def job_id(self) -> Optional[str]:
        return self.jobId

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeEventBus:
    """
    Lightweight, thread-safe, in-process event bus for LysStack.
    Maintains recent event history and dispatches live events to async SSE subscribers.
    """

    def __init__(self, max_history: int = 500):
        self.max_history = max_history
        self._history: deque[RuntimeEvent] = deque(maxlen=max_history)
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._event_counter = 0

    def next_id(self) -> str:
        with self._lock:
            self._event_counter += 1
            return f"evt_{int(time.time() * 1000)}_{self._event_counter:04d}"

    def publish(
        self,
        source_id: str,
        kind: str,
        detail: str,
        source_kind: str = "system",
        source_name: Optional[str] = None,
        duration: str = "—",
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        accent_color: Optional[str] = None,
    ) -> RuntimeEvent:
        now_ts = time.time()
        # Formatted timestamp HH:MM:SS.mmm
        dt = datetime.now()
        ts_str = dt.strftime("%H:%M:%S") + f".{int(dt.microsecond / 1000):03d}"

        display_name = source_name or source_id.capitalize()
        actor = ActorRef(
            id=source_id.lower(),
            kind=source_kind,
            displayName=display_name,
            accentColor=accent_color,
        )

        event = RuntimeEvent(
            id=self.next_id(),
            ts=ts_str,
            rawTs=now_ts,
            source=actor,
            kind=kind,
            detail=detail,
            dur=duration,
            jobId=job_id,
            metadata=metadata or {},
        )

        with self._lock:
            self._history.append(event)
            # Notify live async subscribers
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

        return event

    def recent(self, limit: int = 100, after_id: Optional[str] = None) -> List[RuntimeEvent]:
        with self._lock:
            events = list(self._history)

        if after_id:
            try:
                idx = next(i for i, e in enumerate(events) if e.id == after_id)
                events = events[idx + 1 :]
            except StopIteration:
                pass

        if limit and len(events) > limit:
            events = events[-limit:]

        return events

    def subscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)


# Singleton event bus instance for LysStack runtime
event_bus = RuntimeEventBus()
