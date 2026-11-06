"""
Bug: a provider reset time that has already passed (and was never cleared) makes
ReactiveJobEngine._capacity_wait_seconds return the 0.01s floor, so a job waiting for
capacity spins at roughly 100 steps per second instead of waiting.
"""
from datetime import datetime, timedelta, timezone

import pytest

import runtime.engine as engine_module
from runtime.capacity import CapacityRegistry
from runtime.engine import ReactiveJobEngine
from runtime.job_state import JobState

FROZEN_NOW = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW


@pytest.mark.anyio
async def test_capacity_wait_ignores_expired_reset_time(monkeypatch):
    """
    With the only provider reset time an hour in the past, repeated capacity-wait steps must
    sleep for a bounded interval, not the 0.01s floor that produces a busy loop.
    """
    monkeypatch.setattr(engine_module, "datetime", _FrozenDatetime)

    sleeps = []

    async def fake_sleep(seconds, *args, **kwargs):
        sleeps.append(seconds)

    monkeypatch.setattr(engine_module.asyncio, "sleep", fake_sleep)

    registry = CapacityRegistry()
    registry.register_actor_provider("claude_sonnet", "anthropic")
    registry._provider_reset_at["anthropic"] = FROZEN_NOW - timedelta(hours=1)

    engine = ReactiveJobEngine(
        job_id="job_expired_reset",
        goal="wait for capacity",
        capacity_registry=registry,
    )
    engine.job.state = JobState.WAITING_FOR_CAPACITY

    for _ in range(5):
        assert await engine.step() is True

    assert len(sleeps) == 5
    # Expired reset times must be dropped; a wait of 0.01s per step is the busy-loop regression.
    assert all(seconds >= 1.0 for seconds in sleeps), sleeps
