"""OpenRigBackend unit tests against a scripted fake `rig` CLI (no live OpenRig)."""

import multiprocessing
import socket
import threading
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.claude import ClaudeAdapter
from agents.errors import SprintRunnerError
from runner.agents.registry import AgentRegistry
from runner.backends.base import ExecutionRequest
from runner.backends.openrig_backend import POLL_QUERY_SECONDS, OpenRigBackend, _Seat, _SeatPool
from runner.backends.openrig_ledger import OwnershipLedger
from runner.backends.registry import BackendRegistry, default_backend_registry
from runtime.execution import AgentRun
from runtime.hermes_adapter import HermesActorAdapter
from runtime.task_graph import TaskNode


T0 = datetime(2026, 10, 12, 5, 0, 0, tzinfo=timezone.utc)
RIG_ID = "01000000000000000000000012"
# Every canonical id the tests use: the fake daemon reports them as existing until torn down.
KNOWN_TEST_RIG_IDS = {f"01{n:024d}" for n in range(1, 100)}
GEN = "gen-1"


def iso(seconds):
    return (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def hook(state, raw, at, generation=GEN, **extra):
    return {
        "state": state, "rawEvent": raw, "eventAt": iso(at), "evidenceSource": "runtime_hook",
        "stale": False, "fallback": False, "generation": generation, **extra,
    }


STARTUP_IDLE = hook("idle", "Stop", -30)
STARTED = hook("running", "UserPromptSubmit", 1)
FINISHED = hook("idle", "Stop", 5)
HEURISTIC = {"state": "running", "reason": "window_activity_motion", "evidenceSource": "terminal_activity"}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds > 0
        self.now += seconds


class FakeRig:
    """Scripted `rig` CLI. Each `ps --nodes` call pops the next activity state."""

    def __init__(self, clock, activities=None, result=None, startup="ready"):
        self.clock = clock
        self.calls = []
        self.timeouts = []
        self.version = "0.6.9 (4b48ca21)\n"
        self.activities = list(activities or [STARTUP_IDLE, STARTED, FINISHED])
        self.result = {"status": "succeeded", "summary": "did the thing"} if result is None else result
        self.startup = startup
        self.node_overrides = {}
        self.up_override = None
        self.send_override = None
        self.down_results = []
        self.ps_failure = None
        self.rig_name = None
        self.sent_text = None
        self.rigs_down = []
        self.listed_rigs = []
        self.seat_launch_override = None
        self.next_generation = "gen-2"
        self.gone_rig_ids = set()

    def __call__(self, argv, capture_output, text, timeout):
        assert argv[0] == "rig" and capture_output and text
        assert timeout > 0
        self.calls.append(argv[1:])
        self.timeouts.append(timeout)
        cmd = argv[1]
        if cmd == "--version":
            return self._ok(self.version)
        if cmd == "ps" and "--include-archived" in argv:
            # Teardown pre-check: every test rig id exists until `rig down` succeeds for it.
            listed = [{"rigId": "01000000000000000000000003", "name": "kernel", "status": "stopped"}] + self.listed_rigs
            known = {r["rigId"] for r in listed}
            listed += [{"rigId": rig_id, "name": f"rig-{rig_id}"} for rig_id in sorted(KNOWN_TEST_RIG_IDS - self.gone_rig_ids - known)]
            return self._ok(json.dumps(listed))
        if cmd == "ps" and "--nodes" not in argv:
            return self._ok(json.dumps(
                [{"rigId": "01000000000000000000000003", "name": "kernel", "status": "running"}] + self.listed_rigs
            ))
        if cmd == "up":
            spec = json.loads(Path(argv[2]).read_text())
            self.rig_name = spec["name"]
            self.spec = spec
            if self.up_override is not None:
                return self.up_override(self)
            return self._ok(json.dumps({
                "status": "completed", "rigId": RIG_ID, "errors": [],
                "stages": [{"stage": "import_rig", "status": "ok", "detail": {
                    "rigId": RIG_ID, "specName": self.rig_name,
                    "nodes": [{"logicalId": "hermes.worker", "status": "launched",
                               "sessionName": self.session}]}}],
            }))
        if cmd == "ps":
            if self.ps_failure:
                return self.ps_failure
            activity = self.activities.pop(0) if len(self.activities) > 1 else self.activities[0]
            if activity is None:
                return self._ok("[]")
            node = {
                "rigId": RIG_ID, "nodeId": "01000000000000000000000006", "canonicalSessionName": self.session,
                "sessionStatus": "running", "startupStatus": self.startup, "latestError": None,
                "agentActivity": activity, **self.node_overrides,
            }
            return self._ok(json.dumps([node]))
        if cmd == "send":
            self.sent_text = argv[-1]
            if self.send_override is not None:
                return self.send_override
            if self.result is not False:
                path = re.search(r"create (\S+hermes-result-[0-9a-f]+\.json)", self.sent_text).group(1)
                if isinstance(self.result, bytes):
                    Path(path).write_bytes(self.result)
                else:
                    Path(path).write_text(
                        self.result if isinstance(self.result, str) else json.dumps(self.result)
                    )
            return self._ok(json.dumps({"ok": True, "sent": True, "sessionName": self.session}))
        if cmd == "seat" and argv[2] == "launch":
            if self.seat_launch_override is not None:
                return self.seat_launch_override
            return self._ok(json.dumps({
                "ok": True, "status": "ready", "sessionName": argv[3],
                "seat": {"rigId": RIG_ID, "rigName": self.rig_name, "logicalId": "hermes.worker"},
                "generation": self.next_generation,
            }))
        if cmd == "transcript":
            return self._ok(json.dumps({"session": self.session, "content": "transcript tail"}))
        if cmd == "down":
            self.rigs_down.append(argv[2])
            if self.down_results:
                return self.down_results.pop(0)
            self.gone_rig_ids.add(argv[2])
            return self._ok(json.dumps({"rigId": argv[2], "sessionsKilled": 1, "deleted": True, "errors": []}))
        raise AssertionError(f"unexpected rig call {argv}")

    @property
    def session(self):
        return f"hermes-worker@{self.rig_name}"

    @staticmethod
    def _ok(stdout, returncode=0):
        return subprocess.CompletedProcess([], returncode, stdout, "")


@pytest.fixture
def clock():
    return FakeClock()


class FakeTimer:
    created = []

    def __init__(self, interval, function, args):
        self.interval, self.function, self.args = interval, function, args
        self.started = self.cancelled = False
        FakeTimer.created.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.function(*self.args)


@pytest.fixture(autouse=True)
def pool():
    FakeTimer.created = []
    seat_pool = _SeatPool(idle_seconds=120, timer_factory=FakeTimer)
    yield seat_pool
    seat_pool.drain()


def make_backend(tmp_path, clock, rig, which=lambda name: "/usr/bin/rig", utc_times=(T0,), pool=None, sprint_id="Sprint 07/Proof", ledger=None, cancel_event=None):
    sent_times = iter(utc_times)
    last = utc_times[-1]
    return OpenRigBackend(
        run_dir=tmp_path / "run",
        sprint_id=sprint_id,
        run_process=rig,
        which_func=which,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        utcnow=lambda: next(sent_times, last),
        poll_interval=2.0,
        seat_pool=pool if pool is not None else _CURRENT_POOL[0],
        ledger=ledger,
        cancel_event=cancel_event,
    )


_CURRENT_POOL = [None]


@pytest.fixture(autouse=True)
def _bind_pool(pool):
    _CURRENT_POOL[0] = pool
    yield
    _CURRENT_POOL[0] = None


def make_request(tmp_path, agent="claude", prompt="Implement the thing", timeout=60, worktree_name="worktree"):
    worktree = tmp_path / worktree_name
    worktree.mkdir(parents=True, exist_ok=True)
    metadata = {"phase": "build"}
    if prompt is not None:
        metadata["prompt"] = prompt
    return ExecutionRequest(
        agent_name=agent,
        command=("claude", "-p", "argv prompt"),
        cwd=worktree,
        timeout_seconds=timeout,
        stdout_file=tmp_path / "out.log",
        stderr_file=tmp_path / "err.log",
        metadata=metadata,
    )


def run(tmp_path, clock, rig, **request_kwargs):
    backend = make_backend(tmp_path, clock, rig)
    return backend, backend.execute(make_request(tmp_path, **request_kwargs))


def expect_error(code, tmp_path, clock, rig, **request_kwargs):
    backend = make_backend(tmp_path, clock, rig)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path, **request_kwargs))
    assert excinfo.value.code == code, excinfo.value.message
    return backend, excinfo.value


# --- registration ---------------------------------------------------------------


def test_registered_by_name(tmp_path):
    backend = default_backend_registry.get("openrig", run_dir=tmp_path, sprint_id="s", logger=None)
    assert isinstance(backend, OpenRigBackend)


# --- successful lifecycle -------------------------------------------------------


def test_successful_lifecycle_returns_verified_result(tmp_path, clock):
    rig = FakeRig(clock)
    backend, result = run(tmp_path, clock, rig)

    assert result.returncode == 0
    assert result.backend == "openrig"
    envelope = json.loads(result.stdout)
    assert ClaudeAdapter.parse_json(result.stdout, result.stderr)["result"] == "did the thing"
    assert envelope["is_error"] is False
    assert (tmp_path / "out.log").read_text() == result.stdout
    assert (tmp_path / "err.log").read_text() == ""
    assert [c[0] for c in rig.calls] == [
        "--version", "ps", "up", "ps", "send", "ps", "ps", "transcript",
    ]
    assert rig.rigs_down == []
    assert backend.seat_pool.idle_rig_ids() == [RIG_ID]
    assert result.runtime_metadata == {
        "openrig_version": "0.6.9",
        "openrig_rig_name": rig.rig_name,
        "openrig_runtime": "claude-code",
        "openrig_rig_id": RIG_ID,
        "openrig_session_name": rig.session,
        "openrig_node_id": "01000000000000000000000006",
        "openrig_generation": GEN,
        "openrig_turn_started": True,
        "openrig_seat_reused": False,
    }
    assert all(isinstance(v, (str, bool)) for v in result.runtime_metadata.values())
    backend.seat_pool.drain()
    assert rig.rigs_down == [RIG_ID]


def test_spec_isolates_seat_from_worktree_and_mirrors_hermes_permissions(tmp_path, clock):
    rig = FakeRig(clock)
    backend, _ = run(tmp_path, clock, rig)

    member = rig.spec["pods"][0]["members"][0]
    seat = Path(member["cwd"])
    worktree = (tmp_path / "worktree").resolve()
    assert seat != worktree and worktree not in seat.parents
    agent_dir = Path(member["agent_ref"].removeprefix("path:"))
    settings = json.loads((agent_dir / "runtime" / "hermes-settings.fragment.json").read_text())
    # Granted root is the worktree parent so sibling task worktrees of the job can reuse the seat.
    assert settings["permissions"]["additionalDirectories"] == [str(worktree.parent)]
    assert "Bash(git commit:*)" in settings["permissions"]["deny"]
    assert list((tmp_path / "worktree").iterdir()) == []


def test_completion_without_observed_start_still_requires_post_send_stop(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, FINISHED])
    _, result = run(tmp_path, clock, rig)
    assert result.returncode == 0
    assert result.runtime_metadata["openrig_turn_started"] is False


def test_failed_status_maps_to_nonzero_returncode(tmp_path, clock):
    rig = FakeRig(clock, result={"status": "failed", "summary": "tests are red"})
    _, result = run(tmp_path, clock, rig)
    assert result.returncode == 1
    assert result.stderr == "tests are red"
    assert json.loads(result.stdout)["is_error"] is True
    # A failed task with a valid result is still a clean protocol completion: seat is reusable.
    assert rig.rigs_down == []


# --- ownership ------------------------------------------------------------------


def test_each_execute_owns_a_unique_rig_and_releases_only_it(tmp_path, clock):
    rig_a, rig_b = FakeRig(clock), FakeRig(clock)
    backend_a, _ = run(tmp_path / "a", clock, rig_a)
    backend_b, _ = run(tmp_path / "b", clock, rig_b)
    backend_a.seat_pool.drain()

    assert rig_a.rig_name != rig_b.rig_name
    assert re.fullmatch(r"hermes-sprint-07-proof-[0-9a-f]{8}", rig_a.rig_name)
    for rig in (rig_a, rig_b):
        downs = [c for c in rig.calls if c[0] == "down"]
        assert downs == [["down", RIG_ID, "--delete", "--force", "--json"]]
        assert "kernel" not in json.dumps(downs) and "01000000000000000000000003" not in json.dumps(downs)


def test_session_owned_by_another_rig_fails_closed(tmp_path, clock):
    rig = FakeRig(clock)
    rig.node_overrides = {"rigId": "01000000000000000000000013"}
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


def test_up_reporting_a_different_rig_fails_closed_and_releases(tmp_path, clock):
    rig = FakeRig(clock)
    rig.up_override = lambda r: r._ok(json.dumps({
        "status": "completed", "rigId": RIG_ID, "errors": [],
        "stages": [{"stage": "import_rig", "detail": {"rigId": RIG_ID, "specName": "someone-else", "nodes": []}}],
    }))
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


# --- prompt transport -----------------------------------------------------------


def test_prompt_comes_from_metadata_and_is_passed_after_separator(tmp_path, clock):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig, prompt="--rig kernel do not treat me as a flag")

    send = next(c for c in rig.calls if c[0] == "send")
    separator = send.index("--")
    assert send[separator + 1] == rig.session
    assert send[separator + 2].startswith("--rig kernel do not treat me as a flag")
    assert "argv prompt" not in send[-1]
    assert "Hermes result protocol" in send[-1]


def test_missing_prompt_fails_before_any_rig_call(tmp_path, clock):
    rig = FakeRig(clock)
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig, prompt=None)
    assert rig.calls == []


def test_unsupported_runtime_fails_clearly(tmp_path, clock):
    rig = FakeRig(clock)
    _, err = expect_error("FAILED_OPENRIG_UNSUPPORTED_RUNTIME", tmp_path, clock, rig, agent="codex")
    assert "codex" in err.message
    assert rig.calls == []


# --- delivery is not completion -------------------------------------------------


def test_delivery_without_a_new_turn_times_out_instead_of_succeeding(tmp_path, clock):
    # Send succeeds and the result file even exists, but no hook event after the send.
    rig = FakeRig(clock, activities=[STARTUP_IDLE])
    expect_error("FAILED_TIMEOUT", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


def test_heuristic_activity_is_not_completion_evidence(tmp_path, clock):
    fake_stop = dict(FINISHED, evidenceSource="terminal_activity")
    stale_stop = dict(FINISHED, stale=True)
    rig = FakeRig(clock, activities=[STARTUP_IDLE, HEURISTIC, fake_stop, stale_stop])
    expect_error("FAILED_TIMEOUT", tmp_path, clock, rig)


def test_completion_without_result_file_fails_closed(tmp_path, clock):
    rig = FakeRig(clock, result=False)
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


@pytest.mark.parametrize("bad", ["not json", json.dumps({"status": "maybe", "summary": "x"}), json.dumps(["x"])])
def test_malformed_result_file_fails_closed(tmp_path, clock, bad):
    rig = FakeRig(clock, result=bad)
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)


def test_undelivered_send_fails(tmp_path, clock):
    rig = FakeRig(clock)
    rig.send_override = FakeRig._ok(json.dumps({"ok": False, "error": "Session not found"}), returncode=1)
    expect_error("FAILED_OPENRIG_DELIVERY", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


# --- timeout --------------------------------------------------------------------


def test_every_rig_call_receives_only_remaining_time(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, HEURISTIC, HEURISTIC, STARTED, FINISHED])
    run(tmp_path, clock, rig, timeout=60)
    task_timeouts = rig.timeouts[:-1]  # last call is the separately budgeted release
    assert task_timeouts[0] == 60
    # Non-poll calls get what is left of the task; node polls are also capped per call.
    polls = [t for c, t in zip(rig.calls, rig.timeouts) if c[:2] == ["ps", "--nodes"]]
    others = [t for c, t in zip(rig.calls[:-1], task_timeouts) if c[:2] != ["ps", "--nodes"]]
    assert others == sorted(others, reverse=True)
    assert polls and all(t <= POLL_QUERY_SECONDS for t in polls)
    assert task_timeouts[-1] <= 60 - 6


def test_subprocess_timeout_maps_to_failed_timeout(tmp_path, clock):
    rig = FakeRig(clock)

    def hanging(argv, **kwargs):
        if argv[1] == "send":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return rig(argv, **kwargs)

    backend = make_backend(tmp_path, clock, hanging)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path))
    assert excinfo.value.code == "FAILED_TIMEOUT"
    assert rig.rigs_down == [RIG_ID]


# --- startup / attention / session loss -----------------------------------------


@pytest.mark.parametrize("startup", ["attention_required", "failed"])
def test_startup_attention_fails_seat_not_ready(tmp_path, clock, startup):
    rig = FakeRig(clock, startup=startup)
    expect_error("FAILED_OPENRIG_SEAT_NOT_READY", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


def test_permission_prompt_during_startup_fails_seat_not_ready(tmp_path, clock):
    rig = FakeRig(clock, activities=[{"state": "needs_input", "reason": "permission_prompt"}])
    expect_error("FAILED_OPENRIG_SEAT_NOT_READY", tmp_path, clock, rig)


def test_permission_prompt_mid_task_fails_needs_input(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, {"state": "needs_input", "reason": "permission_prompt"}])
    expect_error("FAILED_OPENRIG_NEEDS_INPUT", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


def test_seat_disappearing_mid_task_fails_session_lost(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, None])
    expect_error("FAILED_OPENRIG_SESSION_LOST", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


def test_occupant_generation_change_fails_session_lost(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, hook("idle", "Stop", 5, generation="gen-2")])
    expect_error("FAILED_OPENRIG_SESSION_LOST", tmp_path, clock, rig)


# --- CLI / daemon failures ------------------------------------------------------


def test_missing_executable(tmp_path, clock):
    rig = FakeRig(clock)
    backend = make_backend(tmp_path, clock, rig, which=lambda name: None)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path))
    assert excinfo.value.code == "FAILED_OPENRIG_EXECUTABLE_MISSING"
    assert rig.calls == []


def test_unsupported_version_fails_closed(tmp_path, clock):
    rig = FakeRig(clock)
    rig.version = "0.7.0 (deadbeef)\n"
    expect_error("FAILED_OPENRIG_UNAVAILABLE", tmp_path, clock, rig)
    assert "up" not in [c[0] for c in rig.calls]


def test_daemon_failure_mid_task_fails_unavailable_and_releases(tmp_path, clock):
    rig = FakeRig(clock)
    rig.ps_failure = subprocess.CompletedProcess([], 1, "", "Daemon not running")
    expect_error("FAILED_OPENRIG_UNAVAILABLE", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


def test_invalid_json_fails_protocol(tmp_path, clock):
    rig = FakeRig(clock)
    rig.ps_failure = FakeRig._ok("<html>not json</html>")
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)


def test_nonzero_rig_up_fails_create_and_releases_any_returned_rig(tmp_path, clock):
    rig = FakeRig(clock)
    rig.up_override = lambda r: r._ok(json.dumps({"status": "failed", "rigId": RIG_ID, "errors": ["boom"]}), 1)
    expect_error("FAILED_OPENRIG_CREATE", tmp_path, clock, rig)
    assert rig.rigs_down == [RIG_ID]


def test_rig_up_without_rig_id_releases_nothing(tmp_path, clock):
    rig = FakeRig(clock)
    rig.up_override = lambda r: r._ok(json.dumps({"error": {"fact": "spec invalid"}}), 1)
    expect_error("FAILED_OPENRIG_CREATE", tmp_path, clock, rig)
    assert rig.rigs_down == []


# --- cleanup --------------------------------------------------------------------


def test_cleanup_after_success_leaves_the_pooled_seat_alone(tmp_path, clock):
    rig = FakeRig(clock)
    backend, _ = run(tmp_path, clock, rig)
    backend.cleanup(success=True)
    backend.cleanup(success=True)
    assert rig.rigs_down == []
    assert backend.seat_pool.idle_rig_ids() == [RIG_ID]


def test_cleanup_retries_a_failed_release_then_is_idempotent(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE])
    rig.down_results = [subprocess.CompletedProcess([], 1, "", "daemon hiccup")]
    backend = make_backend(tmp_path, clock, rig)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path))
    assert excinfo.value.code == "FAILED_TIMEOUT"
    assert backend.released_rig_ids == []

    backend.cleanup(success=False)
    backend.cleanup(success=False)
    assert rig.rigs_down == [RIG_ID, RIG_ID]
    assert backend.released_rig_ids == [RIG_ID]


def test_cleanup_treats_already_gone_rig_as_released(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE])
    rig.down_results = [
        subprocess.CompletedProcess([], 1, "", "daemon hiccup"),
        subprocess.CompletedProcess([], 2, json.dumps({"error": {"fact": f"No rig found matching '{RIG_ID}'."}}), ""),
    ]
    backend = make_backend(tmp_path, clock, rig)
    with pytest.raises(SprintRunnerError):
        backend.execute(make_request(tmp_path))
    backend.cleanup()
    assert backend.released_rig_ids == [RIG_ID]


# --- through Hermes -------------------------------------------------------------


def test_hermes_task_runs_through_openrig_and_verification_continues(tmp_path, clock):
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
    backends = []

    def factory(**kwargs):
        backend = OpenRigBackend(
            run_process=rig, which_func=lambda n: "/usr/bin/rig",
            monotonic=clock.monotonic, sleep=clock.sleep, utcnow=lambda: T0,
            seat_pool=_CURRENT_POOL[0], **kwargs,
        )
        backends.append(backend)
        return backend

    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "worktrees",
        run_dir=tmp_path / "run",
        agent_registry=AgentRegistry({ClaudeAdapter.name: ClaudeAdapter}),
        backend_registry=BackendRegistry({OpenRigBackend.name: factory}),
        job_id="job_openrig",
    )
    task = TaskNode(
        task_id="T1", job_id="job_openrig", description="Touch nothing",
        assigned_actor="claude", metadata={"execution_backend": "openrig", "timeout_seconds": 120},
    )
    result = asyncio.run(adapter.execute_task(task, AgentRun(
        run_id="r1", job_id="job_openrig", task_id="T1", actor_id="claude",
    )))

    assert result.status == "succeeded", result.error
    assert result.metadata["execution_backend"] == "openrig"
    assert result.metadata["backend_runtime_metadata"]["openrig_rig_id"] == RIG_ID
    assert "Touch nothing" in rig.sent_text
    # The runtime's per-task cleanup must not tear down a seat handed back to the job pool.
    assert rig.rigs_down == []
    assert backends[0].seat_pool.idle_rig_ids("job_openrig") == [RIG_ID]


# --- Codex review regressions ---------------------------------------------------


def test_stop_during_a_slow_send_is_not_completion_without_turn_start(tmp_path, clock):
    # Send began at T0 and was confirmed at T0+10; a Stop at +5 with no UserPromptSubmit
    # cannot be proven to follow our delivery.
    rig = FakeRig(clock, activities=[STARTUP_IDLE, FINISHED])
    backend = make_backend(tmp_path, clock, rig, utc_times=(T0, T0 + timedelta(seconds=10)))
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path))
    assert excinfo.value.code == "FAILED_TIMEOUT"


def test_turn_start_during_a_slow_send_proves_the_following_stop(tmp_path, clock):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, FINISHED])
    backend = make_backend(tmp_path, clock, rig, utc_times=(T0, T0 + timedelta(seconds=10)))
    result = backend.execute(make_request(tmp_path))
    assert result.runtime_metadata["openrig_turn_started"] is True


def test_missing_generation_fails_closed_before_send(tmp_path, clock):
    no_generation = {k: v for k, v in STARTUP_IDLE.items() if k != "generation"}
    rig = FakeRig(clock, activities=[no_generation])
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)
    assert "send" not in [c[0] for c in rig.calls]
    assert rig.rigs_down == [RIG_ID]


def test_lost_rig_up_response_reconciles_by_unique_name_and_releases_by_id(tmp_path, clock):
    rig = FakeRig(clock)

    def up_times_out(r):
        r.listed_rigs = [{"rigId": "01000000000000000000000008", "name": r.rig_name, "status": "running"}]
        raise subprocess.TimeoutExpired(["rig", "up"], 1)

    rig.up_override = up_times_out
    expect_error("FAILED_TIMEOUT", tmp_path, clock, rig)
    assert rig.rigs_down == ["01000000000000000000000008"]


def test_unparseable_rig_up_response_also_reconciles(tmp_path, clock):
    rig = FakeRig(clock)

    def garbage(r):
        r.listed_rigs = [{"rigId": "01000000000000000000000008", "name": r.rig_name, "status": "running"}]
        return r._ok("Error: something exploded")

    rig.up_override = garbage
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)
    assert rig.rigs_down == ["01000000000000000000000008"]


def test_orphan_reconcile_never_adopts_other_rigs(tmp_path, clock):
    rig = FakeRig(clock)

    def up_times_out(r):
        r.listed_rigs = [{"rigId": "01000000000000000000000009", "name": "hermes-someone-else", "status": "running"}]
        raise subprocess.TimeoutExpired(["rig", "up"], 1)

    rig.up_override = up_times_out
    expect_error("FAILED_TIMEOUT", tmp_path, clock, rig)
    assert rig.rigs_down == []


def test_non_utf8_result_file_fails_protocol(tmp_path, clock):
    rig = FakeRig(clock, result=b"\xff\xfe not utf-8")
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)


# --- Codex verification regressions ----------------------------------------------


def test_orphan_recovery_never_adopts_a_rig_that_existed_before_launch(tmp_path, clock):
    rig = FakeRig(clock)

    def collide(r):
        # A pre-existing rig already carries the generated name (snapshot taken in preflight).
        raise subprocess.TimeoutExpired(["rig", "up"], 1)

    rig.up_override = collide
    backend = make_backend(tmp_path, clock, rig)
    backend._rig_name = lambda: "hermes-collision-00000000"
    rig.listed_rigs = [{"rigId": "01000000000000000000000010", "name": "hermes-collision-00000000", "status": "running"}]
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path))
    assert excinfo.value.code == "FAILED_TIMEOUT"
    assert rig.rigs_down == []


def test_orphan_recovery_retries_until_a_late_rig_appears(tmp_path, clock):
    rig = FakeRig(clock)
    seen = {"ps_after_up": 0}
    original = FakeRig.__call__

    def up_times_out(r):
        raise subprocess.TimeoutExpired(["rig", "up"], 1)

    def late_listing(argv, **kwargs):
        if argv[1] == "ps" and "--nodes" not in argv and "--include-archived" not in argv and rig.rig_name:
            seen["ps_after_up"] += 1
            if seen["ps_after_up"] == 2:
                rig.listed_rigs = [{"rigId": "01000000000000000000000004", "name": rig.rig_name, "status": "running"}]
        return original(rig, argv, **kwargs)

    rig.up_override = up_times_out
    backend = make_backend(tmp_path, clock, late_listing)
    with pytest.raises(SprintRunnerError):
        backend.execute(make_request(tmp_path))
    assert seen["ps_after_up"] == 2
    assert rig.rigs_down == ["01000000000000000000000004"]


def test_orphan_recovery_is_bounded_after_a_timeout(tmp_path, clock):
    rig = FakeRig(clock)
    rig.up_override = lambda r: (_ for _ in ()).throw(subprocess.TimeoutExpired(["rig", "up"], 1))
    backend = make_backend(tmp_path, clock, rig)
    with pytest.raises(SprintRunnerError):
        backend.execute(make_request(tmp_path, timeout=60))
    ps_after_up = [t for c, t in zip(rig.calls, rig.timeouts) if c[0] == "ps"][1:]
    assert len(ps_after_up) == 3
    assert all(t <= 20 for t in ps_after_up)
    assert clock.now - 1000.0 <= 60 + 20


def test_os_error_from_teardown_does_not_mask_the_original_failure(tmp_path, clock):
    rig = FakeRig(clock, startup="failed")

    def down_explodes(argv, **kwargs):
        if argv[1] == "down":
            raise PermissionError("rig not executable")
        return rig(argv, **kwargs)

    backend = make_backend(tmp_path, clock, down_explodes)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path))
    assert excinfo.value.code == "FAILED_OPENRIG_SEAT_NOT_READY"
    assert backend.released_rig_ids == []


# --- warm seat reuse (D-005) ------------------------------------------------------

GEN2_STOP = hook("idle", "Stop", 20, generation="gen-2")
GEN2_STARTED = hook("running", "UserPromptSubmit", 31, generation="gen-2")
GEN2_FINISHED = hook("idle", "Stop", 35, generation="gen-2")


def second_task(tmp_path, clock, rig, pool, **kwargs):
    backend = make_backend(tmp_path, clock, rig, utc_times=(T0 + timedelta(seconds=30),), pool=pool, **kwargs)
    return backend, backend.execute(make_request(tmp_path, worktree_name="worktree-2"))


def test_second_task_of_the_job_reuses_the_seat_with_a_fresh_occupant(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, FINISHED, GEN2_STOP, GEN2_STARTED, GEN2_FINISHED])
    run(tmp_path, clock, rig)
    calls_before = len(rig.calls)

    _, result = second_task(tmp_path, clock, rig, pool)

    second = [c for c in rig.calls[calls_before:]]
    assert "up" not in [c[0] for c in second]
    launch = next(c for c in second if c[0] == "seat")
    assert launch[:5] == ["seat", "launch", rig.session, "--fresh", "--stop"]
    assert result.runtime_metadata["openrig_seat_reused"] is True
    assert result.runtime_metadata["openrig_generation"] == "gen-2"
    assert result.returncode == 0
    assert pool.idle_rig_ids() == [RIG_ID]
    assert rig.rigs_down == []


def test_reused_seat_is_not_ready_until_the_new_generation_reports_idle(tmp_path, clock, pool):
    # After the relaunch the old occupant's Stop (gen-1) is still visible; it must not count.
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, FINISHED, FINISHED, FINISHED, GEN2_STOP, GEN2_FINISHED])
    run(tmp_path, clock, rig)
    calls_before = len(rig.calls)

    _, result = second_task(tmp_path, clock, rig, pool)

    ps_polls = [c for c in rig.calls[calls_before:] if c[0] == "ps" and "--nodes" in c]
    assert len(ps_polls) >= 4
    assert result.runtime_metadata["openrig_turn_started"] is False


def test_other_jobs_never_receive_the_seat(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    rig.activities = [STARTUP_IDLE, hook("running", "UserPromptSubmit", 31), hook("idle", "Stop", 35)]

    second_task(tmp_path, clock, rig, pool, sprint_id="another-job")

    assert [c[0] for c in rig.calls].count("up") == 2
    assert "seat" not in [c[0] for c in rig.calls]


def test_worktree_outside_the_granted_root_gets_a_new_rig(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path / "repo-a", clock, rig)
    rig.activities = [STARTUP_IDLE, STARTED, FINISHED]

    backend = make_backend(tmp_path / "repo-b", clock, rig, pool=pool)
    backend.execute(make_request(tmp_path / "repo-b"))

    assert [c[0] for c in rig.calls].count("up") == 2


def test_a_failing_task_never_returns_its_seat_to_the_pool(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, {"state": "needs_input", "reason": "permission_prompt"}])
    expect_error("FAILED_OPENRIG_NEEDS_INPUT", tmp_path, clock, rig)
    assert pool.idle_rig_ids() == []
    assert rig.rigs_down == [RIG_ID]


def test_failed_fresh_relaunch_releases_the_leased_seat(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    rig.seat_launch_override = FakeRig._ok(json.dumps({"ok": False, "error": "session_live"}), returncode=1)

    with pytest.raises(SprintRunnerError) as excinfo:
        second_task(tmp_path, clock, rig, pool)
    assert excinfo.value.code == "FAILED_OPENRIG_SEAT_NOT_READY"
    assert rig.rigs_down == [RIG_ID]
    assert pool.idle_rig_ids() == []


def test_relaunch_reporting_another_rig_fails_closed(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    rig.seat_launch_override = FakeRig._ok(json.dumps({
        "ok": True, "sessionName": rig.session, "generation": "gen-2",
        "seat": {"rigId": "01000000000000000000000007"},
    }))
    with pytest.raises(SprintRunnerError) as excinfo:
        second_task(tmp_path, clock, rig, pool)
    assert excinfo.value.code == "FAILED_OPENRIG_SEAT_NOT_READY"
    assert rig.rigs_down == [RIG_ID]


def test_idle_seat_is_released_when_its_timer_fires(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    [timer] = FakeTimer.created
    assert timer.started and timer.interval == 120

    timer.fire()

    assert rig.rigs_down == [RIG_ID]
    assert pool.idle_rig_ids() == []


def test_reacquired_seat_cancels_its_idle_timer(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, FINISHED, GEN2_STOP, GEN2_STARTED, GEN2_FINISHED])
    run(tmp_path, clock, rig)
    first_timer = FakeTimer.created[0]

    second_task(tmp_path, clock, rig, pool)

    assert first_timer.cancelled
    first_timer.fire()
    assert rig.rigs_down == []


def test_a_seat_is_leased_to_one_task_at_a_time(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    worktree = (tmp_path / "worktree-2").resolve()
    worktree.mkdir()
    assert pool.acquire("Sprint 07/Proof", worktree) is not None
    assert pool.acquire("Sprint 07/Proof", worktree) is None


def test_same_backend_releases_a_reacquired_seat_when_the_fresh_relaunch_fails(tmp_path, clock, pool):
    # The sprint runner caches one backend per job, so a seat it pooled earlier must
    # become owned again when it is leased back.
    rig = FakeRig(clock)
    backend = make_backend(tmp_path, clock, rig, pool=pool)
    backend.execute(make_request(tmp_path))
    rig.seat_launch_override = FakeRig._ok(json.dumps({"ok": False, "error": "session_live"}), returncode=1)

    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path, worktree_name="worktree-2"))

    assert excinfo.value.code == "FAILED_OPENRIG_SEAT_NOT_READY"
    assert rig.rigs_down == [RIG_ID]
    assert pool.idle_rig_ids() == []


def test_relaunch_returning_the_previous_generation_is_not_fresh(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    rig.next_generation = GEN

    with pytest.raises(SprintRunnerError) as excinfo:
        second_task(tmp_path, clock, rig, pool)
    assert excinfo.value.code == "FAILED_OPENRIG_SEAT_NOT_READY"
    assert rig.rigs_down == [RIG_ID]


def test_a_stale_timer_callback_never_expires_a_later_idle_period(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, FINISHED, GEN2_STOP, GEN2_STARTED, GEN2_FINISHED])
    run(tmp_path, clock, rig)
    first_timer = FakeTimer.created[0]
    second_task(tmp_path, clock, rig, pool)

    # Simulate a callback that had already entered before cancel() took effect.
    first_timer.function(*first_timer.args)

    assert rig.rigs_down == []
    assert pool.idle_rig_ids() == [RIG_ID]


def test_failed_expiry_teardown_is_retried_by_drain(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    rig.down_results = [subprocess.CompletedProcess([], 1, "", "daemon hiccup")]

    FakeTimer.created[0].fire()
    assert pool.failed_rig_ids() == [RIG_ID]

    pool.drain()
    assert rig.rigs_down == [RIG_ID, RIG_ID]
    assert pool.failed_rig_ids() == []


def test_drain_waits_for_a_teardown_running_on_a_timer_thread(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    entered, unblock, drained = threading.Event(), threading.Event(), threading.Event()
    [seat] = [s for group in pool._idle.values() for s in group]
    real_release = seat.release

    def slow_release(rig_id):
        entered.set()
        unblock.wait(5)
        real_release(rig_id)

    seat.release = slow_release
    expiry = threading.Thread(target=FakeTimer.created[0].fire)
    expiry.start()
    assert entered.wait(5)
    drainer = threading.Thread(target=lambda: (pool.drain(), drained.set()))
    drainer.start()

    assert not drained.wait(0.2)
    unblock.set()
    assert drained.wait(5)
    expiry.join(5)
    assert rig.rigs_down == [RIG_ID]


def test_a_timer_that_fails_to_start_leaves_no_leasable_seat(tmp_path, clock, pool):
    def broken_start(self):
        raise RuntimeError("can't start new thread")

    original = FakeTimer.start
    FakeTimer.start = broken_start
    try:
        rig = FakeRig(clock)
        with pytest.raises(RuntimeError):
            run(tmp_path, clock, rig)
    finally:
        FakeTimer.start = original

    assert pool.idle_rig_ids() == []
    assert pool._timers == {}
    assert rig.rigs_down == [RIG_ID]


def test_drain_reissues_a_teardown_stuck_past_its_wait(tmp_path, clock, pool):
    rig = FakeRig(clock)
    run(tmp_path, clock, rig)
    entered, unblock = threading.Event(), threading.Event()
    [seat] = [s for group in pool._idle.values() for s in group]
    real_release = seat.release
    stuck = [True]

    def release(rig_id):
        if stuck.pop() if stuck else False:
            entered.set()
            unblock.wait(5)
        real_release(rig_id)

    seat.release = release
    expiry = threading.Thread(target=FakeTimer.created[0].fire)
    expiry.start()
    assert entered.wait(5)

    pool.drain(wait_seconds=0.1)

    # Drain did not return with the rig still up: it issued its own teardown by id.
    assert rig.rigs_down == [RIG_ID]
    unblock.set()
    expiry.join(5)
    assert pool.failed_rig_ids() == []


# --- job-end release ------------------------------------------------------------


def fake_seat(job, rig_id, releases, granted_root):
    return _Seat(
        job=job, rig_id=rig_id, rig_name=f"name-{rig_id}", session="s",
        rig_dir=granted_root / rig_id, granted_root=granted_root,
        release=releases.append,
    )


def test_release_job_releases_the_jobs_idle_seats_once(pool, tmp_path):
    released = []
    pool.put(fake_seat("job-a", "01A", released, tmp_path))
    pool.put(fake_seat("job-a", "01B", released, tmp_path))

    assert pool.release_job("job-a") == 2
    assert sorted(released) == ["01A", "01B"]
    # Second call: nothing left for this job, so nothing is torn down again.
    assert pool.release_job("job-a") == 0
    assert sorted(released) == ["01A", "01B"]
    assert pool.idle_rig_ids() == []


def test_release_job_for_an_unknown_job_is_a_noop(pool, tmp_path):
    released = []
    pool.put(fake_seat("job-a", "01A", released, tmp_path))

    assert pool.release_job("nobody") == 0
    assert released == []
    assert pool.idle_rig_ids("job-a") == ["01A"]


def test_release_job_leaves_other_jobs_and_leased_seats_alone(pool, tmp_path):
    released = []
    root = tmp_path / "root"
    pool.put(fake_seat("job-a", "01A", released, root))
    pool.put(fake_seat("job-b", "01B", released, tmp_path / "other"))
    leased = pool.acquire("job-a", root / "wt")
    assert leased is not None

    assert pool.release_job("job-a") == 0
    assert released == []
    assert pool.idle_rig_ids("job-b") == ["01B"]


def test_release_job_cancels_the_timer_so_a_late_expiry_cannot_release_again(pool, tmp_path):
    released = []
    pool.put(fake_seat("job-a", "01A", released, tmp_path))
    timer = FakeTimer.created[-1]

    pool.release_job("job-a")
    assert timer.cancelled
    pool._expire(*timer.args)  # a callback that was already running when the job ended

    assert released == ["01A"]


def test_failed_job_release_is_kept_and_retried_by_the_next_release(pool, tmp_path):
    calls = []

    def flaky(rig_id):
        calls.append(rig_id)
        if len(calls) == 1:
            raise SprintRunnerError("FAILED_OPENRIG_UNAVAILABLE", "daemon hiccup")

    seat = fake_seat("job-a", "01A", [], tmp_path)
    seat.release = flaky
    pool.put(seat)

    pool.release_job("job-a")
    assert pool.failed_rig_ids() == ["01A"]

    assert pool.release_job("job-a") == 1
    assert calls == ["01A", "01A"]
    assert pool.failed_rig_ids() == []


# --- ownership ledger and crash reconciliation ----------------------------------


def ledger_rig_ids(directory):
    ids = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            ids += json.loads(path.read_text(encoding="utf-8"))["rigIds"]
    return ids


def dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def dead_owner_ledger(directory, rig_id, pid=None):
    """What a crashed Hermes process leaves behind: its entry, owned by a pid that is gone."""
    OwnershipLedger(directory, identity=lambda: (pid or dead_pid(), None)).record(rig_id)


def test_launched_rig_stays_in_the_ledger_while_pooled_and_leaves_it_on_release(tmp_path, clock, pool):
    rig = FakeRig(clock)
    backend, _ = run(tmp_path, clock, rig)

    assert ledger_rig_ids(backend.ledger.directory) == [RIG_ID]  # pooled seats are still ours

    assert backend.release_job("Sprint 07/Proof") == 1
    assert rig.rigs_down == [RIG_ID]
    assert ledger_rig_ids(backend.ledger.directory) == []
    assert list(backend.ledger.directory.glob("*.json")) == []


def test_double_release_job_on_the_backend_tears_the_rig_down_once(tmp_path, clock, pool):
    rig = FakeRig(clock)
    backend, _ = run(tmp_path, clock, rig)

    backend.release_job("Sprint 07/Proof")
    assert backend.release_job("Sprint 07/Proof") == 0
    assert rig.rigs_down == [RIG_ID]


def test_ledger_survives_a_crash_and_the_next_backend_reconciles_it(tmp_path, clock, pool):
    ledger_dir = tmp_path / "ledger"
    dead = dead_pid()
    # The task fails (no result file), so its release runs; that release fails too, and the
    # rig is left running when the process goes away.
    crashed_rig = FakeRig(clock, result=False)
    crashed_rig.down_results = [subprocess.CompletedProcess([], 1, "", "daemon hiccup")]
    crashed = make_backend(tmp_path, clock, crashed_rig, ledger=OwnershipLedger(ledger_dir, identity=lambda: (dead, None)))
    with pytest.raises(SprintRunnerError) as excinfo:
        crashed.execute(make_request(tmp_path))
    assert excinfo.value.code == "FAILED_OPENRIG_PROTOCOL"
    assert crashed_rig.rigs_down == [RIG_ID]
    assert ledger_rig_ids(ledger_dir) == [RIG_ID]

    rig = FakeRig(clock)
    survivor = make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir))
    calls_before = len(rig.calls)
    survivor.execute(make_request(tmp_path))

    names = [c[0] for c in rig.calls[calls_before:]]
    assert names.index("down") < names.index("up")  # reconciled before the new task launched
    assert rig.calls[calls_before + names.index("down")][1] == RIG_ID
    assert not list(ledger_dir.glob(f"{dead}-*.json"))


def test_live_owner_entries_are_skipped_by_reconcile(tmp_path, clock, pool):
    ledger_dir = tmp_path / "ledger"
    OwnershipLedger(ledger_dir).record("01000000000000000000000005")  # this process: alive
    rig = FakeRig(clock)
    backend = make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir))

    backend.execute(make_request(tmp_path))

    assert "01000000000000000000000005" not in rig.rigs_down
    assert "01000000000000000000000005" in ledger_rig_ids(ledger_dir)


@pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="needs /proc start times")
def test_reused_pid_is_treated_as_a_dead_owner(tmp_path, clock, pool):
    ledger_dir = tmp_path / "ledger"
    # Same pid as this live process, but a different process start time: the pid was reused.
    OwnershipLedger(ledger_dir, identity=lambda: (os.getpid(), "start-of-another-process")).record("01000000000000000000000011")
    rig = FakeRig(clock)

    make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir)).execute(make_request(tmp_path))

    assert rig.rigs_down == ["01000000000000000000000011"]
    assert "01000000000000000000000011" not in ledger_rig_ids(ledger_dir)


def test_non_ledger_rigs_are_never_released(tmp_path, clock, pool):
    ledger_dir = tmp_path / "ledger"
    dead_owner_ledger(ledger_dir, "01000000000000000000000014")
    rig = FakeRig(clock)
    # Kernel and a Hermes-named rig that is not in the ledger: a name match must not free them.
    rig.listed_rigs = [{"rigId": "01000000000000000000000002", "name": "hermes-sprint-07-deadbeef", "status": "running"}]

    make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir)).execute(make_request(tmp_path))

    assert rig.rigs_down == ["01000000000000000000000014"]


def test_failed_reconcile_release_is_kept_and_retried_by_a_later_run(tmp_path, clock, pool):
    ledger_dir = tmp_path / "ledger"
    dead_owner_ledger(ledger_dir, "01000000000000000000000014")
    first = FakeRig(clock)
    first.down_results = [subprocess.CompletedProcess([], 1, "", "daemon hiccup")]

    # The stale release fails, but that must not fail this task.
    make_backend(tmp_path, clock, first, ledger=OwnershipLedger(ledger_dir)).execute(make_request(tmp_path))
    assert first.rigs_down == ["01000000000000000000000014"]
    assert "01000000000000000000000014" in ledger_rig_ids(ledger_dir)

    second = FakeRig(clock)
    make_backend(tmp_path, clock, second, ledger=OwnershipLedger(ledger_dir), sprint_id="Sprint 08").execute(
        make_request(tmp_path, worktree_name="worktree-2")
    )
    assert second.rigs_down == ["01000000000000000000000014"]
    assert "01000000000000000000000014" not in ledger_rig_ids(ledger_dir)


def test_ledger_write_failure_fails_closed_and_releases_the_rig(tmp_path, clock, pool):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("x", encoding="utf-8")  # the ledger directory cannot be created under a file
    rig = FakeRig(clock)
    backend = make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(blocked))

    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path))

    assert excinfo.value.code == "FAILED_OPENRIG_UNAVAILABLE"
    assert rig.rigs_down == [RIG_ID]


def test_entries_from_another_host_are_never_judged_dead_here(tmp_path, clock, pool):
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    # The pid 999999 means nothing on this machine; the owner lives on another host sharing the state dir.
    foreign = ledger_dir / "other-machine-999999-unknown.json"
    foreign.write_text(json.dumps(
        {"host": "other-machine", "pid": 999999, "started": None, "rigIds": ["01000000000000000000000001"]}
    ), encoding="utf-8")
    rig = FakeRig(clock)

    make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir)).execute(make_request(tmp_path))

    assert rig.rigs_down == []
    assert foreign.exists()


def test_corrupt_ledger_file_is_kept_and_never_released(tmp_path, clock, pool):
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    corrupt = ledger_dir / "999999-unknown.json"
    corrupt.write_text("{not json", encoding="utf-8")
    rig = FakeRig(clock)

    make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir)).execute(make_request(tmp_path))

    assert corrupt.read_text(encoding="utf-8") == "{not json"
    assert rig.rigs_down == []
# --- out-of-band cancel ---------------------------------------------------------


def cancel_on_nth(rig, event, when, n=1):
    """Wrap the fake rig; set `event` when the n-th call matching `when(argv)` is made."""
    seen = [0]

    def call(argv, **kwargs):
        if when(argv):
            seen[0] += 1
            if seen[0] == n:
                event.set()
        return rig(argv, **kwargs)

    return call


def node_poll(argv):
    return argv[1] == "ps" and "--nodes" in argv


def cancelled_execute(tmp_path, clock, rig, event, pool, utc_times=(T0,), **request_kwargs):
    backend = make_backend(tmp_path, clock, rig, pool=pool, utc_times=utc_times, cancel_event=event)
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path, **request_kwargs))
    assert excinfo.value.code == "FAILED_OPENRIG_CANCELLED", excinfo.value.message
    return backend


def assert_released_by_id(rig, backend, rig_id=RIG_ID):
    assert rig.rigs_down == [rig_id]
    assert rig.calls[-1] == ["down", rig_id, "--delete", "--force", "--json"]
    assert backend.released_rig_ids == [rig_id]


def test_cancel_before_launch_creates_no_rig(tmp_path, clock, pool):
    rig = FakeRig(clock)
    event = threading.Event()
    event.set()

    cancelled_execute(tmp_path, clock, rig, event, pool)

    assert not any(c[0] in ("up", "send") for c in rig.calls)
    assert rig.rigs_down == []
    assert pool.idle_rig_ids() == []


def test_cancel_during_ready_wait_stops_polling_and_releases_by_id(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[HEURISTIC])  # startup is ready but no hook Stop ever arrives
    event = threading.Event()

    backend = cancelled_execute(tmp_path, clock, cancel_on_nth(rig, event, node_poll), event, pool)

    polls = [c for c in rig.calls if c[0] == "ps" and "--nodes" in c]
    assert len(polls) == 1, "the wait must stop at the next poll after cancel"
    assert not any(c[0] == "send" for c in rig.calls)
    assert_released_by_id(rig, backend)
    assert pool.idle_rig_ids() == []


def test_cancel_during_completion_wait_releases_by_id_and_never_pools(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, HEURISTIC])  # sent, turn started, never Stop
    event = threading.Event()

    # Poll 1 is the ready check; poll 2 is inside the completion wait, after the send.
    wrapped = cancel_on_nth(rig, event, node_poll, n=2)
    backend = cancelled_execute(tmp_path, clock, wrapped, event, pool)

    assert rig.sent_text is not None
    assert_released_by_id(rig, backend)
    assert pool.idle_rig_ids() == []
    assert backend.pooled_rig_ids == []


def test_cancel_after_completion_is_a_no_op(tmp_path, clock, pool):
    rig = FakeRig(clock)
    event = threading.Event()
    # Cancel arrives during post-completion transcript capture, after the protocol finished.
    wrapped = cancel_on_nth(rig, event, lambda argv: argv[1] == "transcript")
    backend = make_backend(tmp_path, clock, wrapped, pool=pool, cancel_event=event)

    result = backend.execute(make_request(tmp_path))

    assert event.is_set()
    assert result.returncode == 0
    assert result.runtime_metadata["openrig_rig_id"] == RIG_ID
    assert pool.idle_rig_ids() == [RIG_ID]
    assert rig.rigs_down == []
    assert backend.released_rig_ids == []


def test_cancelled_reused_seat_is_released_by_id_and_never_pooled(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, FINISHED, GEN2_STOP, GEN2_STARTED, GEN2_FINISHED])
    run(tmp_path, clock, rig)  # task 1 completes and warms the seat into the job's pool
    assert pool.idle_rig_ids() == [RIG_ID]

    event = threading.Event()
    # Task 2 leases the warm seat, relaunches it fresh, then is cancelled as it sends.
    wrapped = cancel_on_nth(rig, event, lambda argv: argv[1] == "send")
    backend = make_backend(
        tmp_path, clock, wrapped, utc_times=(T0 + timedelta(seconds=30),), pool=pool,
        cancel_event=event,
    )
    with pytest.raises(SprintRunnerError) as excinfo:
        backend.execute(make_request(tmp_path, worktree_name="worktree-2"))

    assert excinfo.value.code == "FAILED_OPENRIG_CANCELLED"
    assert any(c[:2] == ["seat", "launch"] for c in rig.calls), "task 2 must have reused the seat"
    assert_released_by_id(rig, backend)
    assert pool.idle_rig_ids() == []
    assert pool.failed_rig_ids() == [] and pool.inflight_rig_ids() == []
    assert pool.acquire("Sprint 07/Proof", tmp_path / "worktree-3") is None


def test_cancelling_the_hermes_task_releases_the_parked_seat_by_id(tmp_path, clock, pool):
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

    base = FakeRig(clock, activities=[HEURISTIC])  # never ready: the task parks in the ready wait
    in_flight = threading.Event()
    unblock = threading.Event()

    def parked(argv, **kwargs):
        if node_poll(argv):
            in_flight.set()
            unblock.wait(5)
        return base(argv, **kwargs)

    def factory(**kwargs):
        return OpenRigBackend(
            run_process=parked, which_func=lambda n: "/usr/bin/rig",
            monotonic=clock.monotonic, sleep=clock.sleep, utcnow=lambda: T0,
            seat_pool=_CURRENT_POOL[0], **kwargs,
        )

    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "worktrees",
        run_dir=tmp_path / "run",
        agent_registry=AgentRegistry({ClaudeAdapter.name: ClaudeAdapter}),
        backend_registry=BackendRegistry({OpenRigBackend.name: factory}),
        job_id="job_cancel",
    )
    task = TaskNode(
        task_id="T1", job_id="job_cancel", description="Touch nothing",
        assigned_actor="claude", metadata={"execution_backend": "openrig", "timeout_seconds": 120},
    )
    run_obj = AgentRun(run_id="r1", job_id="job_cancel", task_id="T1", actor_id="claude")

    async def cancel_while_parked():
        pending = asyncio.ensure_future(adapter.execute_task(task, run_obj))
        await asyncio.to_thread(in_flight.wait, 5)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        unblock.set()

    # asyncio.run waits for the worker thread, so the release has finished when it returns.
    asyncio.run(cancel_while_parked())

    # A cancel stops the wait at the next poll. Without it the fake clock would run the
    # wait to the 120 s task timeout (about 60 polls), which also releases the rig.
    polls = [c for c in base.calls if c[0] == "ps" and "--nodes" in c]
    assert len(polls) == 1
    assert not any(c[0] == "send" for c in base.calls)
    assert base.rigs_down == [RIG_ID]
    assert pool.idle_rig_ids("job_cancel") == []


# --- full-branch Codex review fixes ------------------------------------------------
def test_a_ledger_entry_that_is_a_rig_name_is_never_torn_down(tmp_path, clock, pool):
    # `rig down` resolves names too, so "kernel" in a dead owner's file must not reach it.
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    poisoned = ledger_dir / "host-999999-unknown.json"
    poisoned.write_text(json.dumps(
        {"host": socket.gethostname(), "pid": dead_pid(), "started": None, "rigIds": ["kernel"]}
    ), encoding="utf-8")
    rig = FakeRig(clock)

    make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir)).execute(make_request(tmp_path))

    assert "kernel" not in rig.rigs_down
    assert rig.rigs_down == []
    assert poisoned.exists()


def test_the_ledger_refuses_to_record_a_non_rig_id(tmp_path):
    with pytest.raises(ValueError):
        OwnershipLedger(tmp_path / "ledger").record("kernel")


def test_teardown_refuses_anything_but_a_rig_id(tmp_path, clock):
    backend = make_backend(tmp_path, clock, FakeRig(clock))
    with pytest.raises(SprintRunnerError) as excinfo:
        backend._release("kernel")
    assert excinfo.value.code == "FAILED_OPENRIG_PROTOCOL"


def _record_many(directory, prefix, count):
    ledger = OwnershipLedger(directory)
    for i in range(count):
        ledger.record(f"01{prefix}{i:023d}")


def test_concurrent_processes_never_lose_each_others_ledger_entries(tmp_path):
    # Another process forgets rigs while this one records: with only an in-process lock
    # the rewrite of a shared file could drop a live owner's new rigId.
    ledger_dir = tmp_path / "ledger"
    ctx = multiprocessing.get_context("fork")
    ledger = OwnershipLedger(ledger_dir)
    for i in range(40):
        ledger.record(f"01F{i:023d}")

    def forget_all():
        other = OwnershipLedger(ledger_dir)
        for i in range(40):
            other.forget(f"01F{i:023d}")

    forgetter = ctx.Process(target=forget_all)
    forgetter.start()
    _record_many(ledger_dir, "R", 40)
    forgetter.join(30)

    assert forgetter.exitcode == 0
    kept = ledger_rig_ids(ledger_dir)
    assert sorted(r for r in kept if r.startswith("01R")) == [f"01R{i:023d}" for i in range(40)]
    assert not any(r.startswith("01F") for r in kept)


def test_cancel_during_the_final_completion_poll_never_pools_the_seat(tmp_path, clock, pool):
    rig = FakeRig(clock)  # ready, started, then Stop on the 3rd node poll
    event = threading.Event()

    backend = cancelled_execute(tmp_path, clock, cancel_on_nth(rig, event, node_poll, n=3), event, pool)

    assert_released_by_id(rig, backend)
    assert pool.idle_rig_ids() == []


def test_a_hung_node_poll_still_sees_the_cancel(tmp_path, clock, pool):
    rig = FakeRig(clock, activities=[STARTUP_IDLE, STARTED, HEURISTIC])
    event = threading.Event()
    poll_timeouts = []

    def call(argv, **kwargs):
        if node_poll(argv) and rig.sent_text is not None:
            poll_timeouts.append(kwargs["timeout"])
            event.set()  # cancelled while the daemon hangs
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return rig(argv, **kwargs)

    backend = cancelled_execute(tmp_path, clock, call, event, pool, timeout=600)

    assert poll_timeouts == [POLL_QUERY_SECONDS]
    assert_released_by_id(rig, backend)


def test_a_seat_is_not_leasable_while_its_timer_is_still_starting(tmp_path, clock, pool):
    leased_meanwhile = []

    class RacingTimer(FakeTimer):
        def start(self):
            worktree = (tmp_path / "worktree-2").resolve()
            worktree.mkdir(exist_ok=True)
            leased_meanwhile.append(pool.acquire("Sprint 07/Proof", worktree))
            raise RuntimeError("can't start new thread")

    pool._timer_factory = RacingTimer
    rig = FakeRig(clock)
    with pytest.raises(RuntimeError):
        run(tmp_path, clock, rig)

    assert leased_meanwhile == [None]
    assert pool.idle_rig_ids() == []
    assert rig.rigs_down == [RIG_ID]


# --- merge-gate review fixes -------------------------------------------------------
def test_a_gone_rig_is_never_torn_down_by_a_rig_named_like_its_id(tmp_path, clock, pool):
    # `rig down <id>` falls back to a name match when the id no longer exists.
    ledger_dir = tmp_path / "ledger"
    stale = "01000000000000000000000014"
    dead_owner_ledger(ledger_dir, stale)
    rig = FakeRig(clock)
    rig.gone_rig_ids.add(stale)
    rig.listed_rigs = [{"rigId": "01000000000000000000000099", "name": stale, "status": "running"}]

    make_backend(tmp_path, clock, rig, ledger=OwnershipLedger(ledger_dir)).execute(make_request(tmp_path))

    assert stale not in rig.rigs_down
    assert "01000000000000000000000099" not in rig.rigs_down
    assert stale not in ledger_rig_ids(ledger_dir)  # already gone counts as released


def test_a_seat_returned_after_its_job_ended_is_torn_down_not_pooled(tmp_path, clock, pool):
    # A cancelled worker thread can finish after the engine already released the job.
    pool.release_job("Sprint 07/Proof")
    rig = FakeRig(clock)

    run(tmp_path, clock, rig)

    assert pool.idle_rig_ids() == []
    assert rig.rigs_down == [RIG_ID]


def test_backend_release_job_reports_a_failed_teardown_so_callers_can_retry(tmp_path, clock, pool):
    rig = FakeRig(clock)
    backend, _ = run(tmp_path, clock, rig)
    rig.down_results = [subprocess.CompletedProcess([], 1, "", "daemon hiccup")]

    with pytest.raises(SprintRunnerError):
        backend.release_job("Sprint 07/Proof")
    assert backend.release_job("Sprint 07/Proof") == 1
    assert rig.rigs_down == [RIG_ID, RIG_ID]
