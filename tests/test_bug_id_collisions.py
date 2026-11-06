"""
Bug: runtime/replanning.py builds generated task ids from int(time.time()) alone, and
jobs/job_launcher.py builds the sprint job id from time.strftime("%Y%m%d_%H%M%S") alone.
Two ids generated within the same second collide.
"""
import asyncio
import json
import subprocess
import time

from jobs.job_launcher import JobLauncher
from runtime.replanning import ProductionPlannerAdapter, ReplanReason, ReplanRequest
from runtime.task_graph import TaskGraph

FIXED_EPOCH = 1_800_000_000.0
FIXED_STAMP = "20270115_093000"


class _FakeProc:
    pid = 4242

    def poll(self):
        return None


def _plan_verification_repair_task_id():
    request = ReplanRequest(
        job_id="job_ids", goal="g", reason=ReplanReason.VERIFICATION_REPAIR, completed_tasks=[],
        failed_tasks=[], current_graph=TaskGraph(job_id="job_ids"), new_observations=[],
        produced_artifacts=[], replan_budget_remaining=2,
    )
    [mutation] = asyncio.run(ProductionPlannerAdapter().plan(request)).mutations
    return mutation.task.task_id


def test_generated_ids_differ_within_same_second(monkeypatch, tmp_path):
    monkeypatch.setattr(time, "time", lambda: FIXED_EPOCH)
    monkeypatch.setattr(time, "strftime", lambda fmt, *args: FIXED_STAMP)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: _FakeProc())

    sprints_dir = tmp_path / "sprints"
    sprints_dir.mkdir()
    (sprints_dir / "sprint_ids.json").write_text(json.dumps({"name": "ids", "phases": []}), encoding="utf-8")
    launcher = JobLauncher(sprints_dir=sprints_dir)
    launcher.root_dir = tmp_path

    def launch_job_id():
        return launcher.launch(
            "sprint_ids",
            dry_run=True,
            mode="legacy_static_runner",
            control_url_override="http://127.0.0.1:9",
        )["jobId"]

    assert _plan_verification_repair_task_id() != _plan_verification_repair_task_id()
    assert launch_job_id() != launch_job_id()
