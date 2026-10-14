import atexit
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from agents.errors import SprintRunnerError

from . import events
from .base import ExecutionBackend, ExecutionResult
from .events import ExecutionTrace
from .openrig_ledger import OwnershipLedger


SUPPORTED_VERSION_PREFIX = "0.6."
# Hermes agent -> OpenRig runtime. Only runtimes whose hook rung OpenRig marks
# "standing" (exactly-once turn boundaries) can prove completion.
SUPPORTED_RUNTIMES = {"claude": "claude-code"}
WORKER_LOGICAL_ID = "hermes.worker"
RELEASE_TIMEOUT_SECONDS = 60
# Shared budget for finding a rig whose `rig up` response was lost (all retries together).
ORPHAN_RECOVERY_SECONDS = 20
ORPHAN_RECOVERY_ATTEMPTS = 3
SEND_IDLE_WAIT_SECONDS = 30
# One `rig ps --nodes` poll may block at most this long, so a cancel is seen promptly
# even when the daemon hangs. A timed-out poll is retried until the task deadline.
POLL_QUERY_SECONDS = 10
# How often a blocking `rig send` checks for an out-of-band cancel.
CANCEL_POLL_SECONDS = 0.5
# OpenRig rigIds are ULIDs. `rig down` also resolves rig *names*, so anything else
# (for example "kernel") must never reach it.
RIG_ID_PATTERN = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")
CANCELLED_CODE = "FAILED_OPENRIG_CANCELLED"
# An idle pooled seat is released after this long. release_job() ends a job sooner.
SEAT_IDLE_SECONDS = 120
# Shared budget for releasing rigs that a crashed Hermes process left in the ledger.
LEDGER_RECONCILE_SECONDS = 20


@dataclass
class _Seat:
    """One Hermes-owned single-seat rig, reusable within one job."""

    job: str
    rig_id: str
    rig_name: str
    session: str
    rig_dir: Path
    granted_root: Path
    release: object  # callable(rig_id) bound to the backend that created the rig
    generation: str = None  # occupant generation of the last task; a reuse must differ
    emitter: object = None  # the execution that last held the seat; receives its D-009 events

    @property
    def seat_dir(self):
        return self.rig_dir / "seat"

    def bind(self, emitter):
        self.emitter = emitter

    def event(self, kind, detail="", **fields):
        """Emit a D-009 event for this seat through the execution holding it. No holder, no event."""
        if self.emitter is None:
            return
        base = {
            "resource": events.resource("seat", self.rig_id, self.rig_name),
            "rig_id": self.rig_id,
            "session_name": self.session,
        }
        if self.generation is not None:
            base["generation"] = self.generation
        self.emitter.event(kind, detail, **{**base, **fields})


class _SeatPool:
    """Idle seats keyed by job. A seat is held by at most one task at a time.

    Once a seat leaves the pool for teardown (expiry or drain) the pool owns that
    teardown: a failed release is kept for drain() to retry, and drain() waits for
    teardowns already running on timer threads, then re-issues any still stuck.
    """

    def __init__(self, idle_seconds=SEAT_IDLE_SECONDS, timer_factory=threading.Timer):
        self.idle_seconds = idle_seconds
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._settled = threading.Condition(self._lock)
        self._idle = {}
        self._timers = {}  # rig_id -> (timer, token); the token fences stale callbacks
        self._failed = {}  # rig_id -> seat whose teardown raised; retried by drain()
        self._inflight = {}  # rig_id -> seat whose teardown is running right now
        # Jobs already ended by release_job(). A task of such a job that finishes late
        # (e.g. a cancelled worker thread) must not pool its seat: put() tears it down.
        self._closed_jobs = set()

    def acquire(self, job, worktree):
        worktree = Path(worktree).resolve()
        with self._lock:
            seats = self._idle.get(job, [])
            for seat in seats:
                if seat.granted_root == worktree or seat.granted_root in worktree.parents:
                    seats.remove(seat)
                    timer, _ = self._timers.pop(seat.rig_id, (None, None))
                    if timer is not None:
                        timer.cancel()
                    return seat
        return None

    def put(self, seat):
        token = object()
        timer = self._timer_factory(self.idle_seconds, self._expire, (seat.rig_id, token))
        timer.daemon = True
        expires_at = _iso(datetime.now(timezone.utc) + timedelta(seconds=self.idle_seconds))
        # Register the token first and publish the seat only after the timer started,
        # so no other task can lease a seat whose timer might still fail to start.
        with self._lock:
            if seat.job in self._closed_jobs:
                self._inflight[seat.rig_id] = seat
                closed = True
            else:
                self._timers[seat.rig_id] = (timer, token)
                closed = False
        if closed:
            self._release(seat)
            return
        try:
            timer.start()
        except BaseException:
            # The caller still owns the seat and tears it down.
            with self._lock:
                if self._timers.get(seat.rig_id, (None, None))[1] is token:
                    del self._timers[seat.rig_id]
            raise
        with self._lock:
            current = self._timers.get(seat.rig_id, (None, None))[1] is token
            if current and seat.job not in self._closed_jobs:
                self._idle.setdefault(seat.job, []).append(seat)
                # Emitted under the pool lock, so a concurrent release_job()/expiry, which needs
                # this lock to take the seat, can only report its release after this event.
                # Sinks never block and never call back into the pool.
                seat.event(events.RESOURCE_POOLED, "Seat returned to the job pool", expires_at=expires_at)
                pooled = True
            else:
                # The timer already fired, a drain ran, or the job ended while the timer was
                # starting: never publish, tear down now.
                if current:
                    del self._timers[seat.rig_id]
                self._inflight[seat.rig_id] = seat
                pooled = False
        if pooled:
            return
        timer.cancel()
        self._release(seat)

    def _expire(self, rig_id, token):
        with self._lock:
            # A callback that already entered when its timer was cancelled must not
            # remove the seat from a later idle period.
            if self._timers.get(rig_id, (None, None))[1] is not token:
                return
            del self._timers[rig_id]
            seat = next(
                (s for group in self._idle.values() for s in group if s.rig_id == rig_id), None
            )
            if seat is None:
                return
            self._idle[seat.job].remove(seat)
            self._inflight[rig_id] = seat
        self._release(seat)

    def _release(self, seat):
        """Tear one seat down; caller has already recorded it in _inflight."""
        try:
            seat.release(seat.rig_id)
            failed = False
        except Exception:  # noqa: BLE001 - logged by the releasing backend; kept for retry
            failed = True
        with self._lock:
            self._inflight.pop(seat.rig_id, None)
            if failed:
                self._failed[seat.rig_id] = seat
            else:
                self._failed.pop(seat.rig_id, None)
            self._settled.notify_all()

    def drain(self, wait_seconds=RELEASE_TIMEOUT_SECONDS):
        """Release every idle seat and retry failed teardowns (process exit, tests)."""
        with self._lock:
            # Let teardowns already running on timer threads finish first.
            settled = self._settled.wait_for(lambda: not self._inflight, timeout=wait_seconds)
            seats = [seat for group in self._idle.values() for seat in group]
            seats += list(self._failed.values())
            if not settled:
                # A timer thread is stuck; exit would kill it mid-teardown. Re-issue
                # the teardown here (rig down by id is idempotent: "No rig found" is success).
                seats += [s for s in self._inflight.values() if s not in seats]
            timers = [timer for timer, _ in self._timers.values()]
            self._idle.clear()
            self._timers.clear()
            self._failed.clear()
            for seat in seats:
                self._inflight[seat.rig_id] = seat
        for timer in timers:
            timer.cancel()
        for seat in seats:
            self._release(seat)

    def release_job(self, job):
        """Release every idle seat of `job` now. Returns how many seats were handed to teardown.

        Safe to repeat: a second call, or a call for an unknown job, finds nothing to do.
        Leased seats are not idle, so they stay with their lease. Failed teardowns of the
        job are retried here. A seat whose teardown fails stays in the ledger until one succeeds.
        """
        with self._lock:
            self._closed_jobs.add(job)
            seats = self._idle.pop(job, [])
            for seat in seats:
                timer, _ = self._timers.pop(seat.rig_id, (None, None))
                if timer is not None:
                    timer.cancel()
            retry = [seat for seat in self._failed.values() if seat.job == job]
            for seat in retry:
                del self._failed[seat.rig_id]
            seats += retry
            for seat in seats:
                self._inflight[seat.rig_id] = seat
        for seat in seats:
            self._release(seat)
        return len(seats)

    def idle_rig_ids(self, job=None):
        with self._lock:
            groups = [self._idle.get(job, [])] if job is not None else list(self._idle.values())
            return [seat.rig_id for group in groups for seat in group]

    def has_failed(self, job):
        with self._lock:
            return any(seat.job == job for seat in self._failed.values())

    def failed_rig_ids(self):
        with self._lock:
            return list(self._failed)

    def inflight_rig_ids(self):
        with self._lock:
            return list(self._inflight)


_POLL_TIMED_OUT = object()


def _openrig_home():
    return Path(os.environ.get("OPENRIG_HOME") or Path.home() / ".openrig")


def daemon_down_by_id(rig_id, timeout):
    """Tear a rig down through the local daemon's id-only `POST /api/down`.

    Returns the daemon's JSON payload. An unknown id (404) returns the same "No rig found"
    shape the CLI prints, so callers treat it as already released. Never resolves names.
    """
    try:
        status = json.loads((_openrig_home() / "daemon.json").read_text(encoding="utf-8"))
        url = f"http://{status.get('host') or '127.0.0.1'}:{int(status['port'])}/api/down"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SprintRunnerError(
            "FAILED_OPENRIG_UNAVAILABLE", f"OpenRig daemon address unknown: {exc}"
        ) from exc
    body = json.dumps({"rigId": rig_id, "delete": True, "force": True}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"error": {"fact": f"No rig found with id {rig_id}"}}
        text = exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        raise SprintRunnerError(
            "FAILED_OPENRIG_UNAVAILABLE", f"OpenRig daemon unreachable for teardown of {rig_id}: {exc}"
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": {"fact": text[:200]}}


def is_rig_id(value):
    return isinstance(value, str) and RIG_ID_PATTERN.fullmatch(value) is not None


DEFAULT_SEAT_POOL = _SeatPool()
atexit.register(DEFAULT_SEAT_POOL.drain)


class OpenRigBackend(ExecutionBackend):
    """Run one task on a Hermes-owned single-seat OpenRig rig.

    OpenRig owns the seat lifecycle; Hermes owns everything else. Each execute()
    leases a warm seat of the same job (giving it a fresh occupant) or launches a
    new rig, proves completion from runtime-hook evidence plus a nonce-bound result
    file, and returns the seat to the per-job pool. Any failure tears the rig down
    by its exact rigId.
    """

    name = "openrig"

    @classmethod
    def supports_agent(cls, agent_name):
        return agent_name in SUPPORTED_RUNTIMES

    def __init__(
        self,
        run_dir,
        sprint_id,
        logger=None,
        run_process=None,
        popen=None,
        which_func=None,
        rig_executable="rig",
        poll_interval=2.0,
        monotonic=None,
        sleep=None,
        utcnow=None,
        seat_pool=None,
        ledger=None,
        daemon_down=None,
        cancel_event=None,
        event_sink=None,
        **kwargs,
    ):
        self.run_dir = Path(run_dir)
        self.sprint_id = str(sprint_id)
        self.event_sink = event_sink
        self.logger = logger
        self.rig_executable = rig_executable
        self.poll_interval = poll_interval
        self._run_process = run_process or subprocess.run
        # Interruptible path for the one call that can block for long (`rig send --wait-for-idle`).
        # Only used in production (or when a test injects it); an injected run_process keeps the old path.
        self._popen = popen if popen is not None else (subprocess.Popen if run_process is None else None)
        self._which = which_func or shutil.which
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self.openrig_dir = self.run_dir / "openrig"
        self.owned_rig_ids = []
        self.released_rig_ids = []
        self.pooled_rig_ids = []
        self.seat_pool = seat_pool if seat_pool is not None else DEFAULT_SEAT_POOL
        self.ledger = ledger if ledger is not None else OwnershipLedger()
        self._daemon_down = daemon_down or daemon_down_by_id
        # Set by the caller to stop this task out of band. Checked at step boundaries only.
        self._cancel_event = cancel_event
        self._preexisting_rig_ids = set()

    # -- contract -------------------------------------------------------------

    def execute(self, request):
        trace = self.trace(self.sprint_id, cancel_codes=(CANCELLED_CODE,))
        trace.started(f"OpenRig task for agent '{request.agent_name}' started")
        try:
            return self._execute(request, trace)
        except BaseException as exc:
            trace.fail(exc)
            raise

    def _execute(self, request, trace):
        deadline = self._monotonic() + request.timeout_seconds
        runtime = SUPPORTED_RUNTIMES.get(request.agent_name)
        if runtime is None:
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNSUPPORTED_RUNTIME",
                f"OpenRig backend does not support agent '{request.agent_name}'; "
                f"supported: {', '.join(sorted(SUPPORTED_RUNTIMES))}",
            )
        prompt = request.metadata.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL",
                "OpenRig backend requires request.metadata['prompt']",
            )

        version = self.preflight(deadline)
        self._check_cancelled("before a seat was leased")
        nonce = secrets.token_hex(8)
        metadata = {"openrig_version": version, "openrig_runtime": runtime}
        seat = self.seat_pool.acquire(self.sprint_id, request.cwd)

        try:
            if seat is not None:
                # This lease owns the seat again until it is handed back to the pool.
                if seat.rig_id in self.pooled_rig_ids:
                    self.pooled_rig_ids.remove(seat.rig_id)
                if seat.rig_id not in self.owned_rig_ids:
                    self.owned_rig_ids.append(seat.rig_id)
                seat.bind(trace)
                self._bind_seat(trace, seat)
                expected_generation = self._fresh_occupant(seat, deadline)
                trace.bind(reused=True, generation=expected_generation)
                trace.event(events.RESOURCE_ACQUIRED, f"Pooled seat {seat.session} leased with a fresh occupant")
            else:
                seat = self._new_seat(runtime, request.cwd, deadline)
                seat.bind(trace)
                self._bind_seat(trace, seat)
                trace.bind(reused=False)
                expected_generation = None
                trace.event(events.RESOURCE_ACQUIRED, f"New seat {seat.session} launched")
            metadata.update(
                openrig_rig_name=seat.rig_name,
                openrig_rig_id=seat.rig_id,
                openrig_session_name=seat.session,
                openrig_seat_reused=expected_generation is not None,
            )

            ready = self._wait_until_ready(
                seat.rig_name, seat.rig_id, seat.session, deadline, expected_generation,
            )
            generation = ready["agentActivity"].get("generation")
            if not isinstance(generation, str) or not generation:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_PROTOCOL",
                    f"OpenRig seat {seat.session} reported no occupant generation",
                )
            metadata.update(openrig_node_id=ready.get("nodeId"), openrig_generation=generation)
            trace.bind(generation=generation, node_id=ready.get("nodeId"))
            trace.event(events.RESOURCE_READY, f"Seat {seat.session} is idle and ready for the prompt")

            result_file = seat.seat_dir / f"hermes-result-{nonce}.json"
            send_started = self._utcnow()
            self._send(seat.session, self._task_text(prompt, request.cwd, result_file), deadline)
            send_confirmed = self._utcnow()
            trace.event(events.RUNNING, "Prompt delivered; waiting for the completion hook")
            started = self._wait_for_completion(
                seat.rig_name, seat.rig_id, seat.session,
                send_started, send_confirmed, generation, deadline,
            )
            metadata["openrig_turn_started"] = started

            outcome = self._read_result(result_file)
            self._save_transcript(seat.session, seat.rig_dir / f"transcript-{nonce}.txt", deadline)
            trace.finish(f"Task reported {outcome['status']}")

            # Clean protocol completion: the seat is healthy enough to serve the job again.
            seat.generation = generation
            self.seat_pool.put(seat)
            self.pooled_rig_ids.append(seat.rig_id)
        except BaseException as exc:
            # Recorded before the rig is released, so the failure precedes its release events.
            trace.fail(exc)
            raise
        finally:
            # Covers rigs recorded by _launch even when it raised afterwards.
            for owned in list(self.owned_rig_ids):
                if owned not in self.released_rig_ids and owned not in self.pooled_rig_ids:
                    if seat is not None and seat.rig_id == owned:
                        self._release_quietly(owned, emitter=seat, label=seat.rig_name)
                    else:
                        self._release_quietly(owned, emitter=trace)

        unreleased = [
            r for r in self.owned_rig_ids
            if r not in self.released_rig_ids and r not in self.pooled_rig_ids
        ]
        if unreleased:
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE",
                f"OpenRig rig(s) {', '.join(unreleased)} could not be released and may still be running",
            )

        succeeded = outcome["status"] == "succeeded"
        envelope = {
            "type": "result",
            "subtype": "success" if succeeded else "error_during_execution",
            "is_error": not succeeded,
            "result": outcome["summary"],
            "backend": self.name,
        }
        stdout = json.dumps(envelope)
        stderr = "" if succeeded else outcome["summary"]
        request.stdout_file.parent.mkdir(parents=True, exist_ok=True)
        request.stdout_file.write_text(stdout, encoding="utf-8")
        request.stderr_file.write_text(stderr, encoding="utf-8")
        return ExecutionResult(
            command=tuple(request.command),
            returncode=0 if succeeded else 1,
            stdout=stdout,
            stderr=stderr,
            backend=self.name,
            runtime_metadata={k: v for k, v in metadata.items() if v is not None},
        )

    def cleanup(self, success=False):
        # Seats handed back to the pool belong to the pool, not to this lease.
        for rig_id in list(self.owned_rig_ids):
            if rig_id not in self.released_rig_ids and rig_id not in self.pooled_rig_ids:
                self._release(rig_id)

    def release_job(self, job):
        """Release the job's pooled seats now instead of waiting for the idle timer."""
        released = self.seat_pool.release_job(job)
        if self.seat_pool.has_failed(job):
            # Kept in the pool for retry: a later release_job() or drain() tries again.
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE",
                f"OpenRig seats of job {job} could not be released; kept for retry",
            )
        return released

    # -- lifecycle steps ------------------------------------------------------

    def preflight(self, deadline):
        if self._which(self.rig_executable) is None:
            raise SprintRunnerError(
                "FAILED_OPENRIG_EXECUTABLE_MISSING",
                f"OpenRig executable was not found: {self.rig_executable}",
            )
        version_text = self._run(["--version"], deadline, "FAILED_OPENRIG_UNAVAILABLE")
        match = re.match(r"\s*(\d+\.\d+\.\d+)", version_text)
        if match is None or not match.group(1).startswith(SUPPORTED_VERSION_PREFIX):
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE",
                f"Unsupported OpenRig version {version_text.strip()!r}; "
                f"expected {SUPPORTED_VERSION_PREFIX}x",
            )
        rigs = self._run_json(["ps", "--json"], deadline, "FAILED_OPENRIG_UNAVAILABLE")
        if not isinstance(rigs, list):
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", "rig ps --json did not return a list"
            )
        # Snapshot before launch: orphan recovery may only adopt rigs absent from it.
        self._preexisting_rig_ids = {
            r.get("rigId") for r in rigs if isinstance(r, dict) and r.get("rigId")
        }
        self._reconcile_ledger(deadline)
        return match.group(1)

    def _reconcile_ledger(self, deadline):
        """Release rigs that a dead Hermes process launched and never released.

        Only exact rigIds from ledger entries of dead owners are released. A failed release
        stays in the ledger for the next preflight. It never fails the current task.
        """
        budget = min(self._monotonic() + LEDGER_RECONCILE_SECONDS, deadline)
        try:
            stale = self.ledger.stale_owners()
        except OSError as exc:
            self._log("warning", "OpenRig ledger could not be read: %s", exc)
            return
        for owner in stale:
            for rig_id in owner.rig_ids:
                if self._remaining(budget) <= 0:
                    self._log("warning", "OpenRig ledger reconcile budget spent; the rest waits for the next run")
                    return
                try:
                    self._release(rig_id, budget)
                except SprintRunnerError as exc:
                    self._log(
                        "warning",
                        "Stale OpenRig rig %s (owner pid %s) not released, kept for retry: %s",
                        rig_id, owner.pid, exc.message,
                    )
                else:
                    self._log("info", "Released OpenRig rig %s left by dead Hermes pid %s", rig_id, owner.pid)

    def _track(self, rig_id):
        """Own `rig_id` for cleanup and persist it before anything relies on it.

        Raises FAILED_OPENRIG_UNAVAILABLE if the ledger cannot be written. The caller's
        finally block then releases the rig, so a rig is never launched unrecorded.
        """
        if rig_id not in self.owned_rig_ids:
            self.owned_rig_ids.append(rig_id)
        try:
            self.ledger.record(rig_id)
        except (OSError, ValueError) as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE",
                f"could not record OpenRig rig {rig_id} in the ownership ledger: {exc}",
            ) from exc

    def _new_seat(self, runtime, worktree, deadline):
        rig_name = self._rig_name()
        rig_dir = self.openrig_dir / rig_name
        # Grant the worktree's parent so later tasks of this job (sibling worktrees)
        # can reuse the seat; the prompt still confines work to the task worktree.
        granted_root = Path(worktree).resolve().parent
        spec_path = self._write_spec(rig_dir, rig_dir / "seat", rig_name, runtime, granted_root)
        rig_id, session = self._launch(spec_path, rig_name, deadline)
        seat = _Seat(
            job=self.sprint_id, rig_id=rig_id, rig_name=rig_name, session=session,
            rig_dir=rig_dir, granted_root=granted_root, release=None,
        )
        seat.release = partial(self._release, emitter=seat, label=rig_name)
        return seat

    @staticmethod
    def _bind_seat(trace, seat):
        trace.bind(
            resource=events.resource("seat", seat.rig_id, seat.rig_name),
            rig_id=seat.rig_id,
            session_name=seat.session,
        )

    def _fresh_occupant(self, seat, deadline):
        """Replace a pooled seat's occupant with a blank conversation; return its generation."""
        payload = self._run_json(
            ["seat", "launch", seat.session, "--fresh", "--stop",
             "--reason", "hermes: fresh context for the next task", "--json"],
            deadline, "FAILED_OPENRIG_SEAT_NOT_READY", allow_failure_payload=True,
        )
        info = payload.get("seat") if isinstance(payload, dict) else None
        generation = payload.get("generation") if isinstance(payload, dict) else None
        if (
            not isinstance(info, dict)
            or payload.get("ok") is not True
            or info.get("rigId") != seat.rig_id
            or payload.get("sessionName") != seat.session
            or not isinstance(generation, str)
            or not generation
            or generation == seat.generation
        ):
            raise SprintRunnerError(
                "FAILED_OPENRIG_SEAT_NOT_READY",
                f"rig seat launch --fresh failed for {seat.session}: {_brief(payload)}",
            )
        self._log("info", "OpenRig seat %s relaunched fresh for reuse", seat.session)
        return generation

    def _write_spec(self, rig_dir, seat_dir, rig_name, runtime, granted_root):
        # Imported lazily: agents -> backends -> agents.claude would be circular.
        from agents.claude import CLAUDE_GIT_MUTATION_DENIALS

        agent_dir = rig_dir / "agent"
        (agent_dir / "runtime").mkdir(parents=True, exist_ok=True)
        seat_dir.mkdir(parents=True, exist_ok=True)
        settings = {
            "permissions": {
                "allow": ["Bash", "Edit", "Write", "Read"],
                "deny": list(CLAUDE_GIT_MUTATION_DENIALS),
                "additionalDirectories": [str(Path(granted_root).resolve())],
            }
        }
        _write_json(agent_dir / "runtime" / "hermes-settings.fragment.json", settings)
        _write_json(
            agent_dir / "runtime" / "claude-activity-hooks.json",
            {"openrig_activity_hooks": True},
        )
        # JSON is valid YAML; serializing avoids hand-built YAML injection.
        _write_json(agent_dir / "agent.yaml", {
            "name": "hermes-worker",
            "version": "1.0",
            "description": "Hermes-owned single-task worker seat",
            "defaults": {"runtime": runtime, "lifecycle": {"restore_policy": "relaunch_fresh"}},
            "profiles": {"default": {"uses": {
                "skills": [], "guidance": [], "subagents": [], "plugins": [],
                "runtime_resources": ["hermes-settings", "activity-hooks"],
            }}},
            "resources": {"runtime_resources": [
                {"id": "hermes-settings", "path": "runtime/hermes-settings.fragment.json",
                 "runtime": runtime, "type": "claude_settings_fragment"},
                {"id": "activity-hooks", "path": "runtime/claude-activity-hooks.json",
                 "runtime": runtime, "type": "claude_activity_hooks"},
            ]},
            "startup": {"files": [], "actions": []},
        })
        spec_path = rig_dir / "rig.yaml"
        _write_json(spec_path, {
            "version": "0.2",
            "name": rig_name,
            "pods": [{
                "id": "hermes",
                "label": "Hermes worker",
                "members": [{
                    "id": "worker",
                    "agent_ref": f"path:{agent_dir.resolve()}",
                    "profile": "default",
                    "runtime": runtime,
                    "cwd": str(seat_dir.resolve()),
                }],
                "edges": [],
            }],
            "edges": [],
        })
        return spec_path

    def _launch(self, spec_path, rig_name, deadline):
        args = ["up", str(spec_path), "--json"]
        try:
            if self._popen is not None and self._cancel_event is not None:
                # Interruptible: a cancel kills `rig up` mid-launch. Whatever it already created is
                # found by the orphan recovery below and released by id like any lost response.
                payload = self._run_json_interruptible(args, deadline, "FAILED_OPENRIG_CREATE")
            else:
                payload = self._run_json(args, deadline, "FAILED_OPENRIG_CREATE", allow_failure_payload=True)
        except SprintRunnerError:
            # The daemon may have created the rig even though its response was lost.
            self._adopt_orphan(rig_name)
            raise
        if not (isinstance(payload, dict) and payload.get("rigId")):
            self._adopt_orphan(rig_name)
        rig_id = payload.get("rigId") if isinstance(payload, dict) else None
        if isinstance(rig_id, str) and rig_id:
            # Track ownership before validating anything else so cleanup can release it.
            self._track(rig_id)
        if (
            not isinstance(rig_id, str)
            or not rig_id
            or payload.get("status") != "completed"
            or payload.get("errors")
        ):
            raise SprintRunnerError(
                "FAILED_OPENRIG_CREATE",
                f"rig up did not complete: {_brief(payload)}",
            )
        session = None
        for stage in payload.get("stages") or []:
            detail = stage.get("detail") if isinstance(stage, dict) else None
            if not isinstance(detail, dict) or stage.get("stage") != "import_rig":
                continue
            if detail.get("rigId") != rig_id or detail.get("specName") != rig_name:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_PROTOCOL", "rig up reported a different rig than requested"
                )
            for node in detail.get("nodes") or []:
                if isinstance(node, dict) and node.get("logicalId") == WORKER_LOGICAL_ID:
                    session = node.get("sessionName")
        if not isinstance(session, str) or not session:
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", "rig up did not report the worker session"
            )
        self._log("info", "OpenRig rig %s (%s) launched", rig_name, rig_id)
        return rig_id, session

    def _adopt_orphan(self, rig_name):
        """Record a rig created under our name whose ID `rig up` never returned.

        Only a rig that is new since the pre-launch snapshot and carries our random
        name is adopted; release is still by exact rigId. Retries are bounded by one
        shared budget so recovery cannot extend a timed-out request indefinitely.
        """
        budget = self._monotonic() + ORPHAN_RECOVERY_SECONDS
        for attempt in range(ORPHAN_RECOVERY_ATTEMPTS):
            if attempt:
                remaining = budget - self._monotonic()
                if remaining <= 0:
                    break
                self._sleep(min(self.poll_interval, remaining))
            try:
                rigs = self._run_json(["ps", "--json"], budget, "FAILED_OPENRIG_UNAVAILABLE")
            except SprintRunnerError as exc:
                self._log("warning", "Orphan check for OpenRig rig %s failed: %s", rig_name, exc.message)
                continue
            if not isinstance(rigs, list):
                continue
            matches = [
                r.get("rigId") for r in rigs
                if isinstance(r, dict) and r.get("name") == rig_name
                and r.get("rigId") not in self._preexisting_rig_ids
            ]
            if len(matches) == 1 and isinstance(matches[0], str) and matches[0]:
                self._track(matches[0])
                return
        self._log("error", "Could not confirm whether OpenRig rig %s was created", rig_name)

    def _wait_until_ready(self, rig_name, rig_id, session, deadline, expected_generation=None):
        while True:
            self._check_cancelled(f"while seat {session} was starting")
            node = self._node(rig_name, rig_id, session, deadline)
            if node is _POLL_TIMED_OUT:
                self._pause(deadline, f"OpenRig seat {session} did not become ready")
                continue
            if node is None:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SESSION_LOST", f"OpenRig seat {session} disappeared during startup"
                )
            startup = node.get("startupStatus")
            activity = node.get("agentActivity") or {}
            if startup in ("attention_required", "failed"):
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SEAT_NOT_READY",
                    f"OpenRig seat {session} startup {startup}: {node.get('latestError') or 'no detail'}",
                )
            if activity.get("state") == "needs_input":
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SEAT_NOT_READY",
                    f"OpenRig seat {session} needs input during startup ({activity.get('reason')})",
                )
            if (
                startup == "ready"
                and _hook_event(activity, "Stop", "idle")
                and (expected_generation is None or activity.get("generation") == expected_generation)
            ):
                return node
            self._pause(deadline, f"OpenRig seat {session} did not become ready")

    def _send(self, session, text, deadline):
        self._check_cancelled(f"before the prompt was sent to seat {session}")
        idle_wait = max(1, min(SEND_IDLE_WAIT_SECONDS, int(self._remaining(deadline))))
        args = ["send", "--wait-for-idle", str(idle_wait), "--json", "--", session, text]
        if self._popen is not None and self._cancel_event is not None:
            payload = self._run_json_interruptible(args, deadline, "FAILED_OPENRIG_DELIVERY")
        else:
            payload = self._run_json(args, deadline, "FAILED_OPENRIG_DELIVERY", allow_failure_payload=True)
        if not isinstance(payload, dict) or payload.get("ok") is not True or payload.get("sent") is not True:
            raise SprintRunnerError(
                "FAILED_OPENRIG_DELIVERY", f"rig send was not delivered: {_brief(payload)}"
            )

    def _wait_for_completion(
        self, rig_name, rig_id, session, send_started, send_confirmed, generation, deadline,
    ):
        """Return True if the turn start was observed.

        A Stop proves completion only if it follows evidence of our turn: either a
        UserPromptSubmit after the send began, or (start missed) the confirmed send itself.
        """
        prompt_at = None
        while True:
            self._check_cancelled(f"while seat {session} was working")
            node = self._node(rig_name, rig_id, session, deadline)
            if node is _POLL_TIMED_OUT:
                self._pause(deadline, f"OpenRig seat {session} did not finish the task")
                continue
            if node is None or node.get("sessionStatus") != "running":
                raise SprintRunnerError(
                    "FAILED_OPENRIG_SESSION_LOST", f"OpenRig seat {session} is no longer running"
                )
            activity = node.get("agentActivity") or {}
            if activity.get("state") == "needs_input":
                raise SprintRunnerError(
                    "FAILED_OPENRIG_NEEDS_INPUT",
                    f"OpenRig seat {session} is blocked on input ({activity.get('reason')})",
                )
            if _is_hook(activity):
                if activity.get("generation") != generation:
                    raise SprintRunnerError(
                        "FAILED_OPENRIG_SESSION_LOST",
                        f"OpenRig seat {session} changed occupant generation mid-task",
                    )
                event_at = _parse_time(activity.get("eventAt"))
                if event_at is not None:
                    if _hook_event(activity, "UserPromptSubmit", "running") and event_at > send_started:
                        prompt_at = event_at
                    elif _hook_event(activity, "Stop", "idle") and event_at > (prompt_at or send_confirmed):
                        # A cancel that arrived during this poll still wins over completion.
                        self._check_cancelled(f"as seat {session} finished")
                        return prompt_at is not None
            self._pause(deadline, f"OpenRig seat {session} did not finish the task")

    def _read_result(self, result_file):
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL",
                "OpenRig turn finished without writing the Hermes result file",
            ) from exc
        except (OSError, ValueError) as exc:  # JSONDecodeError, UnicodeDecodeError
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", "Hermes result file is not valid JSON"
            ) from exc
        if (
            not isinstance(data, dict)
            or data.get("status") not in ("succeeded", "failed")
            or not isinstance(data.get("summary"), str)
        ):
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL",
                "Hermes result file must be {status: succeeded|failed, summary: str}",
            )
        return data

    def _save_transcript(self, session, transcript_file, deadline):
        try:
            payload = self._run_json(
                ["transcript", session, "--json", "--tail", "200"], deadline,
                "FAILED_OPENRIG_UNAVAILABLE",
            )
            content = payload.get("content") if isinstance(payload, dict) else None
            if isinstance(content, str):
                transcript_file.write_text(content, encoding="utf-8")
        except SprintRunnerError as exc:
            # Diagnostics only; the result is already proven.
            self._log("warning", "OpenRig transcript capture failed: %s", exc.message)

    def _release(self, rig_id, deadline=None, *, emitter=None, label=None):
        """Tear one rig down by id and report it through `emitter` (its seat or execution)."""
        emitter = emitter or self._rig_emitter(rig_id)
        resource = events.resource("seat", rig_id, label or rig_id)
        try:
            self._teardown(rig_id, deadline)
        except SprintRunnerError as exc:
            emitter.event(
                events.RELEASE_FAILED, f"OpenRig rig {rig_id} could not be released; kept for retry",
                resource=resource, rig_id=rig_id, error_code=exc.code, error=exc.message,
            )
            raise
        emitter.event(
            events.RESOURCE_RELEASED, f"OpenRig rig {rig_id} released",
            resource=resource, rig_id=rig_id,
        )

    def _rig_emitter(self, rig_id):
        """Rigs that no task holds (ledger reconcile, cleanup retries) get their own event stream."""
        return ExecutionTrace(self.name, self.event_sink, self.sprint_id, execution_id=f"release:{rig_id}")

    def _teardown(self, rig_id, deadline=None):
        if not is_rig_id(rig_id):
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", f"refusing to tear down {rig_id!r}: not an OpenRig rigId"
            )
        if deadline is None:
            deadline = self._monotonic() + RELEASE_TIMEOUT_SECONDS
        remaining = self._remaining(deadline)
        if remaining <= 0:
            raise SprintRunnerError("FAILED_TIMEOUT", f"no time left to release OpenRig rig {rig_id}")
        # Not `rig down`: the CLI falls back to a rig *name* match when no rig has the id,
        # which could tear down someone else's rig. The daemon's /api/down is id-only.
        payload = self._daemon_down(rig_id, remaining)
        already_gone = (
            isinstance(payload, dict)
            and isinstance(payload.get("error"), dict)
            and "No rig found" in str(payload["error"].get("fact", ""))
        )
        if not already_gone and (
            not isinstance(payload, dict)
            or payload.get("rigId") != rig_id
            or payload.get("errors")
        ):
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE", f"rig down {rig_id} failed: {_brief(payload)}"
            )
        self.released_rig_ids.append(rig_id)
        self._forget(rig_id)
        self._log("info", "OpenRig rig %s released", rig_id)

    def _forget(self, rig_id):
        try:
            self.ledger.forget(rig_id)
        except OSError as exc:
            # The rig is already down. A stale entry is harmless: the next reconcile gets
            # "No rig found" from rig down, which counts as released, and drops it.
            self._log("warning", "OpenRig ledger could not drop released rig %s: %s", rig_id, exc)

    def _release_quietly(self, rig_id, emitter=None, label=None):
        try:
            self._release(rig_id, emitter=emitter, label=label)
        except SprintRunnerError as exc:
            # Left in owned_rig_ids for cleanup() to retry.
            self._log("error", "OpenRig release of %s failed: %s", rig_id, exc.message)

    # -- helpers --------------------------------------------------------------

    def _node(self, rig_name, rig_id, session, deadline):
        poll_deadline = min(deadline, self._monotonic() + POLL_QUERY_SECONDS)
        try:
            nodes = self._run_json(
                ["ps", "--nodes", "--json", "--full", "--rig", rig_name], poll_deadline,
                "FAILED_OPENRIG_UNAVAILABLE",
            )
        except SprintRunnerError as exc:
            # Only the poll's own bound expired: go back to the loop, which checks cancel.
            if exc.code == "FAILED_TIMEOUT" and self._remaining(deadline) > 0:
                return _POLL_TIMED_OUT
            raise
        if not isinstance(nodes, list):
            raise SprintRunnerError("FAILED_OPENRIG_PROTOCOL", "rig ps --nodes did not return a list")
        for node in nodes:
            if not isinstance(node, dict) or node.get("canonicalSessionName") != session:
                continue
            if node.get("rigId") != rig_id:
                raise SprintRunnerError(
                    "FAILED_OPENRIG_PROTOCOL",
                    f"Session {session} belongs to rig {node.get('rigId')}, not owned rig {rig_id}",
                )
            return node
        return None

    def _task_text(self, prompt, worktree, result_file):
        return (
            f"{prompt}\n\n"
            "--- Hermes result protocol ---\n"
            f"Work only inside {Path(worktree).resolve()}. When you are completely finished, "
            f"use the Write tool to create {result_file.resolve()} containing a JSON object "
            '{"status": "succeeded" or "failed", "summary": "<one sentence>"}. '
            "Write that file last, exactly once."
        )

    def _rig_name(self):
        slug = re.sub(r"[^a-z0-9-]+", "-", self.sprint_id.lower()).strip("-")[:24] or "task"
        return f"hermes-{slug}-{secrets.token_hex(4)}"

    def _check_cancelled(self, where):
        # Only the wait steps and the send check this. Once _wait_for_completion has
        # returned, the result is proven and a late cancel is a no-op.
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise SprintRunnerError(
                "FAILED_OPENRIG_CANCELLED", f"OpenRig task cancelled {where}"
            )

    def _remaining(self, deadline):
        return deadline - self._monotonic()

    def _pause(self, deadline, what):
        remaining = self._remaining(deadline)
        if remaining <= 0:
            raise SprintRunnerError("FAILED_TIMEOUT", f"{what} before the task timeout")
        self._sleep(min(self.poll_interval, remaining))

    def _run_json_interruptible(self, args, deadline, failure_code):
        """Like _run_json for a call that may block: polls the cancel event and kills the child on cancel.

        Killing `rig send` is safe: a cancelled task's rig is torn down by id right after.
        """
        if self._remaining(deadline) <= 0:
            raise SprintRunnerError("FAILED_TIMEOUT", f"OpenRig task timed out before rig {args[0]}")
        self._check_cancelled(f"before rig {args[0]}")
        try:
            proc = self._popen(
                [self.rig_executable, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
        except FileNotFoundError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_EXECUTABLE_MISSING", f"OpenRig executable was not found: {self.rig_executable}",
            ) from exc
        except OSError as exc:
            raise SprintRunnerError("FAILED_OPENRIG_UNAVAILABLE", f"Could not run rig {args[0]}: {exc}") from exc
        while True:
            remaining = self._remaining(deadline)
            if remaining <= 0:
                proc.kill()
                proc.communicate()
                raise SprintRunnerError("FAILED_TIMEOUT", f"OpenRig command rig {args[0]} exceeded the task timeout")
            try:
                stdout, _ = proc.communicate(timeout=min(CANCEL_POLL_SECONDS, remaining))
                break
            except subprocess.TimeoutExpired:
                if self._cancel_event.is_set():
                    proc.kill()
                    proc.communicate()
                    raise SprintRunnerError("FAILED_OPENRIG_CANCELLED", f"OpenRig task cancelled during rig {args[0]}")
        try:
            return json.loads(stdout or "")
        except json.JSONDecodeError as exc:
            raise SprintRunnerError("FAILED_OPENRIG_PROTOCOL", f"rig {args[0]} returned malformed JSON") from exc

    def _run(self, args, deadline, failure_code, allow_failure_payload=False):
        remaining = self._remaining(deadline)
        if remaining <= 0:
            raise SprintRunnerError("FAILED_TIMEOUT", f"OpenRig task timed out before rig {args[0]}")
        try:
            result = self._run_process(
                [self.rig_executable, *args],
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except FileNotFoundError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_EXECUTABLE_MISSING",
                f"OpenRig executable was not found: {self.rig_executable}",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SprintRunnerError(
                "FAILED_TIMEOUT", f"OpenRig command rig {args[0]} exceeded the task timeout"
            ) from exc
        except OSError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_UNAVAILABLE", f"Could not run rig {args[0]}: {exc}"
            ) from exc
        if result.returncode != 0 and not allow_failure_payload:
            detail = (result.stderr or result.stdout or "unknown error").strip()[:500]
            raise SprintRunnerError(failure_code, f"rig {args[0]} failed: {detail}")
        return result.stdout or ""

    def _run_json(self, args, deadline, failure_code, allow_failure_payload=False):
        text = self._run(args, deadline, failure_code, allow_failure_payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SprintRunnerError(
                "FAILED_OPENRIG_PROTOCOL", f"rig {args[0]} returned malformed JSON"
            ) from exc

    def _log(self, level, message, *args):
        if self.logger is not None:
            getattr(self.logger, level)(message, *args)


def _iso(moment):
    return moment.isoformat().replace("+00:00", "Z")


STATUS_QUERY_SECONDS = 3


def describe_openrig(rig_executable="rig", *, run_process=None, which=None, ledger=None):
    """Read-only OpenRig status for GET /execution: daemon reachability and the ownership ledger.

    Runs only `rig ps --json`. It never runs a mutating command and never reconciles the ledger.
    Returns None when the rig executable is not installed.
    """
    if (which or shutil.which)(rig_executable) is None:
        return None
    run = run_process or subprocess.run
    daemon = "unknown"
    try:
        result = run([rig_executable, "ps", "--json"], capture_output=True, text=True, timeout=STATUS_QUERY_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is not None and result.returncode != 0:
        daemon = "down"
    elif result is not None:
        try:
            daemon = "up" if isinstance(json.loads(result.stdout or ""), list) else "unknown"
        except ValueError:
            daemon = "unknown"
    return {"daemon": daemon, "ledger": (ledger or OwnershipLedger()).summary()}


def _is_hook(activity):
    return (
        activity.get("evidenceSource") == "runtime_hook"
        and activity.get("stale") is False
        and activity.get("fallback") is False
    )


def _hook_event(activity, raw_event, state):
    return _is_hook(activity) and activity.get("rawEvent") == raw_event and activity.get("state") == state


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _brief(payload):
    return json.dumps(payload)[:300] if payload is not None else "no payload"


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
