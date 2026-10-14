"""Job end releases pooled backend resources (OpenRig warm seats) on the reactive runtime path."""

from typing import Any, Dict

import pytest

from runtime.engine import ReactiveJobEngine
from runtime.execution import ActorAdapter, AgentRun, ExecutionManager, TaskExecutionResult
from runtime.hermes_adapter import HermesActorAdapter
from runtime.job_state import JobState
from runtime.task_graph import TaskNode


class RecordingAdapter(ActorAdapter):
    def __init__(self):
        self.released = []

    async def execute_task(self, task: TaskNode, run: AgentRun, context: Dict[str, Any] = None):
        return TaskExecutionResult(status="succeeded")

    def release_job(self, job_id):
        self.released.append(job_id)


@pytest.mark.anyio
async def test_a_finished_job_releases_its_adapters_pooled_resources():
    adapter = RecordingAdapter()
    engine = ReactiveJobEngine(job_id="job_end_release", goal="release at job end", default_adapter=adapter)
    await engine.initialize_and_plan(initial_tasks=[TaskNode(task_id="t1", job_id="job_end_release", description="t1")])

    job = await engine.run_until_complete(max_steps=20)

    assert job.is_terminal
    assert adapter.released == ["job_end_release"]


def test_all_adapters_lists_each_adapter_once():
    manager = ExecutionManager()
    shared = RecordingAdapter()
    manager.set_default_adapter(shared)
    manager.register_adapter("a", shared)
    other = RecordingAdapter()
    manager.register_adapter("b", other)
    assert manager.all_adapters() == [shared, other]


class FakeBackend:
    def __init__(self, calls, **kwargs):
        self.calls, self.kwargs = calls, kwargs

    def release_job(self, job):
        self.calls.append((self.kwargs["sprint_id"], job))


class FakeBackendRegistry:
    def __init__(self):
        self.calls = []

    def get(self, name, **kwargs):
        assert name == "openrig"
        return FakeBackend(self.calls, **kwargs)


def test_hermes_adapter_releases_only_jobs_it_ran_and_only_once(tmp_path):
    registry = FakeBackendRegistry()
    adapter = HermesActorAdapter(run_dir=tmp_path, backend_registry=registry, job_id="j1")
    adapter._job_backends["j1"] = {"openrig"}

    adapter.release_job("unknown-job")
    adapter.release_job("j1")
    adapter.release_job("j1")

    assert registry.calls == [("j1", "j1")]


class FlakyBackendRegistry(FakeBackendRegistry):
    def __init__(self):
        super().__init__()
        self.failures = 1

    def get(self, name, **kwargs):
        registry = self

        class Flaky(FakeBackend):
            def release_job(self, job):
                if registry.failures:
                    registry.failures -= 1
                    raise RuntimeError("daemon hiccup")
                super().release_job(job)

        return Flaky(self.calls, **kwargs)


def test_a_failed_job_release_is_retried_by_the_next_call(tmp_path):
    registry = FlakyBackendRegistry()
    adapter = HermesActorAdapter(run_dir=tmp_path, backend_registry=registry, job_id="j1")
    adapter._job_backends["j1"] = {"openrig"}

    adapter.release_job("j1")  # fails, kept
    adapter.release_job("j1")  # retried, succeeds
    adapter.release_job("j1")  # nothing left

    assert registry.calls == [("j1", "j1")]
    assert adapter._job_backends == {}
