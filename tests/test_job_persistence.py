import json
from unittest.mock import patch

import pytest

from jobs.job_service import ArtifactRefDTO, JobDetailDTO, JobPhaseDTO, JobService
from jobs.job_state_reducer import JobStateReducer


def make_job(status="COMPLETED", job_id="job-1"):
    return JobDetailDTO(
        id=job_id, sprintId="sprint", title="Durable job", repository="repo", branch="main",
        status=status, phases=[JobPhaseDTO("p1", "Build", 1, "builder", "codex", "SUCCEEDED")],
        tasks=[{"task_id": "t1"}], observations=[{"detail": "done"}],
        artifacts=[ArtifactRefDTO("commit", "git_commit", "Commit", "abc123")],
        verification={"status": "PASSED"}, errors=[{"error": "earlier attempt"}],
    )


def test_round_trip_preserves_summary_and_detail(tmp_path):
    service = JobService(runs_root=tmp_path)
    job = make_job()
    service.register_job(job)
    assert json.loads((tmp_path / job.id / "job.json").read_text()) == job.to_dict()
    recovered = JobService(runs_root=tmp_path)
    assert recovered.list_jobs() == service.list_jobs()
    assert recovered.get_job(job.id).to_dict() == job.to_dict()


def test_all_persisted_records_beyond_thirty_are_loaded(tmp_path):
    service = JobService(runs_root=tmp_path)
    for index in range(40):
        service.register_job(make_job(job_id=f"job-{index:02}"))
    recovered = JobService(runs_root=tmp_path)
    assert len(recovered.list_jobs(limit=100)) == 40
    assert recovered.list_jobs(limit=100) == service.list_jobs(limit=100)


def test_unchanged_job_reads_do_not_write_to_disk(tmp_path):
    service = JobService(runs_root=tmp_path)
    job = make_job()
    service.register_job(job)
    with patch("jobs.job_service.tempfile.NamedTemporaryFile") as temporary:
        assert service.get_job(job.id).to_dict() == job.to_dict()
        assert service.list_jobs() == [job.to_summary_dict()]
    temporary.assert_not_called()


@pytest.mark.parametrize("status", ["CREATED", "QUEUED", "PREPARING", "PLANNING", "RUNNING",
                                    "EXECUTING", "VERIFYING", "REPAIRING", "WAITING_FOR_CAPACITY"])
def test_restart_reconciles_and_persists_interrupted_job(tmp_path, status):
    service = JobService(runs_root=tmp_path)
    job = make_job(status)
    job.phases[0].status = "RUNNING"
    service.register_job(job)
    recovered = JobService(runs_root=tmp_path).get_job(job.id)
    assert recovered.status == "FAILED"
    assert recovered.errors[-1] == {"error": "interrupted by runtime restart"}
    assert recovered.completedAt
    assert recovered.phases[0].status == "FAILED"
    assert JobService(runs_root=tmp_path).get_job(job.id).to_dict() == recovered.to_dict()


@pytest.mark.parametrize("status", ["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"])
def test_terminal_status_survives_restart(tmp_path, status):
    service = JobService(runs_root=tmp_path)
    job = make_job(status)
    service.register_job(job)
    assert JobService(runs_root=tmp_path).get_job(job.id).to_dict() == job.to_dict()


@pytest.mark.parametrize("contents", ["{bad", "[]", '{"id": "bad"}'])
def test_corrupt_record_is_warned_and_skipped(tmp_path, caplog, contents):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "job.json").write_text(contents)
    service = JobService(runs_root=tmp_path)
    service.register_job(make_job())
    recovered = JobService(runs_root=tmp_path)
    assert len(recovered.list_jobs()) == 1
    assert "Could not recover job record" in caplog.text


def test_legacy_summary_beyond_thirty_is_recovered_without_duplicates(tmp_path):
    for index in range(40):
        directory = tmp_path / f"legacy_{index:02}"
        directory.mkdir()
        (directory / "run_summary.json").write_text(json.dumps({"sprint_id": str(index)}))
    service = JobService(runs_root=tmp_path)
    assert len(service.list_jobs(limit=100)) == 40
    assert service.get_job("run_legacy_00").status == "COMPLETED"
    assert JobService(runs_root=tmp_path).list_jobs(limit=100) == service.list_jobs(limit=100)


def test_record_takes_precedence_over_summary(tmp_path):
    service = JobService(runs_root=tmp_path)
    job = make_job(job_id="run_legacy")
    service.register_job(job)
    (tmp_path / job.id / "run_summary.json").write_text('{"status":"FAILED"}')
    assert JobService(runs_root=tmp_path).get_job(job.id).to_dict() == job.to_dict()


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_failed_atomic_write_preserves_previous_record(tmp_path, failure, caplog):
    service = JobService(runs_root=tmp_path)
    job = make_job()
    service.register_job(job)
    record = tmp_path / job.id / "job.json"
    previous = record.read_bytes()
    job.title = "Changed"
    with patch(f"jobs.job_service.os.{failure}", side_effect=OSError("disk failure")):
        service.persist_job(job)
    assert record.read_bytes() == previous
    assert list(record.parent.glob(".job-*.tmp")) == []
    assert "disk failure" in caplog.text
    service.persist_job(job)
    assert json.loads(record.read_text())["title"] == "Changed"


def test_reducer_persists_changes_without_endpoint_polling(tmp_path):
    service = JobService(runs_root=tmp_path)
    reducer = JobStateReducer(service)
    reducer.apply("job.created", "", job_id="job-1")
    reducer.apply("phase.started", "Build", job_id="job-1")
    reducer.apply("phase.completed", "Build", job_id="job-1")
    reducer.apply("job.completed", "", job_id="job-1")
    job = JobService(runs_root=tmp_path).get_job("job-1")
    assert job.status == "COMPLETED"
    assert job.phases[0].status == "SUCCEEDED"


def test_recovery_cap_uses_mtime_and_logs(tmp_path, monkeypatch, caplog):
    import os

    service = JobService(runs_root=tmp_path)
    for index, name in enumerate(["z-old", "a-new"]):
        service.register_job(make_job(job_id=name))
        os.utime(tmp_path / name, (100 + index, 100 + index))
    monkeypatch.setattr(JobService, "RECOVERY_LIMIT", 1)
    recovered = JobService(runs_root=tmp_path)
    assert [job["id"] for job in recovered.list_jobs()] == ["a-new"]
    assert "capped at 1" in caplog.text


@pytest.mark.anyio
async def test_reactive_changes_persist_without_polling(tmp_path):
    from runtime.engine import ReactiveJobEngine
    from runtime.events import RuntimeEventBridge
    from runtime.job_state import JobState
    from runtime.task_graph import TaskNode

    service = JobService(runs_root=tmp_path)
    bridge = RuntimeEventBridge()
    engine = ReactiveJobEngine(job_id="reactive", goal="Persist", event_bridge=bridge)
    service.register_engine(engine)
    await engine.initialize_and_plan(initial_tasks=[
        TaskNode(task_id="t1", job_id="reactive", description="Build")])
    record = tmp_path / "reactive" / "job.json"
    data = json.loads(record.read_text())
    assert data["tasks"][0]["task_id"] == "t1"
    assert data["status"] == engine.job.state.value.upper()
    previous = engine.job.state
    engine.job.state = JobState.FAILED
    await bridge.emit_job_state_changed(engine.job, previous, reason="test failure")
    assert json.loads(record.read_text())["status"] == "FAILED"


def test_unreadable_record_does_not_stop_recovery(tmp_path, caplog):
    from pathlib import Path

    service = JobService(runs_root=tmp_path)
    service.register_job(make_job())
    service.register_job(make_job(job_id="unreadable"))
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path.parent.name == "unreadable":
            raise PermissionError("permission denied")
        return original(path, *args, **kwargs)

    with patch.object(Path, "read_text", read):
        recovered = JobService(runs_root=tmp_path)
    assert [job["id"] for job in recovered.list_jobs()] == ["job-1"]
    assert "permission denied" in caplog.text


def test_legacy_migration_does_not_consume_recovery_cap_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(JobService, "RECOVERY_LIMIT", 3)
    for index in range(3):
        directory = tmp_path / f"legacy_{index}"
        directory.mkdir()
        (directory / "run_summary.json").write_text(json.dumps({"sprint_id": str(index)}))
    service = JobService(runs_root=tmp_path)
    job = service.get_job("run_legacy_0")
    job.title = "Persisted title absent from the legacy summary"
    service.persist_job(job)
    first = service.list_jobs(limit=100)
    assert len(first) == 3
    # Migration creates run_legacy_* record folders alongside the legacy folders.
    # Make the original summaries newest so a folder-based cap excludes all records.
    import os
    for index in range(3):
        os.utime(tmp_path / f"legacy_{index}", (2000000000, 2000000000))
    second = JobService(runs_root=tmp_path).list_jobs(limit=100)
    assert second == first


def test_restart_reconciles_running_task_records(tmp_path):
    from runtime.task_graph import TaskNode, TaskStatus

    service = JobService(runs_root=tmp_path)
    job = make_job("RUNNING")
    job.phases[0].status = "RUNNING"
    job.tasks = [TaskNode(task_id="t1", status=TaskStatus.RUNNING).to_dict(),
                 TaskNode(task_id="t2", status=TaskStatus.SUCCEEDED).to_dict()]
    completed_task = dict(job.tasks[1])
    service.register_job(job)
    recovered = JobService(runs_root=tmp_path)
    tasks = recovered.get_job_tasks(job.id)
    assert tasks[0]["status"] == "FAILED"
    assert tasks[0]["completed_at"] == recovered.get_job(job.id).completedAt
    assert tasks[1] == completed_task
    assert JobService(runs_root=tmp_path).get_job_tasks(job.id) == tasks


@pytest.mark.anyio
async def test_reactive_observation_survives_restart_without_polling(tmp_path):
    from runtime.engine import ReactiveJobEngine
    from runtime.events import RuntimeEventBridge
    from runtime.observations import ObservationRegistry

    service = JobService(runs_root=tmp_path)
    registry = ObservationRegistry()
    bridge = RuntimeEventBridge()
    engine = ReactiveJobEngine(job_id="observed", goal="Persist observations",
                               event_bridge=bridge, observation_registry=registry)
    service.register_engine(engine)
    observation = registry.add_observation(job_id="observed", kind="discovery", content="Keep me")
    await bridge.emit_observation_created(observation)
    data = json.loads((tmp_path / "observed" / "job.json").read_text())
    assert data["observations"] == [observation.to_dict()]
    assert JobService(runs_root=tmp_path).get_job_observations("observed") == [observation.to_dict()]
