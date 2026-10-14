"""OpenRigBackend unit tests against a scripted fake `rig` CLI (no live OpenRig)."""

import threading
import asyncio
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.claude import ClaudeAdapter
from agents.errors import SprintRunnerError
from runner.agents.registry import AgentRegistry
from runner.backends.base import ExecutionRequest
from runner.backends.openrig_backend import OpenRigBackend, _SeatPool
from runner.backends.registry import BackendRegistry, default_backend_registry
from runtime.execution import AgentRun
from runtime.hermes_adapter import HermesActorAdapter
from runtime.task_graph import TaskNode


T0 = datetime(2026, 10, 12, 5, 0, 0, tzinfo=timezone.utc)
RIG_ID = "01RIGOWNEDBYHERMES0000000001"
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

    def __call__(self, argv, capture_output, text, timeout):
        assert argv[0] == "rig" and capture_output and text
        assert timeout > 0
        self.calls.append(argv[1:])
        self.timeouts.append(timeout)
        cmd = argv[1]
        if cmd == "--version":
            return self._ok(self.version)
        if cmd == "ps" and "--nodes" not in argv:
            return self._ok(json.dumps(
                [{"rigId": "01KERNEL", "name": "kernel", "status": "running"}] + self.listed_rigs
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
                "rigId": RIG_ID, "nodeId": "01NODE", "canonicalSessionName": self.session,
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


def make_backend(tmp_path, clock, rig, which=lambda name: "/usr/bin/rig", utc_times=(T0,), pool=None, sprint_id="Sprint 07/Proof"):
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
        "openrig_node_id": "01NODE",
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
        assert "kernel" not in json.dumps(downs) and "01KERNEL" not in json.dumps(downs)


def test_session_owned_by_another_rig_fails_closed(tmp_path, clock):
    rig = FakeRig(clock)
    rig.node_overrides = {"rigId": "01SOMEONEELSE"}
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
    assert task_timeouts == sorted(task_timeouts, reverse=True)
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
        r.listed_rigs = [{"rigId": "01ORPHAN", "name": r.rig_name, "status": "running"}]
        raise subprocess.TimeoutExpired(["rig", "up"], 1)

    rig.up_override = up_times_out
    expect_error("FAILED_TIMEOUT", tmp_path, clock, rig)
    assert rig.rigs_down == ["01ORPHAN"]


def test_unparseable_rig_up_response_also_reconciles(tmp_path, clock):
    rig = FakeRig(clock)

    def garbage(r):
        r.listed_rigs = [{"rigId": "01ORPHAN", "name": r.rig_name, "status": "running"}]
        return r._ok("Error: something exploded")

    rig.up_override = garbage
    expect_error("FAILED_OPENRIG_PROTOCOL", tmp_path, clock, rig)
    assert rig.rigs_down == ["01ORPHAN"]


def test_orphan_reconcile_never_adopts_other_rigs(tmp_path, clock):
    rig = FakeRig(clock)

    def up_times_out(r):
        r.listed_rigs = [{"rigId": "01OTHER", "name": "hermes-someone-else", "status": "running"}]
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
    rig.listed_rigs = [{"rigId": "01PREEXISTING", "name": "hermes-collision-00000000", "status": "running"}]
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
        if argv[1] == "ps" and "--nodes" not in argv and rig.rig_name:
            seen["ps_after_up"] += 1
            if seen["ps_after_up"] == 2:
                rig.listed_rigs = [{"rigId": "01LATE", "name": rig.rig_name, "status": "running"}]
        return original(rig, argv, **kwargs)

    rig.up_override = up_times_out
    backend = make_backend(tmp_path, clock, late_listing)
    with pytest.raises(SprintRunnerError):
        backend.execute(make_request(tmp_path))
    assert seen["ps_after_up"] == 2
    assert rig.rigs_down == ["01LATE"]


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
        "seat": {"rigId": "01NOTOURS"},
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
