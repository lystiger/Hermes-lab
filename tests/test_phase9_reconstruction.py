from datetime import datetime, timezone
import pytest
import uuid

from runtime.job_state import JobRecord, JobState
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.execution import AgentRun, AgentRunStatus
from runtime.observations import Observation
from runtime.verification import VerificationResult, VerificationStatus
from runtime.storage.schema_registry import StoredRuntimeEvent, create_event
from runtime.storage.projector import RuntimeStateProjector, ReconstructedRuntimeState


def test_reconstruction_job_record():
    """Requirement F: Rebuild final JobRecord from events only."""
    job_id = "job_rec_001"
    now_iso = datetime.now(timezone.utc).isoformat()

    events = [
        create_event(
            job_id=job_id,
            sequence=1,
            event_type="job.created",
            payload={"goal": "Build authentication module", "title": "Auth Sprint", "priority": "P0", "repository": "hermes-lab", "branch": "main"},
            occurred_at="2026-08-25T10:00:00Z",
        ),
        create_event(
            job_id=job_id,
            sequence=2,
            event_type="job.state_changed",
            payload={"previous_state": "created", "new_state": "planning", "reason": "Initial plan decomposition"},
            occurred_at="2026-08-25T10:00:01Z",
        ),
        create_event(
            job_id=job_id,
            sequence=3,
            event_type="job.state_changed",
            payload={"previous_state": "planning", "new_state": "executing", "reason": "Plan ready"},
            occurred_at="2026-08-25T10:00:02Z",
        ),
        create_event(
            job_id=job_id,
            sequence=4,
            event_type="job.state_changed",
            payload={"previous_state": "executing", "new_state": "verifying", "reason": "All tasks completed"},
            occurred_at="2026-08-25T10:00:05Z",
        ),
        create_event(
            job_id=job_id,
            sequence=5,
            event_type="job.completed",
            payload={"detail": "Job completed successfully"},
            occurred_at="2026-08-25T10:00:10Z",
        ),
    ]

    state = RuntimeStateProjector.project(events)

    assert isinstance(state, ReconstructedRuntimeState)
    assert state.job.job_id == job_id
    assert state.job.goal == "Build authentication module"
    assert state.job.title == "Auth Sprint"
    assert state.job.priority == "P0"
    assert state.job.state == JobState.COMPLETED
    assert state.job.created_at == "2026-08-25T10:00:00Z"
    assert state.job.started_at == "2026-08-25T10:00:01Z"
    assert state.job.completed_at == "2026-08-25T10:00:10Z"


def test_reconstruction_task_graph():
    """Requirement G: Create task/dependency/state events, rebuild graph, compare state."""
    job_id = "job_rec_graph"

    events = [
        create_event(job_id=job_id, sequence=1, event_type="job.created", payload={"goal": "DAG Test"}),
        # Task 1
        create_event(
            job_id=job_id,
            sequence=2,
            event_type="task.created",
            task_id="T1",
            payload={"taskId": "T1", "description": "Scaffold DB", "dependencies": [], "requiredCapabilities": ["db"]},
        ),
        create_event(job_id=job_id, sequence=3, event_type="task.started", task_id="T1", actor_id="agent_1", payload={"taskId": "T1", "actorId": "agent_1"}),
        create_event(job_id=job_id, sequence=4, event_type="task.completed", task_id="T1", actor_id="agent_1", payload={"taskId": "T1", "artifactsCount": 1}),
        # Task 2 (depends on T1)
        create_event(
            job_id=job_id,
            sequence=5,
            event_type="task.created",
            task_id="T2",
            payload={"taskId": "T2", "description": "Implement API", "dependencies": ["T1"], "requiredCapabilities": ["fastapi"]},
        ),
        create_event(job_id=job_id, sequence=6, event_type="task.ready", task_id="T2", payload={"taskId": "T2"}),
        create_event(job_id=job_id, sequence=7, event_type="task.assigned", task_id="T2", actor_id="agent_2", payload={"taskId": "T2", "assignedActor": "agent_2"}),
        create_event(job_id=job_id, sequence=8, event_type="task.started", task_id="T2", actor_id="agent_2", payload={"taskId": "T2", "actorId": "agent_2"}),
        create_event(job_id=job_id, sequence=9, event_type="task.completed", task_id="T2", actor_id="agent_2", payload={"taskId": "T2"}),
        # Task 3 (superseded)
        create_event(
            job_id=job_id,
            sequence=10,
            event_type="task.created",
            task_id="T3_old",
            payload={"taskId": "T3_old", "description": "Old verify", "dependencies": ["T2"]},
        ),
        create_event(
            job_id=job_id,
            sequence=11,
            event_type="task.superseded",
            task_id="T3_old",
            payload={"taskId": "T3_old", "supersededBy": "T3_new", "reason": "Updated test framework"},
        ),
    ]

    state = RuntimeStateProjector.project(events)
    graph = state.graph

    assert graph.count() == 3
    t1 = graph.get_task("T1")
    assert t1.status == TaskStatus.SUCCEEDED
    assert t1.assigned_actor == "agent_1"

    t2 = graph.get_task("T2")
    assert t2.status == TaskStatus.SUCCEEDED
    assert t2.dependencies == ["T1"]
    assert t2.assigned_actor == "agent_2"

    t3 = graph.get_task("T3_old")
    assert t3.status == TaskStatus.SUPERSEDED
    assert t3.superseded_by == "T3_new"
    assert t3.supersede_reason == "Updated test framework"

    assert graph.is_all_completed() is True


def test_reconstruction_agent_runs():
    """Requirement H: Started -> succeeded/failed/timed-out/cancelled reconstruct correctly."""
    job_id = "job_rec_runs"

    events = [
        create_event(job_id=job_id, sequence=1, event_type="job.created", payload={"goal": "Runs Test"}),
        # Run 1: Succeeded
        create_event(
            job_id=job_id,
            sequence=2,
            event_type="agent.started",
            run_id="run_01",
            task_id="T1",
            actor_id="gemini",
            payload={"runId": "run_01", "taskId": "T1", "actorId": "gemini", "attempt": 1},
            occurred_at="2026-08-25T10:01:00Z",
        ),
        create_event(
            job_id=job_id,
            sequence=3,
            event_type="agent.finished",
            run_id="run_01",
            task_id="T1",
            actor_id="gemini",
            payload={"runId": "run_01", "taskId": "T1", "exitReason": "normal_completion"},
            occurred_at="2026-08-25T10:01:10Z",
        ),
        # Run 2: Failed
        create_event(
            job_id=job_id,
            sequence=4,
            event_type="agent.started",
            run_id="run_02",
            task_id="T2",
            actor_id="claude",
            payload={"runId": "run_02", "taskId": "T2", "actorId": "claude", "attempt": 1},
            occurred_at="2026-08-25T10:01:15Z",
        ),
        create_event(
            job_id=job_id,
            sequence=5,
            event_type="agent.failed",
            run_id="run_02",
            task_id="T2",
            actor_id="claude",
            payload={"runId": "run_02", "taskId": "T2", "error": "SyntaxError: unexpected EOF", "exitReason": "execution_failure"},
            occurred_at="2026-08-25T10:01:20Z",
        ),
        # Run 3: Timed Out
        create_event(
            job_id=job_id,
            sequence=6,
            event_type="agent.started",
            run_id="run_03",
            task_id="T2",
            actor_id="codex",
            payload={"runId": "run_03", "taskId": "T2", "actorId": "codex", "attempt": 2},
            occurred_at="2026-08-25T10:01:25Z",
        ),
        create_event(
            job_id=job_id,
            sequence=7,
            event_type="agent.timed_out",
            run_id="run_03",
            task_id="T2",
            actor_id="codex",
            payload={"runId": "run_03", "taskId": "T2", "timeoutSeconds": 30.0},
            occurred_at="2026-08-25T10:01:55Z",
        ),
    ]

    state = RuntimeStateProjector.project(events)
    assert len(state.runs) == 3

    r1 = state.get_run("run_01")
    assert r1.status == AgentRunStatus.SUCCEEDED
    assert r1.actor_id == "gemini"
    assert r1.exit_reason == "normal_completion"
    assert r1.started_at == "2026-08-25T10:01:00Z"
    assert r1.finished_at == "2026-08-25T10:01:10Z"

    r2 = state.get_run("run_02")
    assert r2.status == AgentRunStatus.FAILED
    assert r2.actor_id == "claude"
    assert "SyntaxError" in r2.error

    r3 = state.get_run("run_03")
    assert r3.status == AgentRunStatus.TIMED_OUT
    assert r3.actor_id == "codex"
    assert "Timed out" in r3.error


def test_reconstruction_observations_and_artifacts():
    """Requirement I: Observation and artifact history survives process-memory loss."""
    job_id = "job_rec_obs_art"

    events = [
        create_event(job_id=job_id, sequence=1, event_type="job.created", payload={"goal": "Obs Test"}),
        create_event(
            job_id=job_id,
            sequence=2,
            event_type="observation.created",
            task_id="T1",
            actor_id="gemini",
            payload={
                "observation_id": "obs_1001",
                "job_id": job_id,
                "kind": "discovery",
                "content": "Discovered legacy schema table: users_v1",
                "task_id": "T1",
                "actor_id": "gemini",
                "confidence": 0.95,
                "metadata": {"requires_follow_up": True},
            },
        ),
        create_event(
            job_id=job_id,
            sequence=3,
            event_type="artifact.created",
            task_id="T1",
            payload={
                "id": "art_commit_01",
                "type": "git_commit",
                "label": "feat(db): add migrations",
                "ref": "9a8b7c6d",
                "metadata": {"files_changed": 3},
            },
        ),
    ]

    state = RuntimeStateProjector.project(events)
    assert len(state.observations) == 1
    obs = state.get_observation("obs_1001")
    assert obs is not None
    assert obs.content == "Discovered legacy schema table: users_v1"
    assert obs.metadata["requires_follow_up"] is True

    assert len(state.artifacts) == 1
    assert state.artifacts[0]["id"] == "art_commit_01"
    assert state.artifacts[0]["ref"] == "9a8b7c6d"


def test_reconstruction_replan_and_repair_counters():
    """Requirement J & K: Replan / verification repair counters rebuild correctly."""
    job_id = "job_rec_replan_repair"

    events = [
        create_event(job_id=job_id, sequence=1, event_type="job.created", payload={"goal": "Counters Test"}),
        create_event(job_id=job_id, sequence=2, event_type="job.state_changed", payload={"previous_state": "created", "new_state": "planning"}),
        create_event(job_id=job_id, sequence=3, event_type="job.state_changed", payload={"previous_state": "planning", "new_state": "executing"}),
        # Replan 1
        create_event(job_id=job_id, sequence=4, event_type="job.state_changed", payload={"previous_state": "executing", "new_state": "planning", "reason": "Task failure replan"}),
        create_event(job_id=job_id, sequence=5, event_type="replan.requested", payload={"reason": "Task failure", "remainingBudget": 2}),
        create_event(job_id=job_id, sequence=6, event_type="replan.completed", payload={"mutationsCount": 1, "explanation": "Added fallback"}),
        create_event(job_id=job_id, sequence=7, event_type="job.state_changed", payload={"previous_state": "planning", "new_state": "executing"}),
        # Verification & Repair 1
        create_event(job_id=job_id, sequence=8, event_type="job.state_changed", payload={"previous_state": "executing", "new_state": "verifying"}),
        create_event(job_id=job_id, sequence=9, event_type="verification.failed", payload={"status": "REPAIRABLE", "summary": "1 test failed"}),
        create_event(job_id=job_id, sequence=10, event_type="job.state_changed", payload={"previous_state": "verifying", "new_state": "repairing", "reason": "Fix failing test"}),
        create_event(job_id=job_id, sequence=11, event_type="job.state_changed", payload={"previous_state": "repairing", "new_state": "executing"}),
        # Verification 2 -> Passed
        create_event(job_id=job_id, sequence=12, event_type="job.state_changed", payload={"previous_state": "executing", "new_state": "verifying"}),
        create_event(job_id=job_id, sequence=13, event_type="verification.passed", payload={"status": "PASSED", "summary": "All tests passed"}),
        create_event(job_id=job_id, sequence=14, event_type="job.completed", payload={"new_state": "completed"}),
    ]

    state = RuntimeStateProjector.project(events)
    assert state.job.state == JobState.COMPLETED
    assert state.job.replan_count == 1
    assert state.job.repair_count == 1
    assert state.last_verification is not None
    assert state.last_verification.status == VerificationStatus.PASSED
