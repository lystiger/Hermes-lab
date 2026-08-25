import os
import logging
from typing import Any, Optional
from runtime.storage.event_store import RuntimeEventStore, StorageUnavailableError
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.postgres_store import PostgresRuntimeEventStore

logger = logging.getLogger("hermes.runtime.storage.config")

_GLOBAL_EVENT_STORE: Optional[RuntimeEventStore] = None
_GLOBAL_LEASE_STORE: Optional[Any] = None


def get_database_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL") or os.environ.get("HERMES_DATABASE_URL")


def get_storage_backend() -> str:
    explicit = os.environ.get("HERMES_STORAGE_BACKEND")
    if explicit:
        return explicit.lower()
    return "postgres" if get_database_url() else "memory"


def create_event_store(
    database_url: Optional[str] = None,
    backend: Optional[str] = None,
) -> RuntimeEventStore:
    """
    Factory creating a RuntimeEventStore instance.
    If Postgres backend is selected or DATABASE_URL is present, creates PostgresRuntimeEventStore.
    Otherwise creates InMemoryRuntimeEventStore.
    """
    selected_backend = backend or get_storage_backend()
    db_url = database_url or get_database_url()

    if selected_backend == "postgres":
        if not db_url:
            raise ValueError(
                "PostgreSQL storage backend configured but no DATABASE_URL provided."
            )
        logger.info("Initializing PostgresRuntimeEventStore with configured database URL")
        return PostgresRuntimeEventStore(database_url=db_url)

    logger.info("Initializing InMemoryRuntimeEventStore (in-memory test/dev mode)")
    return InMemoryRuntimeEventStore()


def get_global_event_store() -> RuntimeEventStore:
    global _GLOBAL_EVENT_STORE
    if _GLOBAL_EVENT_STORE is None:
        _GLOBAL_EVENT_STORE = create_event_store()
    return _GLOBAL_EVENT_STORE


def set_global_event_store(store: RuntimeEventStore) -> None:
    global _GLOBAL_EVENT_STORE
    _GLOBAL_EVENT_STORE = store


def create_lease_store(
    database_url: Optional[str] = None,
    backend: Optional[str] = None,
) -> Any:
    """
    Factory creating a JobLeaseStore instance.
    """
    selected_backend = backend or get_storage_backend()
    db_url = database_url or get_database_url()

    if selected_backend == "postgres":
        if not db_url:
            raise ValueError(
                "PostgreSQL storage backend configured but no DATABASE_URL provided."
            )
        from runtime.lease import PostgresJobLeaseStore
        logger.info("Initializing PostgresJobLeaseStore with configured database URL")
        return PostgresJobLeaseStore(db_url)

    from runtime.lease import InMemoryJobLeaseStore
    logger.info("Initializing InMemoryJobLeaseStore (in-memory test/dev mode)")
    return InMemoryJobLeaseStore()


def get_global_lease_store() -> Any:
    global _GLOBAL_LEASE_STORE
    if _GLOBAL_LEASE_STORE is None:
        _GLOBAL_LEASE_STORE = create_lease_store()
    return _GLOBAL_LEASE_STORE


def set_global_lease_store(store: Any) -> None:
    global _GLOBAL_LEASE_STORE
    _GLOBAL_LEASE_STORE = store


async def init_storage_lifespan() -> RuntimeEventStore:
    """
    Initializes and validates the global event store at application startup.
    Fails explicitly if configured persistence is unavailable (no silent in-memory fallback).
    """
    store = get_global_event_store()
    if getattr(store, "_closed", False):
        if isinstance(store, InMemoryRuntimeEventStore):
            store._closed = False
        else:
            set_global_event_store(create_event_store())
            store = get_global_event_store()

    backend = get_storage_backend()
    if backend == "postgres":
        is_healthy = await store.health_check()
        if not is_healthy:
            raise StorageUnavailableError(
                f"Configured PostgreSQL database is unavailable at startup. Failing fast to prevent silent durability loss."
            )
        logger.info("PostgreSQL storage connectivity verified successfully.")
    return store
