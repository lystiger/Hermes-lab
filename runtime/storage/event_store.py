from abc import ABC, abstractmethod
from typing import List, Optional
from runtime.storage.schema_registry import StoredRuntimeEvent


class EventStoreError(Exception):
    """Base exception for all event store operations."""
    pass


class StorageUnavailableError(EventStoreError):
    """Raised when the backing storage system is unreachable or disconnected."""
    pass


class DuplicateEventError(EventStoreError):
    """Raised when an event with the same ID or sequence already exists with different data."""
    pass


class IdempotencyConflictError(EventStoreError):
    """Raised when appending an event with an existing event_id but conflicting payload/metadata."""
    pass


class SequenceConflictError(EventStoreError):
    """Raised when an explicit sequence assignment conflicts with an existing event sequence."""
    pass


class RuntimeEventStore(ABC):
    """
    Abstract interface for append-only, sequentially ordered runtime event storage.
    """

    @abstractmethod
    async def append(self, event: StoredRuntimeEvent) -> StoredRuntimeEvent:
        """
        Atomically appends an event to the store.
        If event.sequence <= 0, allocates the next monotonically increasing sequence for the job.
        Implements idempotent deduplication if the exact same event is appended again.
        """
        pass

    @abstractmethod
    async def list_events(self, job_id: str, limit: Optional[int] = None) -> List[StoredRuntimeEvent]:
        """
        Retrieves all stored events for the given job_id in ascending sequence order.
        """
        pass

    @abstractmethod
    async def events_after(
        self, job_id: str, sequence: int, limit: Optional[int] = None
    ) -> List[StoredRuntimeEvent]:
        """
        Retrieves events for the given job_id with sequence > `sequence` in ascending order.
        """
        pass

    @abstractmethod
    async def latest_sequence(self, job_id: str) -> int:
        """
        Returns the highest sequence number allocated for the given job_id, or 0 if no events exist.
        """
        pass

    @abstractmethod
    async def get_event(self, event_id: str) -> Optional[StoredRuntimeEvent]:
        """
        Retrieves a single stored event by its unique event_id.
        """
        pass

    @abstractmethod
    async def list_unfinished_jobs(self) -> List[str]:
        """
        Lists job IDs that have started but have not emitted a terminal job state event.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verifies that the event store backend is reachable and operating normally.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Closes any open connection pools or resources cleanly.
        """
        pass
