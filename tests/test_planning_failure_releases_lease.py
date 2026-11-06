"""Bug 8 test.

Bug 8: fixed (test_planning_exception_cancels_heartbeat_releases_lease_and_fails_job) - reproduced and fixed.
Not marked not reproduced.
"""

import asyncio

import pytest

import runtime.storage.config as storage_config
from jobs.job_launcher import JobLauncher
from jobs.job_service import job_service
from runtime.engine import ReactiveJobEngine
from runtime.lease import InMemoryJobLeaseStore, JobLeaseManager


@pytest.mark.anyio
async def test_planning_exception_cancels_heartbeat_releases_lease_and_fails_job(tmp_path, monkeypatch):
    """
    When planning raises, jobs/job_launcher.py (launch_goal_background, around line 675) ends the
    driver but leaves the lease heartbeat running and the lease held, and the job is not recorded
    as failed. The heartbeat must be cancelled, the lease released and the job marked FAILED.
    """
    store = InMemoryJobLeaseStore()
    monkeypatch.setattr(storage_config, "_GLOBAL_LEASE_STORE", store)

    heartbeats = []
    original_heartbeat = JobLeaseManager._heartbeat_loop

    async def recording_heartbeat(self, job_id):
        heartbeats.append(asyncio.current_task())
        await original_heartbeat(self, job_id)

    monkeypatch.setattr(JobLeaseManager, "_heartbeat_loop", recording_heartbeat)

    async def failing_plan(self, initial_tasks=None):
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr(ReactiveJobEngine, "initialize_and_plan", failing_plan)

    launcher = JobLauncher()
    res = launcher.launch_goal_background(goal="Add an API", target_repo=tmp_path, dry_run=True)
    job_id = res["jobId"]
    try:
        await launcher._active_async_tasks[job_id]
        await asyncio.sleep(0)  # the heartbeat task starts on the loop after the planner task ends

        assert len(heartbeats) == 1
        heartbeat = heartbeats[0]
        await asyncio.wait({heartbeat}, timeout=1)
        assert heartbeat.done(), "lease heartbeat is still running after planning failed"

        assert await store.get_lease(job_id) is None, "execution lease is still held after planning failed"
        assert job_service.get_job(job_id).status == "FAILED"
    finally:
        for task in heartbeats:
            task.cancel()
