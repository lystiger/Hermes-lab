import asyncio
import copy
import logging
from typing import Dict, List, Optional, Set
from dataclasses import replace

from runtime.storage.event_store import (
    RuntimeEventStore,
    IdempotencyConflictError,
    SequenceConflictError,
)
from runtime.storage.schema_registry import StoredRuntimeEvent

logger = logging.getLogger("hermes.runtime.storage.in_memory")

TERMINAL_EVENT_TYPES = {
    "job.completed",
    "job.blocked",
    "job.failed",
    "job.cancelled",
}


class InMemoryRuntimeEventStore(RuntimeEventStore):
    """
    Thread-safe, in-memory implementation of RuntimeEventStore.
    Enforces per-job monotonic sequencing, idempotency, and uniqueness identical to PostgreSQL.
    """

    def __init__(self):
        # job_id -> list of StoredRuntimeEvent
        self._events_by_job: Dict[str, List[StoredRuntimeEvent]] = {}
        # event_id -> StoredRuntimeEvent
        self._events_by_id: Dict[str, StoredRuntimeEvent] = {}
        # job_id -> current latest sequence
        self._job_sequences: Dict[str, int] = {}
        # job_id -> asyncio.Lock
        self._job_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._closed = False

    async def _get_job_lock(self, job_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if job_id not in self._job_locks:
                self._job_locks[job_id] = asyncio.Lock()
            return self._job_locks[job_id]

    async def append(self, event: StoredRuntimeEvent) -> StoredRuntimeEvent:
        if self._closed:
            raise RuntimeError("Event store is closed")

        lock = await self._get_job_lock(event.job_id)
        async with lock:
            # 1. Check Idempotency by event_id
            existing = self._events_by_id.get(event.event_id)
            if existing is not None:
                # Validate identical payload and properties
                if (
                    existing.job_id == event.job_id
                    and existing.event_type == event.event_type
                    and existing.payload == event.payload
                    and existing.task_id == event.task_id
                    and existing.run_id == event.run_id
                    and existing.actor_id == event.actor_id
                    and existing.schema_version == event.schema_version
                ):
                    logger.debug("Idempotent duplicate append for event %s", event.event_id)
                    return copy.deepcopy(existing)
                else:
                    raise IdempotencyConflictError(
                        f"Event '{event.event_id}' already exists with conflicting data"
                    )

            # 2. Determine and validate sequence
            current_seq = self._job_sequences.get(event.job_id, 0)
            if event.sequence <= 0:
                allocated_seq = current_seq + 1
            else:
                # Explicit sequence validation: must be exact next sequence (no gaps or duplicates)
                if event.sequence != current_seq + 1:
                    raise SequenceConflictError(
                        f"Explicit sequence {event.sequence} is invalid; expected next sequence {current_seq + 1} for job '{event.job_id}'"
                    )
                allocated_seq = event.sequence

            # Construct stored event with immutable copy
            stored = replace(
                event,
                sequence=allocated_seq,
                payload=copy.deepcopy(event.payload),
            )

            # 3. Store event
            if event.job_id not in self._events_by_job:
                self._events_by_job[event.job_id] = []
            self._events_by_job[event.job_id].append(stored)
            self._events_by_id[stored.event_id] = stored
            self._job_sequences[event.job_id] = max(current_seq, allocated_seq)

            return copy.deepcopy(stored)

    async def list_events(self, job_id: str, limit: Optional[int] = None) -> List[StoredRuntimeEvent]:
        lock = await self._get_job_lock(job_id)
        async with lock:
            events = self._events_by_job.get(job_id, [])
            # Return deep copies sorted by sequence
            sorted_events = sorted(events, key=lambda e: e.sequence)
            if limit is not None and limit > 0:
                sorted_events = sorted_events[:limit]
            return [copy.deepcopy(e) for e in sorted_events]

    async def events_after(
        self, job_id: str, sequence: int, limit: Optional[int] = None
    ) -> List[StoredRuntimeEvent]:
        lock = await self._get_job_lock(job_id)
        async with lock:
            events = self._events_by_job.get(job_id, [])
            filtered = [e for e in events if e.sequence > sequence]
            sorted_events = sorted(filtered, key=lambda e: e.sequence)
            if limit is not None and limit > 0:
                sorted_events = sorted_events[:limit]
            return [copy.deepcopy(e) for e in sorted_events]

    async def latest_sequence(self, job_id: str) -> int:
        lock = await self._get_job_lock(job_id)
        async with lock:
            return self._job_sequences.get(job_id, 0)

    async def get_event(self, event_id: str) -> Optional[StoredRuntimeEvent]:
        async with self._global_lock:
            evt = self._events_by_id.get(event_id)
            return copy.deepcopy(evt) if evt else None

    async def list_unfinished_jobs(self) -> List[str]:
        async with self._global_lock:
            unfinished = []
            for job_id, events in self._events_by_job.items():
                if not events:
                    continue
                has_terminal = False
                for e in events:
                    if e.event_type in TERMINAL_EVENT_TYPES:
                        has_terminal = True
                        break
                    if e.event_type == "job.state_changed":
                        new_state = (e.payload.get("new_state") or "").lower()
                        if new_state in {"completed", "blocked", "failed", "cancelled"}:
                            has_terminal = True
                            break
                if not has_terminal:
                    unfinished.append(job_id)
            return sorted(unfinished)

    async def health_check(self) -> bool:
        return not self._closed

    async def close(self) -> None:
        self._closed = True

    def clear(self) -> None:
        """Utility for test setups to reset store state."""
        self._events_by_job.clear()
        self._events_by_id.clear()
        self._job_sequences.clear()
        self._job_locks.clear()
