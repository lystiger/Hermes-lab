"""Bug 7 test.

Bug 7: fixed (test_interrupted_planning_or_repairing_resumes_explicitly) - reproduced and fixed.
Not marked not reproduced.
"""

import pytest

from runtime.job_state import JobRecord, JobState
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.events import RuntimeEventBridge
from runtime.engine import ReactiveJobEngine
from capabilities.capabilities import CapabilityRegistry


def create_test_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register_actor({
        "id": "actor_code",
        "name": "Code Actor",
        "capabilities": ["code.edit", "code.review"],
    })
    return reg


@pytest.mark.anyio
@pytest.mark.parametrize("interrupted_state", [JobState.PLANNING, JobState.REPAIRING])
async def test_interrupted_planning_or_repairing_resumes_explicitly(interrupted_state):
    """
    A job interrupted in PLANNING or REPAIRING must resume explicitly after recovery.
    runtime/recovery.py (around line 298) has a no-op branch for these states, so the
    rehydrated engine stays in a state that engine.step() does not advance: step()
    returns False, and run_until_complete() then marks the job BLOCKED with
    "Execution exceeded maximum step limit" although no step was spent.
    """
    store = InMemoryRuntimeEventStore()
    bridge = RuntimeEventBridge(event_store=store)

    job = JobRecord(job_id=f"job_rec_{interrupted_state.value}", goal="Repair the auth module")
    await bridge.emit_job_created(job)
    job.state = interrupted_state
    await bridge.emit_job_state_changed(job, previous_state=JobState.CREATED)

    engine, _ = await ReactiveJobEngine.resume(
        job_id=job.job_id,
        event_store=store,
        capability_registry=create_test_registry(),
    )

    advanced = await engine.step()

    assert advanced is True
    assert engine.job.state != JobState.BLOCKED
    assert "step limit" not in str(engine.job.blocked_reason or "")
