from jobs.job_service import JobService
from jobs.job_state_reducer import JobStateReducer

PHASES = [
    {"name": "build", "role": "builder", "agent": "claude"},
    {"name": "harden", "role": "hardener", "agent": "codex"},
    {"name": "harden-2", "role": "hardener", "agent": "gemini"},
    {"name": "verify", "role": "verifier", "agent": "claude"},
]


def make_reducer(tmp_path):
    reducer = JobStateReducer(JobService(runs_root=tmp_path))
    reducer.apply("job.created", "", job_id="job-1", metadata={"phases": PHASES})
    return reducer


def phase_event(reducer, kind, order, **extra):
    spec = PHASES[order - 1]
    reducer.apply(
        kind, "", job_id="job-1", source_id=spec["agent"],
        metadata={"phase": spec["name"], "role": spec["role"], "agent": spec["agent"], "order": order, **extra},
    )


def test_phases_with_the_same_role_keep_separate_rows(tmp_path):
    reducer = make_reducer(tmp_path)
    phase_event(reducer, "phase.started", 2)
    phase_event(reducer, "phase.completed", 2)
    phase_event(reducer, "phase.started", 3)

    job = reducer._service.get_job("job-1")
    assert [p.name for p in job.phases] == ["build", "harden", "harden-2", "verify"]
    assert [p.status for p in job.phases] == ["PENDING", "SUCCEEDED", "RUNNING", "PENDING"]
    assert job.phases[2].agentId == "gemini"
    assert job.phases[1].completedAt and job.phases[2].startedAt


def test_completion_does_not_match_a_phase_by_substring(tmp_path):
    reducer = make_reducer(tmp_path)
    phase_event(reducer, "phase.started", 2)
    phase_event(reducer, "phase.started", 3)
    phase_event(reducer, "phase.failed", 3, error="boom")

    job = reducer._service.get_job("job-1")
    assert job.phases[1].status == "RUNNING"
    assert job.phases[2].status == "FAILED"


def test_task_assignment_keeps_the_phase_role(tmp_path):
    reducer = make_reducer(tmp_path)
    phase_id = reducer._service.get_job("job-1").phases[1].id
    reducer.apply("task.assigned", "", job_id="job-1", metadata={"taskId": phase_id, "assignedActor": "gemini"})

    phase = reducer._service.get_job("job-1").phases[1]
    assert phase.role == "hardener"
    assert phase.agentId == "gemini"


def test_unknown_phase_is_inserted_at_its_order(tmp_path):
    reducer = JobStateReducer(JobService(runs_root=tmp_path))
    reducer.apply("phase.started", "", job_id="job-1", metadata={"phase": "verify", "role": "verifier", "order": 2})
    reducer.apply("phase.started", "", job_id="job-1", metadata={"phase": "build", "role": "builder", "order": 1})

    job = reducer._service.get_job("job-1")
    assert [(p.order, p.name, p.role) for p in job.phases] == [(1, "build", "builder"), (2, "verify", "verifier")]
