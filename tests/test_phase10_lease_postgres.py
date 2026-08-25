import os
import pytest
from datetime import datetime, timezone
from runtime.lease import InMemoryJobLeaseStore, PostgresJobLeaseStore, JobLeaseStore


@pytest.mark.anyio
async def test_in_memory_job_lease_store_lifecycle():
    store = InMemoryJobLeaseStore()
    
    # Acquire lease
    acquired = await store.acquire_lease("job_l1", "node_1", duration_seconds=10.0)
    assert acquired is True

    # Check lease
    lease = await store.get_lease("job_l1")
    assert lease is not None
    assert lease.owner_id == "node_1"
    assert lease.is_active() is True

    # Renew lease
    renewed = await store.renew_lease("job_l1", "node_1", duration_seconds=20.0)
    assert renewed is True

    # Failed renewal by another node
    renew_failed = await store.renew_lease("job_l1", "node_2", duration_seconds=20.0)
    assert renew_failed is False

    # Release lease
    released = await store.release_lease("job_l1", "node_1")
    assert released is True

    # Post release
    lease_after = await store.get_lease("job_l1")
    assert lease_after is None


@pytest.mark.anyio
async def test_postgres_job_lease_store_integration():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url or "postgres" not in db_url.lower():
        pytest.skip("DATABASE_URL not set or not postgres")

    store = PostgresJobLeaseStore(db_url)
    
    try:
        # Acquire lease
        acquired = await store.acquire_lease("pg_job_l1", "pg_node_1", duration_seconds=10.0)
        assert acquired is True

        # Check lease
        lease = await store.get_lease("pg_job_l1")
        assert lease is not None
        assert lease.owner_id == "pg_node_1"

        # Renew lease
        renewed = await store.renew_lease("pg_job_l1", "pg_node_1", duration_seconds=20.0)
        assert renewed is True

        # Failed acquire by another node
        blocked = await store.acquire_lease("pg_job_l1", "pg_node_2", duration_seconds=10.0)
        assert blocked is False

        # Release lease
        released = await store.release_lease("pg_job_l1", "pg_node_1")
        assert released is True
    finally:
        await store.close()
