import atexit
import json
import re
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agents.errors import SprintRunnerError

from .base import ExecutionBackend, ExecutionResult
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

    @property
    def seat_dir(self):
        return self.rig_dir / "seat"


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
        with self._lock:
            self._idle.setdefault(seat.job, []).append(seat)
            self._timers[seat.rig_id] = (timer, token)
        try:
            timer.start()
        except BaseException:
            # Without an expiry timer the seat must not stay leasable; the caller
            # still owns it and tears it down.
            with self._lock:
                if self._timers.get(seat.rig_id, (None, None))[1] is token:
                    del self._timers[seat.rig_id]
                group = self._idle.get(seat.job, [])
                if seat in group:
                    group.remove(seat)
            raise

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

    def failed_rig_ids(self):
        with self._lock:
            return list(self._failed)

    def inflight_rig_ids(self):
        with self._lock:
            return list(self._inflight)


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

    def __init__(
        self,
        run_dir,
        sprint_id,
        logger=None,
        run_process=None,
        which_func=None,
        rig_executable="rig",
        poll_interval=2.0,
        monotonic=None,
        sleep=None,
        utcnow=None,
        seat_pool=None,
        ledger=None,
        cancel_event=None,
        **kwargs,
    ):
        self.run_dir = Path(run_dir)
        self.sprint_id = str(sprint_id)
        self.logger = logger
        self.rig_executable = rig_executable
        self.poll_interval = poll_interval
        self._run_process = run_process or subprocess.run
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
        # Set by the caller to stop this task out of band. Checked at step boundaries only.
        self._cancel_event = cancel_event
        self._preexisting_rig_ids = set()

    # -- contract -------------------------------------------------------------

    def execute(self, request):
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
                expected_generation = self._fresh_occupant(seat, deadline)
            else:
                seat = self._new_seat(runtime, request.cwd, deadline)
                expected_generation = None
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

            result_file = seat.seat_dir / f"hermes-result-{nonce}.json"
            send_started = self._utcnow()
            self._send(seat.session, self._task_text(prompt, request.cwd, result_file), deadline)
            send_confirmed = self._utcnow()
            started = self._wait_for_completion(
                seat.rig_name, seat.rig_id, seat.session,
                send_started, send_confirmed, generation, deadline,
            )
            metadata["openrig_turn_started"] = started

            outcome = self._read_result(result_file)
            self._save_transcript(seat.session, seat.rig_dir / f"transcript-{nonce}.txt", deadline)

            # Clean protocol completion: the seat is healthy enough to serve the job again.
            seat.generation = generation
            self.seat_pool.put(seat)
            self.pooled_rig_ids.append(seat.rig_id)
        finally:
            # Covers rigs recorded by _launch even when it raised afterwards.
            for owned in list(self.owned_rig_ids):
                if owned not in self.released_rig_ids and owned not in self.pooled_rig_ids:
                    self._release_quietly(owned)

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
        return self.seat_pool.release_job(job)

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
        return _Seat(
            job=self.sprint_id, rig_id=rig_id, rig_name=rig_name, session=session,
            rig_dir=rig_dir, granted_root=granted_root, release=self._release,
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
        try:
            payload = self._run_json(
                ["up", str(spec_path), "--json"], deadline, "FAILED_OPENRIG_CREATE",
                allow_failure_payload=True,
            )
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
        payload = self._run_json(
            ["send", "--wait-for-idle", str(idle_wait), "--json", "--", session, text],
            deadline, "FAILED_OPENRIG_DELIVERY", allow_failure_payload=True,
        )
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

    def _release(self, rig_id, deadline=None):
        if deadline is None:
            deadline = self._monotonic() + RELEASE_TIMEOUT_SECONDS
        payload = self._run_json(
            ["down", rig_id, "--delete", "--force", "--json"],
            deadline,
            "FAILED_OPENRIG_UNAVAILABLE",
            allow_failure_payload=True,
        )
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

    def _release_quietly(self, rig_id):
        try:
            self._release(rig_id)
        except SprintRunnerError as exc:
            # Left in owned_rig_ids for cleanup() to retry.
            self._log("error", "OpenRig release of %s failed: %s", rig_id, exc.message)

    # -- helpers --------------------------------------------------------------

    def _node(self, rig_name, rig_id, session, deadline):
        nodes = self._run_json(
            ["ps", "--nodes", "--json", "--full", "--rig", rig_name], deadline,
            "FAILED_OPENRIG_UNAVAILABLE",
        )
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
