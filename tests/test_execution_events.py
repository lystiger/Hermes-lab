"""D-009 execution visibility: event order per backend, sink safety, registry, snapshot.

OpenRig runs against the scripted fake `rig` from test_openrig_backend.py; nothing here
reaches a real daemon. Subprocess and Herdr use plain fakes.
"""

import asyncio
import json
import re
import shlex
import sys
import subprocess
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from agents.claude import ClaudeAdapter
from agents.errors import SprintRunnerError
from runner.agents.registry import AgentRegistry
from runner.backends import events
from runner.backends.base import ExecutionRequest
from runner.backends.events import EXECUTION_EVENT_KINDS, ExecutionEvent
from runner.backends.execution_registry import (
    ExecutionRegistry,
    build_execution_snapshot,
    probe_backends,
)
from runner.backends.herdr_backend import HerdrBackend
from runner.backends.openrig_backend import OpenRigBackend, _SeatPool, describe_openrig
from runner.backends.openrig_ledger import OwnershipLedger
from runner.backends.registry import BackendRegistry
from runner.backends.subprocess_backend import SubprocessBackend
from runtime.execution import AgentRun
from runtime.hermes_adapter import HermesActorAdapter
from runtime.task_graph import TaskNode

from test_openrig_backend import (
    FINISHED,
    GEN2_FINISHED,
    GEN2_STARTED,
    GEN2_STOP,
    RIG_ID,
    STARTED,
    STARTUP_IDLE,
    T0,
    FakeClock,
    FakeRig,
    FakeTimer,
    fake_daemon_down,
)

ALLOWED_METADATA = {
    "backend", "executionId", "resource", "reused", "generation", "rigId", "sessionName",
    "nodeId", "expiresAt", "errorCode", "error", "durationMs",
}


class Sink:
    """Records events. Thread-safe: list.append is atomic and backends emit from worker threads."""

    def __init__(self):
        self.events = []

    def __call__(self, event):
        self.events.append(event)

    def kinds(self):
        return [e.kind for e in self.events]

    def of(self, kind):
        return [e for e in self.events if e.kind == kind]


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def sink():
    return Sink()


@pytest.fixture(autouse=True)
def fresh_timers():
    FakeTimer.created = []


def check_contract(sink):
    """Every event follows D-009: a known kind, backend + executionId, only the allowed metadata keys."""
    for event in sink.events:
        assert event.kind in EXECUTION_EVENT_KINDS
        assert {"backend", "executionId"} <= set(event.metadata)
        assert set(event.metadata) <= ALLOWED_METADATA, event.metadata
    ids = {e.metadata["executionId"] for e in sink.events}
    return ids


# --- subprocess ------------------------------------------------------------------


def sub_request(tmp_path, **kwargs):
    worktree = tmp_path / "wt"
    worktree.mkdir(exist_ok=True)
    return ExecutionRequest(
        agent_name=kwargs.pop("agent_name", "claude"),
        command=("claude", "-p", "x"),
        cwd=worktree,
        timeout_seconds=30,
        stdout_file=tmp_path / "out.log",
        stderr_file=tmp_path / "err.log",
        metadata={"phase": "build"},
    )


def completed(returncode=0, stdout="ok", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_subprocess_success_order_and_shape(tmp_path, sink):
    backend = SubprocessBackend(run_process=lambda *a, **k: completed(), event_sink=sink, sprint_id="job-1")
    result = backend.execute(sub_request(tmp_path))

    assert result.returncode == 0
    assert sink.kinds() == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.RUNNING, events.FINISHED, events.RESOURCE_RELEASED,
    ]
    assert len(check_contract(sink)) == 1
    for event in sink.events:
        assert event.job_id == "job-1"
    acquired = sink.of(events.RESOURCE_ACQUIRED)[0].metadata
    assert acquired["resource"]["kind"] == "process"
    assert acquired["resource"]["id"] == acquired["executionId"]
    assert sink.of(events.FINISHED)[0].metadata["durationMs"] >= 0


def test_subprocess_nonzero_exit_is_finished_not_failed(tmp_path, sink):
    backend = SubprocessBackend(run_process=lambda *a, **k: completed(returncode=3), event_sink=sink)
    result = backend.execute(sub_request(tmp_path))

    assert result.returncode == 3
    assert events.FAILED not in sink.kinds()
    assert sink.kinds()[-2:] == [events.FINISHED, events.RESOURCE_RELEASED]


def test_subprocess_timeout_fails_with_code_before_release(tmp_path, sink):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=30)

    backend = SubprocessBackend(run_process=timeout, event_sink=sink)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(sub_request(tmp_path))

    assert excinfo.value.code == "FAILED_TIMEOUT"
    assert sink.kinds() == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.RUNNING, events.FAILED, events.RESOURCE_RELEASED,
    ]
    failed = sink.of(events.FAILED)[0].metadata
    assert failed["errorCode"] == "FAILED_TIMEOUT"
    assert failed["error"]


def test_subprocess_missing_executable_is_a_backend_failure(tmp_path, sink):
    def missing(*args, **kwargs):
        raise FileNotFoundError("claude")

    backend = SubprocessBackend(run_process=missing, event_sink=sink)
    with pytest.raises(SprintRunnerError):
        backend.execute(sub_request(tmp_path))
    assert sink.of(events.FAILED)[0].metadata["errorCode"] == "FAILED_AGENT_EXECUTABLE_MISSING"


def test_subprocess_without_a_sink_is_silent_and_unchanged(tmp_path):
    backend = SubprocessBackend(run_process=lambda *a, **k: completed(stdout="hi"))
    assert backend.execute(sub_request(tmp_path)).stdout == "hi"


# --- herdr -----------------------------------------------------------------------


class FakeHerdr:
    """Answers the herdr calls the backend makes and completes the worker at wait-output."""

    def __init__(self, run_dir, fail_run=False):
        self.run_dir = run_dir
        self.fail_run = fail_run

    def __call__(self, argv, capture_output, text, timeout):
        args = argv[1:]
        ok = lambda payload: subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
        if args[:2] == ["api", "snapshot"]:
            return ok({})
        if args[:2] == ["workspace", "create"]:
            return ok({"result": {"workspace": {"workspace_id": "ws-1"}, "root_pane": {"pane_id": "root-1"}}})
        if args[:2] == ["pane", "split"]:
            return ok({"result": {"pane": {"pane_id": "pane-1"}}})
        if args[:2] == ["pane", "rename"]:
            return ok({})
        if args[:2] == ["pane", "run"]:
            if self.fail_run:
                return subprocess.CompletedProcess(argv, 1, "", "pane gone")
            # The wrapper would write its exit status here; the fake records where, and writes it at wait-output.
            wrapper = Path(shlex.split(args[3])[1])
            token = re.search(r'"\$status" > (.+)', wrapper.read_text()).group(1)
            self.exit_path = Path(shlex.split(token)[0])
            return subprocess.CompletedProcess(argv, 0, "", "")
        if args[:2] == ["pane", "wait-output"]:
            self.exit_path.write_text("0")
            return ok({})
        if args[:2] == ["pane", "send-keys"]:
            return ok({})
        raise AssertionError(f"unexpected herdr call {args}")


def herdr_backend(tmp_path, sink, **kwargs):
    run_dir = tmp_path / "run"
    return HerdrBackend(
        run_dir=run_dir, sprint_id="job-h", run_process=FakeHerdr(run_dir, **kwargs),
        which_func=lambda name: "/usr/bin/x", event_sink=sink, keep_workspace=True,
    )


def test_herdr_success_order_and_pane_resource(tmp_path, sink):
    backend = herdr_backend(tmp_path, sink)
    backend.execute(sub_request(tmp_path))

    assert sink.kinds() == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.RUNNING, events.FINISHED, events.RESOURCE_RELEASED,
    ]
    check_contract(sink)
    resource = sink.of(events.RESOURCE_ACQUIRED)[0].metadata["resource"]
    assert resource == {"kind": "pane", "id": "pane-1", "label": "build"}
    assert sink.of(events.RESOURCE_RELEASED)[0].metadata["resource"]["id"] == "pane-1"


def test_herdr_command_failure_is_failed_then_released(tmp_path, sink):
    backend = herdr_backend(tmp_path, sink, fail_run=True)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(sub_request(tmp_path))

    assert excinfo.value.code == "FAILED_HERDR_COMMAND"
    assert sink.kinds() == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.FAILED, events.RESOURCE_RELEASED,
    ]
    assert sink.of(events.FAILED)[0].metadata["errorCode"] == "FAILED_HERDR_COMMAND"


def test_herdr_failure_before_a_pane_emits_no_resource_events(tmp_path, sink):
    backend = HerdrBackend(
        run_dir=tmp_path / "run", sprint_id="job-h", run_process=FakeHerdr(tmp_path / "run"),
        which_func=lambda name: None, event_sink=sink,
    )
    with pytest.raises(SprintRunnerError):
        backend.execute(sub_request(tmp_path))
    assert sink.kinds() == [events.STARTED, events.FAILED]


# --- openrig ---------------------------------------------------------------------


def openrig(tmp_path, clock, rig, pool, sink, utc_at=T0, cancel_event=None):
    return OpenRigBackend(
        run_dir=tmp_path / "run",
        sprint_id="job-ev",
        run_process=rig,
        which_func=lambda name: "/usr/bin/rig",
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        utcnow=lambda: utc_at,
        poll_interval=2.0,
        seat_pool=pool,
        ledger=OwnershipLedger(tmp_path / "ledger"),
        cancel_event=cancel_event,
        daemon_down=fake_daemon_down(rig),
        event_sink=sink,
    )


@pytest.fixture
def pool():
    seat_pool = _SeatPool(idle_seconds=120, timer_factory=FakeTimer)
    yield seat_pool
    seat_pool.drain()


def test_openrig_success_order_and_metadata(tmp_path, clock, pool, sink):
    rig = FakeRig(clock)
    openrig(tmp_path, clock, rig, pool, sink).execute(sub_request_openrig(tmp_path))

    assert sink.kinds() == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.RUNNING, events.FINISHED, events.RESOURCE_POOLED,
    ]
    check_contract(sink)
    acquired = sink.of(events.RESOURCE_ACQUIRED)[0].metadata
    assert acquired["reused"] is False
    assert acquired["rigId"] == RIG_ID
    assert acquired["sessionName"] == rig.session
    assert acquired["resource"]["kind"] == "seat"
    assert acquired["resource"]["id"] == RIG_ID
    ready = sink.of(events.RESOURCE_READY)[0].metadata
    assert ready["generation"] == "gen-1"
    assert ready["nodeId"] == "01000000000000000000000006"
    pooled = sink.of(events.RESOURCE_POOLED)[0].metadata
    assert pooled["resource"]["id"] == RIG_ID
    assert pooled["expiresAt"].endswith("Z")
    assert sink.of(events.FINISHED)[0].metadata["durationMs"] >= 0


def sub_request_openrig(tmp_path):
    from test_openrig_backend import make_request

    return make_request(tmp_path)


def test_openrig_reused_seat_reports_reuse_and_new_generation(tmp_path, clock, pool, sink):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, FINISHED, GEN2_STOP, GEN2_STARTED, GEN2_FINISHED])
    openrig(tmp_path, clock, rig, pool, Sink()).execute(sub_request_openrig(tmp_path))

    second = Sink()
    from test_openrig_backend import make_request

    openrig(tmp_path, clock, rig, pool, second, utc_at=T0 + timedelta(seconds=30)).execute(
        make_request(tmp_path, worktree_name="worktree-2")
    )

    assert second.kinds() == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.RUNNING, events.FINISHED, events.RESOURCE_POOLED,
    ]
    acquired = second.of(events.RESOURCE_ACQUIRED)[0].metadata
    assert acquired["reused"] is True
    assert acquired["generation"] == "gen-2"
    assert second.of(events.RESOURCE_READY)[0].metadata["generation"] == "gen-2"


def test_openrig_failed_send_fails_before_its_release(tmp_path, clock, pool, sink):
    rig = FakeRig(clock)
    rig.send_override = subprocess.CompletedProcess([], 1, json.dumps({"ok": False, "sent": False}), "")
    with pytest.raises(SprintRunnerError) as excinfo:
        openrig(tmp_path, clock, rig, pool, sink).execute(sub_request_openrig(tmp_path))

    assert excinfo.value.code == "FAILED_OPENRIG_DELIVERY"
    assert sink.kinds() == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.FAILED, events.RESOURCE_RELEASED,
    ]
    failed = sink.of(events.FAILED)[0].metadata
    assert failed["errorCode"] == "FAILED_OPENRIG_DELIVERY"
    released = sink.of(events.RESOURCE_RELEASED)[0].metadata
    assert released["rigId"] == RIG_ID
    assert rig.rigs_down == [RIG_ID]


def test_openrig_cancel_before_lease_reports_cancelled(tmp_path, clock, pool, sink):
    cancel = threading.Event()
    cancel.set()
    rig = FakeRig(clock)
    with pytest.raises(SprintRunnerError):
        openrig(tmp_path, clock, rig, pool, sink, cancel_event=cancel).execute(sub_request_openrig(tmp_path))

    assert sink.kinds() == [events.STARTED, events.CANCELLED]
    assert sink.of(events.CANCELLED)[0].metadata["errorCode"] == "FAILED_OPENRIG_CANCELLED"


def test_openrig_pool_expiry_releases_and_reports_it(tmp_path, clock, pool, sink):
    rig = FakeRig(clock)
    openrig(tmp_path, clock, rig, pool, sink).execute(sub_request_openrig(tmp_path))
    assert sink.kinds()[-1] == events.RESOURCE_POOLED

    FakeTimer.created[-1].fire()

    assert sink.kinds()[-1] == events.RESOURCE_RELEASED
    released = sink.events[-1].metadata
    assert released["rigId"] == RIG_ID
    assert released["resource"]["id"] == RIG_ID
    assert rig.rigs_down == [RIG_ID]
    check_contract(sink)


def test_openrig_release_job_reports_each_idle_seat(tmp_path, clock, pool, sink):
    rig = FakeRig(clock)
    backend = openrig(tmp_path, clock, rig, pool, sink)
    backend.execute(sub_request_openrig(tmp_path))

    assert backend.release_job("job-ev") == 1
    assert sink.kinds()[-2:] == [events.RESOURCE_POOLED, events.RESOURCE_RELEASED]
    assert rig.rigs_down == [RIG_ID]
    # A repeated release_job finds nothing and emits nothing.
    count = len(sink.events)
    backend.release_job("job-ev")
    assert len(sink.events) == count


def test_openrig_drain_reports_release_of_idle_seats(tmp_path, clock, pool, sink):
    rig = FakeRig(clock)
    openrig(tmp_path, clock, rig, pool, sink).execute(sub_request_openrig(tmp_path))

    pool.drain(wait_seconds=0.1)

    assert sink.kinds()[-1] == events.RESOURCE_RELEASED
    assert rig.rigs_down == [RIG_ID]


def test_openrig_failed_release_is_reported_and_kept_for_retry(tmp_path, clock, pool, sink):
    rig = FakeRig(clock)
    backend = openrig(tmp_path, clock, rig, pool, sink)
    backend.execute(sub_request_openrig(tmp_path))
    rig.down_results = [subprocess.CompletedProcess([], 0, json.dumps({
        "rigId": RIG_ID, "errors": ["daemon busy"],
    }), "")]

    with pytest.raises(SprintRunnerError) as excinfo:
        backend.release_job("job-ev")

    assert excinfo.value.code == "FAILED_OPENRIG_UNAVAILABLE"
    failed = sink.of(events.RELEASE_FAILED)
    assert len(failed) == 1
    assert failed[0].metadata["rigId"] == RIG_ID
    assert failed[0].metadata["errorCode"] == "FAILED_OPENRIG_UNAVAILABLE"
    assert sink.kinds()[-1] == events.RELEASE_FAILED

    # The retry succeeds and reports the release.
    backend.release_job("job-ev")
    assert sink.kinds()[-1] == events.RESOURCE_RELEASED


def test_openrig_sink_errors_never_fail_the_task(tmp_path, clock, pool):
    def broken(event):
        raise RuntimeError("sink exploded")

    rig = FakeRig(clock)
    result = openrig(tmp_path, clock, rig, pool, broken).execute(sub_request_openrig(tmp_path))
    assert result.returncode == 0


# --- sink safety and the runtime path ----------------------------------------------


class RecordingBridge:
    """Stands in for RuntimeEventBridge: records what would be persisted, optionally failing."""

    def __init__(self, delay=0.0, fail_kinds=()):
        self.persisted = []
        self.delay = delay
        self.fail_kinds = set(fail_kinds)

    async def persist_and_publish(self, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        if kwargs["kind"] in self.fail_kinds:
            raise RuntimeError("store unavailable")
        self.persisted.append(kwargs)


def make_adapter(tmp_path, bridge=None, registry=None, job_id="job_ev"):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    return HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "worktrees",
        run_dir=tmp_path / "run",
        job_id=job_id,
        event_bridge=bridge,
        backend_registry=registry,
    )


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason='Windows CI delivers a SIGINT mid-test (asyncio.run raises KeyboardInterrupt), '
           'which aborts the whole pytest session; source not yet identified',
)
def test_concurrent_emits_from_threads_are_all_persisted_in_order(tmp_path):
    bridge = RecordingBridge(delay=0.0)
    adapter = make_adapter(tmp_path, bridge)
    threads, per_thread = 8, 50

    async def main():
        adapter._bind_event_loop(asyncio.get_running_loop())

        def emitter(n):
            for seq in range(per_thread):
                adapter._on_execution_event(ExecutionEvent(
                    kind=events.RUNNING, job_id="job_ev", detail=f"{n}:{seq}",
                    metadata={"backend": "subprocess", "executionId": f"exec-{n}"},
                ))

        workers = [threading.Thread(target=emitter, args=(n,)) for n in range(threads)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        deadline = asyncio.get_running_loop().time() + 5
        while len(bridge.persisted) < threads * per_thread and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)

    asyncio.run(main())

    assert len(bridge.persisted) == threads * per_thread
    for n in range(threads):
        seqs = [int(p["detail"].split(":")[1]) for p in bridge.persisted if p["metadata"]["executionId"] == f"exec-{n}"]
        assert seqs == list(range(per_thread))
    assert all(p["source_kind"] == "runtime" for p in bridge.persisted)


def test_sink_never_blocks_the_worker_on_a_slow_store(tmp_path):
    bridge = RecordingBridge(delay=0.2)
    adapter = make_adapter(tmp_path, bridge)

    async def main():
        adapter._bind_event_loop(asyncio.get_running_loop())
        started = time.monotonic()
        # Emitting from a worker thread (not the loop): each call must return without waiting.
        await asyncio.to_thread(lambda: [
            adapter._on_execution_event(ExecutionEvent(
                kind=events.RUNNING, job_id="job_ev", detail="x",
                metadata={"backend": "openrig", "executionId": "e"},
            )) for _ in range(10)
        ])
        assert time.monotonic() - started < 0.5
        deadline = asyncio.get_running_loop().time() + 5
        while len(bridge.persisted) < 10 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)

    asyncio.run(main())
    assert len(bridge.persisted) == 10


def test_a_failing_store_drops_only_that_event(tmp_path):
    bridge = RecordingBridge(fail_kinds={events.RUNNING})
    adapter = make_adapter(tmp_path, bridge)

    async def main():
        adapter._bind_event_loop(asyncio.get_running_loop())
        for kind in (events.STARTED, events.RUNNING, events.FINISHED):
            adapter._on_execution_event(ExecutionEvent(
                kind=kind, job_id="job_ev", detail="", metadata={"backend": "herdr", "executionId": "e"},
            ))
        deadline = asyncio.get_running_loop().time() + 5
        while len(bridge.persisted) < 2 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)

    asyncio.run(main())
    assert [p["kind"] for p in bridge.persisted] == [events.STARTED, events.FINISHED]


def test_sink_without_a_loop_only_updates_the_registry(tmp_path):
    from runner.backends.execution_registry import default_execution_registry

    bridge = RecordingBridge()
    adapter = make_adapter(tmp_path, bridge, job_id="job_nl")
    adapter._on_execution_event(ExecutionEvent(
        kind=events.RESOURCE_ACQUIRED, job_id="job_nl", detail="",
        metadata={"backend": "openrig", "executionId": "e-nl", "resource": {"kind": "seat", "id": "01NOLOOP", "label": "x"}},
    ))
    assert bridge.persisted == []
    assert any(r["id"] == "01NOLOOP" for r in default_execution_registry.resources())
    default_execution_registry.apply(ExecutionEvent(
        kind=events.RESOURCE_RELEASED, job_id="job_nl", detail="",
        metadata={"backend": "openrig", "executionId": "e-nl", "resource": {"kind": "seat", "id": "01NOLOOP", "label": "x"}},
    ))


def test_openrig_task_through_the_runtime_is_persisted_in_order(tmp_path, clock, pool):
    """End to end: adapter -> openrig -> sink -> bridge. Every lifecycle event reaches the bridge."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "Hermes Test"],
        ["git", "config", "user.email", "test@hermes.local"],
    ):
        subprocess.run(args, cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    rig = FakeRig(clock)
    bridge = RecordingBridge()
    job_id = "job_persist"
    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "worktrees",
        run_dir=tmp_path / "run",
        agent_registry=AgentRegistry({ClaudeAdapter.name: ClaudeAdapter}),
        backend_registry=BackendRegistry({
            OpenRigBackend.name: lambda **kw: OpenRigBackend(
                run_process=rig, which_func=lambda n: "/usr/bin/rig",
                monotonic=clock.monotonic, sleep=clock.sleep, utcnow=lambda: T0,
                seat_pool=pool, daemon_down=fake_daemon_down(rig), **kw,
            ),
        }),
        job_id=job_id,
        event_bridge=bridge,
    )
    task = TaskNode(
        task_id="T1", job_id=job_id, description="Touch nothing", assigned_actor="claude",
        metadata={"execution_backend": "openrig", "timeout_seconds": 120},
    )
    async def run_task_and_flush():
        result = await adapter.execute_task(task, AgentRun(
            run_id="r1", job_id=job_id, task_id="T1", actor_id="claude",
        ))
        # Persistence runs on this loop after the worker returns; wait for it before the loop closes.
        deadline = asyncio.get_running_loop().time() + 5
        while len(bridge.persisted) < 6 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        return result

    result = asyncio.run(run_task_and_flush())

    assert result.status == "succeeded", result.error
    kinds = [p["kind"] for p in bridge.persisted]
    assert kinds == [
        events.STARTED, events.RESOURCE_ACQUIRED, events.RESOURCE_READY,
        events.RUNNING, events.FINISHED, events.RESOURCE_POOLED,
    ]
    assert {p["source_id"] for p in bridge.persisted} == {"openrig"}
    assert {p["job_id"] for p in bridge.persisted} == {job_id}
    assert all(p["metadata"]["backend"] == "openrig" for p in bridge.persisted)
    # Backends do not know the runtime task; the adapter stamps it so the UI can link task -> resource.
    assert {p["task_id"] for p in bridge.persisted} == {"T1"}
    assert {p["run_id"] for p in bridge.persisted} == {"r1"}
    assert {p["actor_id"] for p in bridge.persisted} == {"claude"}
    from runner.backends.execution_registry import default_execution_registry
    assert any(row["taskId"] == "T1" for row in default_execution_registry.resources())


# --- registry and snapshot ---------------------------------------------------------


def ev(kind, backend="openrig", resource_id="01REG", **meta):
    execution_id = meta.pop("executionId", "exec-r")
    metadata = {
        "backend": backend,
        "executionId": execution_id,
        "resource": {"kind": "seat", "id": resource_id, "label": "seat-label"},
        **meta,
    }
    return ExecutionEvent(kind=kind, job_id="job-r", detail="", metadata=metadata)


def test_registry_follows_a_seat_through_its_states():
    registry = ExecutionRegistry()
    registry.apply(ev(events.RESOURCE_ACQUIRED, reused=False, rigId="01REG"))
    assert registry.resources()[0]["state"] == "acquiring"
    registry.apply(ev(events.RESOURCE_READY, generation="g1"))
    assert registry.resources()[0]["state"] == "ready"
    registry.apply(ev(events.RUNNING))
    assert registry.resources()[0]["state"] == "running"
    registry.apply(ev(events.FINISHED))
    assert registry.resources()[0]["state"] == "running"
    registry.apply(ev(events.RESOURCE_POOLED, expiresAt="2026-10-14T10:00:00Z"))
    row = registry.resources()[0]
    assert row["state"] == "idle"
    assert row["expiresAt"] == "2026-10-14T10:00:00Z"
    assert row["details"]["generation"] == "g1"
    assert row["jobId"] == "job-r"
    registry.apply(ev(events.RESOURCE_RELEASED))
    assert registry.resources() == []


def test_registry_marks_failures_and_keeps_release_failures_visible():
    registry = ExecutionRegistry()
    registry.apply(ev(events.RESOURCE_ACQUIRED))
    registry.apply(ev(events.FAILED, errorCode="FAILED_OPENRIG_DELIVERY"))
    assert registry.resources()[0]["state"] == "releasing"
    registry.apply(ev(events.RELEASE_FAILED, executionId="release:01REG"))
    row = registry.resources()[0]
    assert row["state"] == "failed"
    assert row["executionId"] == "release:01REG"


def test_registry_ignores_events_without_a_resource():
    registry = ExecutionRegistry()
    registry.apply(ExecutionEvent(kind=events.STARTED, job_id="j", detail="", metadata={"backend": "x", "executionId": "e"}))
    assert registry.resources() == []


def test_registry_resource_copies_do_not_leak_internal_state():
    registry = ExecutionRegistry()
    registry.apply(ev(events.RESOURCE_ACQUIRED, reused=True))
    rows = registry.resources()
    rows[0]["details"]["reused"] = False
    assert registry.resources()[0]["details"]["reused"] is True


def test_snapshot_shape_and_registry_contents():
    registry = ExecutionRegistry()
    registry.apply(ev(events.RESOURCE_POOLED, expiresAt="2026-10-14T10:00:00Z"))
    snapshot = build_execution_snapshot(
        registry=registry,
        probe=lambda: ([{"name": "openrig", "available": True, "detail": "d"}],
                       {"daemon": "up", "ledger": {"owners": 1, "rigIds": ["01REG"]}}),
    )

    assert set(snapshot) == {"backends", "resources", "openrig", "takenAt"}
    assert snapshot["backends"] == [{"name": "openrig", "available": True, "detail": "d"}]
    assert snapshot["openrig"] == {"daemon": "up", "ledger": {"owners": 1, "rigIds": ["01REG"]}}
    (row,) = snapshot["resources"]
    assert set(row) == {
        "backend", "kind", "id", "label", "state", "jobId", "taskId", "executionId",
        "since", "expiresAt", "details",
    }
    assert row["kind"] == "seat" and row["state"] == "idle"
    assert row["taskId"] is None


def test_snapshot_without_openrig_reports_null(tmp_path):
    snapshot = build_execution_snapshot(
        registry=ExecutionRegistry(),
        probe=lambda: ([], None),
    )
    assert snapshot["openrig"] is None
    assert snapshot["resources"] == []


def test_snapshot_probe_only_runs_read_only_rig_commands(tmp_path, monkeypatch):
    calls = []

    def recorder(argv, capture_output, text, timeout):
        calls.append(list(argv[1:]))
        return subprocess.CompletedProcess(argv, 0, "[]", "")

    ledger_dir = tmp_path / "ledger-absent"
    backends, openrig = probe_backends(
        which=lambda name: "/usr/bin/" + name, run_process=recorder,
        ledger=OwnershipLedger(ledger_dir),
    )

    assert calls == [["ps", "--json"]]
    assert openrig == {"daemon": "up", "ledger": {"owners": 0, "rigIds": []}}
    assert {b["name"] for b in backends} == {"subprocess", "herdr", "openrig"}
    # A read-only status probe must not create the ledger directory.
    assert not ledger_dir.exists()


def test_describe_openrig_reports_daemon_down_and_unknown():
    down = describe_openrig(
        run_process=lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "daemon down"),
        which=lambda name: "/usr/bin/rig", ledger=OwnershipLedger(Path("/nonexistent-ledger-dir-x")),
    )
    assert down["daemon"] == "down"

    def times_out(*a, **k):
        raise subprocess.TimeoutExpired(cmd="rig", timeout=3)

    unknown = describe_openrig(run_process=times_out, which=lambda name: "/usr/bin/rig",
                               ledger=OwnershipLedger(Path("/nonexistent-ledger-dir-x")))
    assert unknown["daemon"] == "unknown"
    assert describe_openrig(which=lambda name: None) is None


def test_ledger_summary_is_read_only(tmp_path):
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    (ledger_dir / "dead-host-1-x.json").write_text(json.dumps({
        "host": "some-other-host", "pid": 1, "started": "x", "rigIds": [RIG_ID],
    }))
    (ledger_dir / "garbage.json").write_text("{not json")
    before = sorted(p.name for p in ledger_dir.iterdir())

    summary = OwnershipLedger(ledger_dir).summary()

    assert summary == {"owners": 1, "rigIds": [RIG_ID]}
    assert sorted(p.name for p in ledger_dir.iterdir()) == before
    assert not (ledger_dir / ".lock").exists()


def test_execution_route_is_registered_as_get():
    import main

    routes = [r for r in main.app.routes if getattr(r, "path", None) == "/execution"]
    assert len(routes) == 1
    assert routes[0].methods == {"GET"}


def test_execution_route_returns_the_snapshot(monkeypatch):
    import main

    monkeypatch.setattr(main, "build_execution_snapshot", lambda: {"backends": [], "resources": [], "openrig": None})
    assert asyncio.run(main.get_execution()) == {"backends": [], "resources": [], "openrig": None}


# --- merge-gate review fixes -------------------------------------------------------
def test_live_bus_events_carry_runtime_ids_for_the_ui(tmp_path):
    from events.event_bus import RuntimeEventBus
    from runtime.events import RuntimeEventBridge

    bus = RuntimeEventBus()
    bridge = RuntimeEventBridge()
    bridge.set_bus(bus)
    asyncio.run(bridge.persist_and_publish(
        source_id="openrig", source_kind="runtime", kind=events.STARTED, detail="",
        job_id="j1", task_id="T1", run_id="r1", actor_id="claude", metadata={"backend": "openrig"},
    ))
    wire = bus.get_history()[-1].to_dict() if hasattr(bus, "get_history") else bus._history[-1].to_dict()
    assert (wire["jobId"], wire["taskId"], wire["runId"], wire["actorId"]) == ("j1", "T1", "r1", "claude")


def test_a_bus_without_runtime_id_support_still_gets_the_event():
    from runtime.events import RuntimeEventBridge

    class OldBus:
        def __init__(self):
            self.got = []

        def publish(self, source_id, kind, detail, source_kind="system", duration="—",
                    job_id=None, metadata=None, accent_color=None):
            self.got.append(kind)

    bus = OldBus()
    bridge = RuntimeEventBridge()
    bridge.set_bus(bus)
    asyncio.run(bridge.persist_and_publish(
        source_id="x", source_kind="runtime", kind="execution.started", detail="", task_id="T1",
    ))
    assert bus.got == ["execution.started"]


def test_an_observability_write_failure_never_halts_the_job_at_flush():
    from runtime.events import RuntimeEventBridge

    class BrokenStore:
        async def append(self, event):
            raise RuntimeError("disk full")

    bridge = RuntimeEventBridge()
    bridge.set_store(BrokenStore())

    async def scenario():
        assert await bridge.persist_and_publish(
            source_id="openrig", source_kind="runtime", kind=events.STARTED, detail="", fail_closed=False,
        ) is None
        await bridge.flush()  # must not raise

    asyncio.run(scenario())


def test_fail_closed_writes_still_halt_on_store_failure():
    from runtime.events import RuntimeEventBridge

    class BrokenStore:
        async def append(self, event):
            raise RuntimeError("disk full")

    bridge = RuntimeEventBridge()
    bridge.set_store(BrokenStore())
    with pytest.raises(RuntimeError):
        asyncio.run(bridge.persist_and_publish(source_id="x", source_kind="runtime", kind="task.started", detail=""))


def test_snapshot_carries_a_taken_at_cutoff_before_its_resources():
    import time as _time
    from runner.backends.execution_registry import ExecutionRegistry, build_execution_snapshot

    before = _time.time()
    snap = build_execution_snapshot(registry=ExecutionRegistry(), probe=lambda: ([], None))
    assert before <= snap["takenAt"] <= _time.time()


def test_snapshot_keeps_failure_diagnostics_until_the_next_attempt():
    from runner.backends.execution_registry import ExecutionRegistry

    reg = ExecutionRegistry()
    reg.apply(ev(events.RUNNING))
    reg.apply(ev(events.RELEASE_FAILED, errorCode="FAILED_OPENRIG_UNAVAILABLE", error="daemon down"))
    [row] = reg.resources()
    assert row["state"] == "failed"
    assert row["details"]["errorCode"] == "FAILED_OPENRIG_UNAVAILABLE"
    assert row["details"]["error"] == "daemon down"
    assert row["details"]["releaseFailed"] is True

    reg.apply(ev(events.RESOURCE_ACQUIRED))
    [row] = reg.resources()
    assert not {"errorCode", "error", "releaseFailed"} & set(row["details"])
