"""Execution-backend contract tests.

These pin the boundary a future sessionful backend (e.g. a persistent-seat runtime)
must fit behind without changes to the scheduler, runtime, or sprint runner:

- a new backend registers by name only; callers never branch on its type
- execute(request) -> ExecutionResult is the only per-run call
- callers that obtain a backend instance own calling cleanup() exactly once
- timeouts surface as SprintRunnerError("FAILED_TIMEOUT")
- runtime_metadata is an open mapping that callers pass through
"""

import asyncio
import importlib.util
import subprocess
from pathlib import Path

import pytest

from agents.errors import SprintRunnerError as BackendSprintRunnerError
from runner.agents.base import AgentAdapter
from runner.agents.errors import SprintRunnerError
from runner.agents.registry import AgentRegistry
from runner.backends.base import ExecutionBackend, ExecutionRequest, ExecutionResult
from runner.backends.registry import BackendRegistry, default_backend_registry
from runtime.execution import AgentRun
from runtime.hermes_adapter import HermesActorAdapter
from runtime.task_graph import TaskNode


RUNNER_PATH = Path(__file__).resolve().parent.parent / "runner" / "run-hermes-sprint.py"
SPEC = importlib.util.spec_from_file_location("run_hermes_sprint_contract", RUNNER_PATH)
RUNNER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER_MODULE)
HermesSprintRunner = RUNNER_MODULE.HermesSprintRunner


class FakeSessionfulBackend(ExecutionBackend):
    """Stands in for a backend that allocates a persistent seat per instance."""

    name = "fake-sessionful"
    instances = []

    def __init__(self, fail_with=None, **kwargs):
        self.kwargs = kwargs
        self.fail_with = fail_with
        self.seat_id = None
        self.requests = []
        self.cleanup_calls = []
        FakeSessionfulBackend.instances.append(self)

    def execute(self, request):
        self.requests.append(request)
        if self.seat_id is None:
            self.seat_id = f"seat-{len(FakeSessionfulBackend.instances)}"
        if self.fail_with is not None:
            raise self.fail_with
        request.stdout_file.parent.mkdir(parents=True, exist_ok=True)
        request.stdout_file.write_text("ok", encoding="utf-8")
        request.stderr_file.write_text("", encoding="utf-8")
        return ExecutionResult(
            command=tuple(request.command),
            returncode=0,
            stdout="ok",
            stderr="",
            backend=self.name,
            runtime_metadata={"session_id": "sess-1", "seat_id": self.seat_id},
        )

    def cleanup(self, success=False):
        self.cleanup_calls.append(success)
        self.seat_id = None


class EchoAdapter(AgentAdapter):
    name = "echo"

    def build_command(self, prompt, options, worktree=None):
        return ["echo", prompt]

    def validate_result(self, result, context):
        pass


@pytest.fixture(autouse=True)
def _reset_instances():
    FakeSessionfulBackend.instances = []
    yield
    FakeSessionfulBackend.instances = []


def make_request(tmp_path):
    return ExecutionRequest(
        agent_name="echo",
        command=("echo", "hi"),
        cwd=tmp_path,
        timeout_seconds=5,
        stdout_file=tmp_path / "out.log",
        stderr_file=tmp_path / "err.log",
    )


# --- registry -----------------------------------------------------------------


def test_default_registry_exposes_only_builtin_backends():
    assert default_backend_registry.supported_backends == ("herdr", "openrig", "subprocess")


def test_new_backend_registers_by_name_and_receives_construction_kwargs(tmp_path):
    registry = BackendRegistry()
    registry.register(FakeSessionfulBackend)

    backend = registry.get("fake-sessionful", run_dir=tmp_path, sprint_id="s1", logger=None)

    assert isinstance(backend, FakeSessionfulBackend)
    assert backend.kwargs == {"run_dir": tmp_path, "sprint_id": "s1", "logger": None}
    assert "fake-sessionful" in registry.supported_backends


def test_registry_returns_a_fresh_owned_instance_per_get(tmp_path):
    registry = BackendRegistry({FakeSessionfulBackend.name: FakeSessionfulBackend})
    assert registry.get("fake-sessionful") is not registry.get("fake-sessionful")


def test_registry_accepts_factory_callables(tmp_path):
    registry = BackendRegistry({"leased": lambda **kwargs: FakeSessionfulBackend(**kwargs)})
    backend = registry.get("leased", run_dir=tmp_path)
    assert isinstance(backend, FakeSessionfulBackend)
    assert backend.kwargs == {"run_dir": tmp_path}


def test_unknown_backend_fails_closed():
    with pytest.raises(BackendSprintRunnerError) as excinfo:
        BackendRegistry().get("not-registered")
    assert excinfo.value.code == "FAILED_UNKNOWN_BACKEND"


# --- base contract ------------------------------------------------------------


def test_execute_is_the_only_abstract_method():
    assert ExecutionBackend.__abstractmethods__ == frozenset({"execute"})


def test_default_cleanup_is_a_noop_accepting_success():
    class Minimal(ExecutionBackend):
        name = "minimal"

        def execute(self, request):
            raise NotImplementedError

    assert Minimal().cleanup(success=True) is None
    assert Minimal().cleanup() is None


def test_request_and_result_metadata_are_open_mappings(tmp_path):
    request = make_request(tmp_path)
    assert dict(request.metadata) == {}
    result = FakeSessionfulBackend().execute(request)
    assert result.runtime_metadata["session_id"] == "sess-1"
    assert result.backend == "fake-sessionful"


# --- runtime caller: HermesActorAdapter ---------------------------------------


def _git_repo(path):
    path.mkdir(parents=True)
    for args in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "Hermes Test"],
        ["git", "config", "user.email", "test@hermes.local"],
    ):
        subprocess.run(args, cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("contract\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


def _run_task(tmp_path, backend_factory):
    repo = _git_repo(tmp_path / "repo")
    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "worktrees",
        run_dir=tmp_path / "run",
        agent_registry=AgentRegistry({EchoAdapter.name: EchoAdapter}),
        backend_registry=BackendRegistry({FakeSessionfulBackend.name: backend_factory}),
        job_id="job_contract",
    )
    task = TaskNode(
        task_id="T1",
        job_id="job_contract",
        description="noop",
        assigned_actor="echo",
        metadata={"execution_backend": "fake-sessionful", "timeout_seconds": 7},
    )
    run = AgentRun(run_id="run_1", job_id="job_contract", task_id="T1", actor_id="echo")
    return asyncio.run(adapter.execute_task(task, run))


def test_runtime_dispatches_new_backend_and_releases_it_once_on_success(tmp_path):
    result = _run_task(tmp_path, FakeSessionfulBackend)

    assert result.status == "succeeded", result.error
    [backend] = FakeSessionfulBackend.instances
    assert len(backend.requests) == 1
    assert backend.requests[0].timeout_seconds == 7
    assert backend.cleanup_calls == [True]
    assert backend.seat_id is None
    assert result.metadata["execution_backend"] == "fake-sessionful"
    assert result.metadata["backend_runtime_metadata"] == {
        "session_id": "sess-1",
        "seat_id": "seat-1",
    }


@pytest.mark.parametrize(
    "error_type",
    [BackendSprintRunnerError, SprintRunnerError],
    ids=["backend-import-path", "runtime-import-path"],
)
def test_runtime_classifies_backend_timeout_and_releases_once(tmp_path, error_type):
    # Real backends raise agents.errors.SprintRunnerError, a distinct class from
    # runner.agents.errors.SprintRunnerError; both must keep their failure code.
    def factory(**kwargs):
        return FakeSessionfulBackend(
            fail_with=error_type("FAILED_TIMEOUT", "timed out"), **kwargs
        )

    result = _run_task(tmp_path, factory)

    assert result.status == "failed"
    assert result.exit_reason == "failed_timeout"
    [backend] = FakeSessionfulBackend.instances
    assert backend.cleanup_calls == [False]
    assert backend.seat_id is None


def test_runtime_survives_cleanup_failure(tmp_path):
    class ExplodingCleanup(FakeSessionfulBackend):
        def cleanup(self, success=False):
            super().cleanup(success)
            raise BackendSprintRunnerError("FAILED_CLEANUP", "boom")

    result = _run_task(tmp_path, ExplodingCleanup)

    assert result.status == "succeeded", result.error
    [backend] = FakeSessionfulBackend.instances
    assert backend.cleanup_calls == [True]


# --- runner caller: HermesSprintRunner ----------------------------------------


def test_sprint_runner_selects_new_backend_without_runner_changes(tmp_path):
    import json

    # Run records go under the test's own directory, not the home folder.
    spec = json.loads((Path(__file__).resolve().parent.parent / "sprints" / "lab-s03.json").read_text())
    spec["runs_root"] = str(tmp_path / "runs")
    spec_path = tmp_path / "lab-s03.json"
    spec_path.write_text(json.dumps(spec))

    registry = BackendRegistry({FakeSessionfulBackend.name: FakeSessionfulBackend})
    runner = HermesSprintRunner(
        spec_path=spec_path,
        dry_run=True,
        skip_agent_exec=True,
        backend_registry=registry,
        backend_override="fake-sessionful",
    )

    first = runner._get_backend(runner.resolve_backend_name({}))
    second = runner._get_backend(runner.resolve_backend_name({}))

    assert first is second
    assert set(first.kwargs) == {
        "run_dir",
        "sprint_id",
        "logger",
        "keep_workspace",
        "event_sink",
        "cancel_event",
        "cancel_grace_seconds",
    }


def _run_planned_task(tmp_path, metadata, **adapter_kwargs):
    repo = _git_repo(tmp_path / "repo")
    seen = {}

    class RecordingEcho(EchoAdapter):
        def validate_result(self, result, context):
            seen["phase"] = dict(context.phase)

    adapter = HermesActorAdapter(
        target_repo=repo, worktree_root=tmp_path / "worktrees", run_dir=tmp_path / "run",
        agent_registry=AgentRegistry({EchoAdapter.name: RecordingEcho}),
        backend_registry=BackendRegistry({FakeSessionfulBackend.name: FakeSessionfulBackend}),
        job_id="job_contract", **adapter_kwargs,
    )
    task = TaskNode(task_id="T1", job_id="job_contract", description="noop", assigned_actor="echo",
                    metadata={"execution_backend": "fake-sessionful", **metadata})
    run = AgentRun(run_id="run_1", job_id="job_contract", task_id="T1", actor_id="echo")
    return asyncio.run(adapter.execute_task(task, run)), seen


def test_a_planned_builder_that_changes_nothing_fails(tmp_path):
    result, _ = _run_planned_task(tmp_path, {"role": "builder"})
    assert result.status == "failed"
    assert "FAILED_NO_CHANGES" in result.error


def test_job_permissions_and_timeout_reach_tasks_that_carry_none(tmp_path):
    result, seen = _run_planned_task(
        tmp_path, {"role": "hardener"},
        default_permissions={"commands": ["npm run typecheck"]}, default_timeout_seconds=900,
    )
    assert result.status == "succeeded", result.error
    assert seen["phase"]["permissions"] == {"commands": ["npm run typecheck"]}
    assert FakeSessionfulBackend.instances[0].requests[0].timeout_seconds == 900


def test_agent_prompts_tell_agents_not_to_run_git(tmp_path):
    adapter = HermesActorAdapter(target_repo=_git_repo(tmp_path / "repo"), worktree_root=tmp_path / "wt",
                                 run_dir=tmp_path / "run", job_id="job_contract")
    prompt = adapter.build_effective_prompt("Build the page")
    assert "Build the page" in prompt and "Never run git" in prompt


def test_two_jobs_can_run_a_task_with_the_same_id(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    results = []
    for job in ("job_a", "job_b"):
        adapter = HermesActorAdapter(
            target_repo=repo, worktree_root=tmp_path / job, run_dir=tmp_path / f"run_{job}",
            agent_registry=AgentRegistry({EchoAdapter.name: EchoAdapter}),
            backend_registry=BackendRegistry({FakeSessionfulBackend.name: FakeSessionfulBackend}), job_id=job,
            target_branch=f"job/{job}/integration",
        )
        task = TaskNode(task_id="T1", job_id=job, description="noop", assigned_actor="echo",
                        metadata={"execution_backend": "fake-sessionful", "role": "hardener"})
        results.append(asyncio.run(adapter.execute_task(task, AgentRun(run_id=f"r_{job}", job_id=job, task_id="T1", actor_id="echo"))))
    assert [r.status for r in results] == ["succeeded", "succeeded"], [r.error for r in results]
