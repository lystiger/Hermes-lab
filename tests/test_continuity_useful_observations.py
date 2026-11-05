from pathlib import Path
import threading
import pytest
from runtime.hermes_adapter import HermesActorAdapter
from runtime.task_graph import TaskNode
from runtime.observations import Observation
from runtime.execution import AgentRun


def test_real_run_completion_observation_formatting_few_files():
    """Verify changed files formatting for up to 20 files with git status prefixes cleaned."""
    files = [" M src/app.py", "?? tests/test_app.py", "A  docs/readme.md"]
    formatted = HermesActorAdapter._format_completion_files(files)
    assert formatted == "src/app.py, tests/test_app.py, docs/readme.md"


def test_real_run_completion_observation_formatting_more_than_twenty_files():
    """Verify formatting when more than 20 files changed: names 20, then 'and N more'."""
    files = [f"src/module_{i:02d}.py" for i in range(25)]
    formatted = HermesActorAdapter._format_completion_files(files, limit=20)

    # First 20 files are named
    for i in range(20):
        assert f"src/module_{i:02d}.py" in formatted

    # The 21st through 25th files are not named directly
    for i in range(20, 25):
        assert f"src/module_{i:02d}.py" not in formatted

    # Truncation suffix
    assert formatted.endswith(", and 5 more")

    # Edge case: exactly 21 files -> 'and 1 more'
    files_21 = [f"src/module_{i:02d}.py" for i in range(21)]
    formatted_21 = HermesActorAdapter._format_completion_files(files_21, limit=20)
    assert formatted_21.endswith(", and 1 more")

    # Edge case: exactly 20 files -> no 'and N more'
    files_20 = [f"src/module_{i:02d}.py" for i in range(20)]
    formatted_20 = HermesActorAdapter._format_completion_files(files_20, limit=20)
    assert "and" not in formatted_20


def test_is_completion_boilerplate_identification():
    """Verify identification of routine completion boilerplate."""
    # Dry run boilerplate
    assert HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Task t1 completed dry-run execution by antigravity")
    )
    assert HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Task completed dry-run execution")
    )
    assert HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Task t1 completed dry-run execution by antigravity", metadata={"dry_run": True})
    )
    assert HermesActorAdapter.is_completion_boilerplate(
        {"content": "Task t1_fix completed dry-run execution by antigravity"}
    )

    # Bare exit code boilerplate
    assert HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Agent antigravity completed task t1 with exit code 0")
    )
    assert HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Agent completed with exit code 0")
    )
    assert HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Task t1 completed with exit code 0")
    )
    assert HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Agent antigravity completed task t1 with exit code 1")
    )

    # Useful observations (must NOT be treated as boilerplate)
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Agent antigravity completed task t1 (commit c0ffee12): src/app.py")
    )
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Agent antigravity completed task t1 (commit c0ffee12)")
    )
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Discovered Stripe API version is 2026-08-01")
    )
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="ZeroDivisionError: division by zero", kind="verification_failure")
    )
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Context pressure handoff at 88.0% context window.", kind="continuity_handoff")
    )
    # Observations containing useful discoveries alongside completion text must NOT be treated as boilerplate
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Task t1 completed dry-run execution by antigravity. Database migration 004 required before running tests")
    )
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(
            content="Task t1 completed dry-run execution by antigravity. Database migration 004 required before running tests",
            metadata={"dry_run": True},
        )
    )
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="completed dry-run execution\nUseful migration discovery: add column user_id")
    )
    assert not HermesActorAdapter.is_completion_boilerplate(
        Observation(content="Agent antigravity completed task t1 with exit code 0. Discovered migration needed")
    )


def test_build_continuity_section_omits_when_only_boilerplate_remains():
    """Verify continuity section is completely omitted when only boilerplate observations exist."""
    adapter = HermesActorAdapter()
    task = TaskNode(
        task_id="t2_useful_continuity",
        job_id="job_test",
        description="Write new feature",
        attempt=0,
    )

    boilerplate_obs = [
        Observation(
            job_id="job_test",
            task_id="t1",
            kind="discovery",
            content="Task t1 completed dry-run execution by antigravity",
            metadata={"dry_run": True},
        ),
        Observation(
            job_id="job_test",
            task_id="t1",
            kind="execution_output",
            content="Agent antigravity completed task t1 with exit code 0",
        ),
    ]

    # Section is empty string
    section = adapter.build_continuity_section(task, observations=boilerplate_obs)
    assert section == ""

    # Effective prompt completely omits continuity section
    prompt = adapter.build_effective_prompt(
        base_prompt="Do the task work.",
        current_agent="claude",
        role="builder",
        task=task,
        observations=boilerplate_obs,
    )
    assert "--- LYSSTACK CONTINUITY CONTEXT ---" not in prompt
    assert "--- END CONTINUITY CONTEXT ---" not in prompt
    assert "Do the task work." in prompt


def test_build_continuity_section_retains_useful_observations():
    """Verify useful observations are retained while boilerplate is excluded."""
    adapter = HermesActorAdapter()
    task = TaskNode(
        task_id="t2_useful_continuity",
        job_id="job_test",
        description="Verify changes",
        attempt=0,
    )

    mixed_obs = [
        Observation(
            job_id="job_test",
            task_id="t1",
            kind="discovery",
            content="Task t1 completed dry-run execution by antigravity",
            metadata={"dry_run": True},
        ),
        Observation(
            job_id="job_test",
            task_id="t1",
            kind="execution_output",
            content="Agent antigravity completed task t1 (commit sha_123456): src/core.py, tests/test_core.py",
        ),
        Observation(
            job_id="job_test",
            task_id="t1",
            kind="discovery",
            content="Database migration 004 required before running tests",
        ),
    ]

    section = adapter.build_continuity_section(task, observations=mixed_obs)
    assert "--- LYSSTACK CONTINUITY CONTEXT ---" in section
    assert "completed dry-run execution" not in section
    assert "Agent antigravity completed task t1 (commit sha_123456): src/core.py, tests/test_core.py" in section
    assert "Database migration 004 required before running tests" in section
    assert "--- END CONTINUITY CONTEXT ---" in section


def test_build_continuity_section_retains_observation_with_dry_run_and_useful_discovery():
    """Verify that an observation containing both dry-run completion text and a useful discovery is retained."""
    adapter = HermesActorAdapter()
    task = TaskNode(
        task_id="t2_useful_continuity",
        job_id="job_test",
        description="Verify changes",
        attempt=0,
    )

    obs = [
        Observation(
            job_id="job_test",
            task_id="t1",
            kind="discovery",
            content="Task t1 completed dry-run execution by antigravity. Database migration 004 required before running tests",
            metadata={"dry_run": True},
        )
    ]

    section = adapter.build_continuity_section(task, observations=obs)
    assert "--- LYSSTACK CONTINUITY CONTEXT ---" in section
    assert "Database migration 004 required before running tests" in section
    assert "--- END CONTINUITY CONTEXT ---" in section


def test_build_continuity_section_preserves_reroute_and_failure_when_obs_are_boilerplate():
    """Verify reroute notice and failure error remain even when all observations are boilerplate."""
    adapter = HermesActorAdapter()

    # Task with reroute metadata
    task_reroute = TaskNode(
        task_id="t2",
        job_id="job_test",
        description="Work",
        attempt=0,
        metadata={"previous_actor": "antigravity", "last_reroute_reason": "rate_limited"},
    )
    dry_obs = [Observation(content="Task t1 completed dry-run execution by antigravity")]
    sec_reroute = adapter.build_continuity_section(task_reroute, observations=dry_obs)
    assert "--- LYSSTACK CONTINUITY CONTEXT ---" in sec_reroute
    assert "[Reroute Notice] Execution rerouted from 'antigravity'. Reason: rate_limited" in sec_reroute
    assert "[Previous Attempt Discoveries & Observations]" not in sec_reroute

    # Task with retry error
    task_retry = TaskNode(
        task_id="t2",
        job_id="job_test",
        description="Work",
        attempt=1,
        error="SyntaxError: invalid syntax at line 10",
    )
    sec_retry = adapter.build_continuity_section(task_retry, observations=dry_obs)
    assert "--- LYSSTACK CONTINUITY CONTEXT ---" in sec_retry
    assert "[Previous Failure (Attempt 1)]" in sec_retry
    assert "SyntaxError: invalid syntax at line 10" in sec_retry
    assert "[Previous Attempt Discoveries & Observations]" not in sec_retry


def test_real_agent_completion_observation_content_and_metadata(tmp_path):
    """Verify _execute_real_agent constructs completion observation with commit sha and files."""
    adapter = HermesActorAdapter(
        target_repo=tmp_path,
        worktree_root=tmp_path / "wt",
        run_dir=tmp_path / "runs",
        dry_run=False,
        skip_agent_exec=False,
    )

    task = TaskNode(
        task_id="t1_build",
        job_id="job_real",
        description="Build auth service",
        assigned_actor="antigravity",
        metadata={"role": "builder"},
    )
    run = AgentRun(run_id="run_1", job_id="job_real", task_id="t1_build", actor_id="antigravity")

    adapter.ensure_integration_worktree = lambda: None
    adapter._resolve_backend_name = lambda *a, **k: "mock"
    adapter._task_event_sink = lambda *a, **k: (lambda ev: None)
    adapter._ensure_worktree = lambda *a, **k: tmp_path / "fake_wt"
    adapter._seed_dependencies = lambda *a, **k: None
    adapter.sync_task_worktree_from_integration = lambda *a, **k: None
    adapter._prepare_effective_prompt = lambda *a, **k: "fake prompt"
    adapter._save_effective_prompt = lambda *a, **k: None
    adapter.run_dir = tmp_path / "fake_runs"
    adapter.target_subdir = ""
    adapter.build_tool_job_config = lambda *a, **k: {}
    adapter.tool_registry = None

    class MockAgentAdapter:
        def execute(self, ctx):
            class Res:
                returncode = 0
                stdout = "done"
                stderr = ""
                runtime_metadata = {}
            return Res()

    class MockAgentRegistry:
        def get(self, name):
            return MockAgentAdapter()

    class MockBackendRegistry:
        def get(self, name, **kwargs):
            return None

    adapter.agent_registry = MockAgentRegistry()
    adapter.backend_registry = MockBackendRegistry()
    adapter.validate_python_syntax = lambda *a, **k: None
    adapter.inspect_changed_files = lambda *a, **k: [" M auth/login.py", "?? auth/models.py"]
    adapter._commit_and_integrate_changes = lambda *a, **k: "d3b07384d113edec49eaa6238ad5ff00"

    res = adapter._execute_real_agent(task, run, "antigravity", "builder")
    assert res.status == "succeeded"
    assert len(res.observations) == 1
    obs = res.observations[0]
    assert obs.kind == "execution_output"
    assert obs.content == "Agent antigravity completed task t1_build (commit d3b07384d113edec49eaa6238ad5ff00): auth/login.py, auth/models.py"
    assert "with exit code 0" not in obs.content
    assert obs.metadata["commit_sha"] == "d3b07384d113edec49eaa6238ad5ff00"
    assert obs.metadata["changed_files"] == ["auth/login.py", "auth/models.py"]

    # When > 20 files are changed
    files_25 = [f" M mod_{i}.py" for i in range(25)]
    adapter.inspect_changed_files = lambda *a, **k: files_25
    res2 = adapter._execute_real_agent(task, run, "antigravity", "builder")
    obs2 = res2.observations[0]
    assert "and 5 more" in obs2.content
    assert "commit d3b07384d113edec49eaa6238ad5ff00" in obs2.content

