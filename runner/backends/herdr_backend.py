import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from agents.errors import SprintRunnerError

from . import events
from .base import ExecutionBackend, ExecutionResult


class Seat:
    """An exclusive seat pane within a Herdr workspace."""

    def __init__(self, label: str, is_hot: bool = False, pane_id: Optional[str] = None):
        self.label = label
        self.is_hot = is_hot
        self.pane_id = pane_id
        self.busy = False
        self.leased_by = None

    def __repr__(self):
        return f"Seat(label={self.label!r}, is_hot={self.is_hot!r}, pane_id={self.pane_id!r}, busy={self.busy!r})"


_SEAT_POOLS: Dict[Tuple[str, str], "SeatPool"] = {}
_SEAT_POOLS_LOCK = threading.Lock()


class SeatPool:
    """Fixed, named seat pool hosted in a single Herdr workspace."""

    def __init__(
        self,
        run_dir: Union[str, Path],
        sprint_id: str,
        size: int = 5,
        hot: bool = True,
        acquire_timeout_seconds: float = 600.0,
    ):
        self.run_dir = Path(run_dir)
        self.sprint_id = sprint_id
        self.size = max(1, int(size))
        self.hot = bool(hot)
        self.acquire_timeout_seconds = float(acquire_timeout_seconds)
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self.seats: Dict[str, Seat] = {}

        for i in range(1, self.size + 1):
            label = f"seat-{i}"
            self.seats[label] = Seat(label=label, is_hot=False)
        if self.hot:
            self.seats["hot"] = Seat(label="hot", is_hot=True)

        self._load_from_runtime()

    @classmethod
    def get_or_create(
        cls,
        run_dir: Union[str, Path],
        sprint_id: str,
        size: int = 5,
        hot: bool = True,
        acquire_timeout_seconds: float = 600.0,
    ) -> "SeatPool":
        key = (str(Path(run_dir).resolve()), str(sprint_id))
        with _SEAT_POOLS_LOCK:
            if key not in _SEAT_POOLS:
                _SEAT_POOLS[key] = cls(
                    run_dir=run_dir,
                    sprint_id=sprint_id,
                    size=size,
                    hot=hot,
                    acquire_timeout_seconds=acquire_timeout_seconds,
                )
            return _SEAT_POOLS[key]

    @classmethod
    def clear_pool(cls, run_dir: Union[str, Path], sprint_id: str) -> None:
        key = (str(Path(run_dir).resolve()), str(sprint_id))
        with _SEAT_POOLS_LOCK:
            _SEAT_POOLS.pop(key, None)

    @classmethod
    def reset(cls) -> None:
        with _SEAT_POOLS_LOCK:
            _SEAT_POOLS.clear()

    def _load_from_runtime(self) -> None:
        runtime_file = self.run_dir / "herdr" / "runtime.json"
        if runtime_file.exists():
            try:
                data = json.loads(runtime_file.read_text(encoding="utf-8"))
                seat_panes = data.get("seat_panes", {})
                for label, pane_id in seat_panes.items():
                    if label in self.seats:
                        self.seats[label].pane_id = pane_id
            except Exception:
                pass

    def ensure_workspace(self, cwd: Path, backend: "HerdrBackend") -> str:
        backend._ensure_workspace(cwd)
        return backend.workspace_id

    def ensure_seat_pane(
        self, seat_or_label: Union[Seat, str], cwd: Path, backend: "HerdrBackend"
    ) -> str:
        if isinstance(seat_or_label, str):
            seat = self.seats.get(seat_or_label)
            if seat is None:
                is_hot = seat_or_label == "hot"
                seat = Seat(label=seat_or_label, is_hot=is_hot)
                self.seats[seat_or_label] = seat
        else:
            seat = seat_or_label

        if seat.pane_id is not None:
            return seat.pane_id

        self.ensure_workspace(cwd, backend)
        response = backend._run_json(
            [
                "pane",
                "split",
                backend.root_pane_id,
                "--direction",
                "down",
                "--cwd",
                str(cwd),
                "--no-focus",
            ],
            failure_code="FAILED_HERDR_COMMAND",
        )
        pane_id = backend._extract_id(
            response, ("result", "pane", "pane_id"), "worker pane"
        )
        if pane_id not in backend.created_pane_ids:
            backend.created_pane_ids.append(pane_id)
        backend._run_json(
            ["pane", "rename", pane_id, seat.label],
            failure_code="FAILED_HERDR_COMMAND",
        )
        backend._record_operation(
            "seat_pane_create", pane_id=pane_id, seat=seat.label
        )
        seat.pane_id = pane_id
        backend._write_runtime()
        return pane_id

    def acquire(
        self,
        is_hot: bool = False,
        timeout: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
        cwd: Optional[Path] = None,
        backend: Optional["HerdrBackend"] = None,
    ) -> Seat:
        timeout = self.acquire_timeout_seconds if timeout is None else float(timeout)
        deadline = time.monotonic() + timeout

        with self._cond:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise SprintRunnerError(
                        "FAILED_CANCELLED",
                        "Herdr execution cancelled while waiting for a seat",
                    )

                candidate: Optional[Seat] = None
                if is_hot:
                    hot_seat = self.seats.get("hot")
                    if hot_seat and not hot_seat.busy:
                        candidate = hot_seat
                else:
                    for i in range(1, self.size + 1):
                        label = f"seat-{i}"
                        seat = self.seats.get(label)
                        if seat and not seat.busy:
                            candidate = seat
                            break

                if candidate is not None:
                    candidate.busy = True
                    if candidate.pane_id is None and backend is not None:
                        try:
                            self.ensure_seat_pane(
                                candidate, cwd or backend.run_dir, backend
                            )
                        except BaseException:
                            candidate.busy = False
                            self._cond.notify_all()
                            raise
                    return candidate

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SprintRunnerError(
                        "FAILED_SEAT_TIMEOUT",
                        f"Timed out waiting for a free Herdr seat after {timeout} seconds",
                    )

                self._cond.wait(min(remaining, 0.1))

    def release(self, seat: Union[Seat, str]) -> None:
        with self._cond:
            if isinstance(seat, str):
                target = self.seats.get(seat)
            else:
                target = seat
            if target:
                target.busy = False
                target.leased_by = None
            self._cond.notify_all()

    @contextmanager
    def lease(
        self,
        is_hot: bool = False,
        timeout: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
        cwd: Optional[Path] = None,
        backend: Optional["HerdrBackend"] = None,
    ):
        seat = self.acquire(
            is_hot=is_hot,
            timeout=timeout,
            cancel_event=cancel_event,
            cwd=cwd,
            backend=backend,
        )
        try:
            yield seat
        finally:
            self.release(seat)


class HerdrBackend(ExecutionBackend):
    """Host one-shot worker CLIs in runner-owned persistent Herdr panes."""

    name = "herdr"

    def __init__(
        self,
        run_dir,
        sprint_id,
        logger=None,
        keep_workspace=True,
        run_process=None,
        which_func=None,
        herdr_executable="herdr",
        event_sink=None,
        seat_pool=None,
        backend_settings=None,
        **kwargs,
    ):
        self.run_dir = Path(run_dir)
        self.sprint_id = sprint_id
        self.logger = logger
        self.keep_workspace = keep_workspace
        self._run_process = run_process or subprocess.run
        self._which = which_func or shutil.which
        self.herdr_executable = herdr_executable
        self.workspace_id = None
        self.root_pane_id = None
        self.created_pane_ids = []
        self.herdr_dir = self.run_dir / "herdr"
        self.wrapper_dir = self.run_dir / "wrappers"
        self.commands_log = self.herdr_dir / "commands.log"
        self.runtime_file = self.herdr_dir / "runtime.json"
        self.event_sink = event_sink
        self.cancel_event = kwargs.get("cancel_event") or threading.Event()
        self._workspace_lock = threading.Lock()

        # Seat pool resolution
        pool_cfg = seat_pool if seat_pool is not None else kwargs.get("seat_pool")
        if pool_cfg is None:
            bs = backend_settings if backend_settings is not None else kwargs.get("backend_settings")
            if isinstance(bs, dict):
                pool_cfg = bs.get("seat_pool")

        if pool_cfg:
            if isinstance(pool_cfg, SeatPool):
                self.seat_pool = pool_cfg
            else:
                cfg = pool_cfg if isinstance(pool_cfg, dict) else {}
                size = cfg.get("size", 5)
                hot = cfg.get("hot", True)
                timeout = cfg.get("acquire_timeout_seconds", 600)
                self.seat_pool = SeatPool.get_or_create(
                    run_dir=self.run_dir,
                    sprint_id=self.sprint_id,
                    size=size,
                    hot=hot,
                    acquire_timeout_seconds=timeout,
                )
        else:
            self.seat_pool = None

        self._load_runtime()

    def execute(self, request):
        trace = self.trace(self.sprint_id, cancel_codes=("FAILED_CANCELLED",))
        trace.started(f"Herdr task for agent '{request.agent_name}' started")
        try:
            return self._execute(request, trace)
        except BaseException as exc:
            trace.fail(exc)
            raise


    def _execute(self, request, trace):
        if self.cancel_event.is_set():
            raise SprintRunnerError("FAILED_CANCELLED", "Herdr execution cancelled before launch")
        self.preflight(request.command[0])
        self._ensure_workspace(request.cwd)

        seat = None
        if self.seat_pool:
            is_hot = request.metadata.get("priority") == "hot"
            seat = self.seat_pool.acquire(
                is_hot=is_hot,
                timeout=self.seat_pool.acquire_timeout_seconds,
                cancel_event=self.cancel_event,
                cwd=request.cwd,
                backend=self,
            )
            pane_id = seat.pane_id
            trace.bind(resource=events.resource("seat", seat.label, seat.label))
            trace.event(events.RESOURCE_ACQUIRED, f"Seat {seat.label} acquired (pane {pane_id})")
        else:
            pane_id = self._create_worker_pane(request)
            label = str(request.metadata.get("phase", request.agent_name))[:80]
            trace.bind(resource=events.resource("pane", pane_id, label))
            trace.event(events.RESOURCE_ACQUIRED, f"Worker pane {pane_id} created")

        from .execution_registry import default_execution_registry

        def interrupt():
            try:
                self._interrupt_pane(pane_id)
            except Exception:
                if self.logger:
                    self.logger.warning("Could not interrupt pane %s", pane_id, exc_info=True)

        stopped = threading.Event()

        def watch_cancel():
            while not stopped.wait(0.1):
                if self.cancel_event.is_set():
                    interrupt()
                    return

        watcher = threading.Thread(target=watch_cancel, daemon=True)
        default_execution_registry.register_execution(
            trace.execution_id, self.sprint_id, pane_id, self.cancel_event.set
        )
        watcher.start()
        try:
            if seat is not None:
                result = self._run_in_pane(request, trace, pane_id, seat=seat)
            else:
                result = self._run_in_pane(request, trace, pane_id)
            if self.cancel_event.is_set():
                raise SprintRunnerError("FAILED_CANCELLED", "Herdr execution cancelled")
            return result
        except BaseException as exc:
            if self.cancel_event.is_set():
                cancelled = SprintRunnerError("FAILED_CANCELLED", "Herdr execution cancelled")
                trace.fail(cancelled)
                raise cancelled from exc
            trace.fail(exc)
            raise
        finally:
            stopped.set()
            watcher.join(timeout=0.2)
            default_execution_registry.unregister_execution(trace.execution_id)
            if self.cancel_event.is_set():
                interrupt()
            if self.seat_pool and seat is not None:
                trace.event(events.RESOURCE_RELEASED, f"Seat {seat.label} released")
                self.seat_pool.release(seat)
            else:
                trace.event(events.RESOURCE_RELEASED, f"Worker pane {pane_id} finished its command")

    def _run_in_pane(self, request, trace, pane_id, seat=None):
        trace.event(events.RESOURCE_READY, "Pane created and ready for the command")
        if seat is not None:
            wrapper_path, nonce, exit_file = self.build_wrapper(request, seat=seat)
        else:
            wrapper_path, nonce, exit_file = self.build_wrapper(request)
        marker_regex = self.completion_regex(nonce)

        try:
            self._run_json(
                ["pane", "run", pane_id, f"bash {shlex.quote(str(wrapper_path))}"],
                failure_code="FAILED_HERDR_COMMAND",
                allow_empty_output=True,
            )
            trace.event(events.RUNNING, "Worker command running in the pane")
            try:
                self._run_json(
                    [
                        "pane",
                        "wait-output",
                        pane_id,
                        "--regex",
                        marker_regex,
                        "--source",
                        "recent-unwrapped",
                        "--lines",
                        "2000",
                        "--timeout",
                        str(request.timeout_seconds * 1000),
                    ],
                    failure_code="FAILED_HERDR_COMMAND",
                    process_timeout=request.timeout_seconds + 5,
                )
            except SprintRunnerError as exc:
                if exc.code == "FAILED_TIMEOUT" or "timeout" in exc.message.lower():
                    self._interrupt_pane(pane_id)
                    raise SprintRunnerError(
                        "FAILED_TIMEOUT",
                        f"Agent {request.agent_name} timed out after "
                        f"{request.timeout_seconds} seconds in Herdr pane {pane_id}",
                    ) from exc
                raise

            if not exit_file.exists():
                raise SprintRunnerError(
                    "FAILED_HERDR_PROTOCOL",
                    f"Herdr completion marker appeared without an exit status for pane {pane_id}",
                )
            try:
                returncode = int(exit_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError) as exc:
                raise SprintRunnerError(
                    "FAILED_HERDR_PROTOCOL",
                    f"Invalid worker exit status for Herdr pane {pane_id}",
                ) from exc
        finally:
            try:
                wrapper_path.unlink(missing_ok=True)
            except OSError:
                pass

        stdout = _read_text(request.stdout_file)
        stderr = _read_text(request.stderr_file)
        runtime_metadata = {
            "herdr_workspace_id": self.workspace_id,
            "herdr_pane_id": pane_id,
        }
        if seat is not None:
            runtime_metadata["herdr_seat"] = seat.label
        self._record_operation("worker_complete", pane_id=pane_id, status=returncode)
        if self.cancel_event.is_set():
            raise SprintRunnerError("FAILED_CANCELLED", "Herdr execution cancelled")
        trace.finish(f"Worker exited with code {returncode}")
        return ExecutionResult(
            command=tuple(request.command),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            backend=self.name,
            runtime_metadata=runtime_metadata,
        )

    def preflight(self, worker_executable):
        if self._which(self.herdr_executable) is None:
            raise SprintRunnerError(
                "FAILED_HERDR_EXECUTABLE_MISSING",
                f"Herdr executable was not found: {self.herdr_executable}",
            )
        if not _executable_exists(worker_executable, self._which):
            raise SprintRunnerError(
                "FAILED_AGENT_EXECUTABLE_MISSING",
                f"Worker executable was not found: {worker_executable}",
            )
        self._run_json(
            ["api", "snapshot"], failure_code="FAILED_HERDR_UNAVAILABLE"
        )

    def _load_runtime(self):
        if not self.runtime_file.exists():
            return
        try:
            data = json.loads(self.runtime_file.read_text(encoding="utf-8"))
            if self.workspace_id is None and data.get("workspace_id"):
                self.workspace_id = data["workspace_id"]
            if self.root_pane_id is None and data.get("root_pane_id"):
                self.root_pane_id = data["root_pane_id"]
            for pid in data.get("worker_pane_ids", []):
                if pid not in self.created_pane_ids:
                    self.created_pane_ids.append(pid)
            if self.seat_pool:
                seat_panes = data.get("seat_panes", {})
                for label, pid in seat_panes.items():
                    if label in self.seat_pool.seats:
                        self.seat_pool.seats[label].pane_id = pid
        except Exception:
            pass

    def _ensure_workspace(self, cwd):
        with self._workspace_lock:
            if self.workspace_id is not None:
                return
            self._load_runtime()
            if self.workspace_id is not None:
                return
            response = self._run_json(
                [
                    "workspace",
                    "create",
                    "--cwd",
                    str(cwd),
                    "--label",
                    f"Hermes Lab — {self.sprint_id}",
                    "--no-focus",
                ],
                failure_code="FAILED_HERDR_COMMAND",
            )
            self.workspace_id = self._extract_id(
                response, ("result", "workspace", "workspace_id"), "workspace"
            )
            self.root_pane_id = self._extract_id(
                response, ("result", "root_pane", "pane_id"), "root pane"
            )
            self._record_operation("workspace_create", pane_id=self.root_pane_id)
            self._write_runtime()


    def _create_worker_pane(self, request):
        response = self._run_json(
            [
                "pane",
                "split",
                self.root_pane_id,
                "--direction",
                "down",
                "--cwd",
                str(request.cwd),
                "--no-focus",
            ],
            failure_code="FAILED_HERDR_COMMAND",
        )
        pane_id = self._extract_id(
            response, ("result", "pane", "pane_id"), "worker pane"
        )
        self.created_pane_ids.append(pane_id)
        label = str(request.metadata.get("phase", request.agent_name))[:80]
        self._run_json(
            ["pane", "rename", pane_id, label],
            failure_code="FAILED_HERDR_COMMAND",
        )
        self._record_operation("pane_create", pane_id=pane_id)
        self._write_runtime()
        return pane_id

    def build_wrapper(self, request, seat=None):
        self.wrapper_dir.mkdir(parents=True, exist_ok=True)
        request.stdout_file.parent.mkdir(parents=True, exist_ok=True)
        nonce = secrets.token_hex(16)
        phase = _safe_name(str(request.metadata.get("phase", request.agent_name)))
        wrapper_path = self.wrapper_dir / f"{phase}_{nonce}.sh"
        exit_file = self.herdr_dir / f"{phase}_{nonce}.exit"
        self.herdr_dir.mkdir(parents=True, exist_ok=True)
        quoted_argv = "\n".join(f"  {shlex.quote(str(arg))}" for arg in request.command)
        marker = self.completion_marker(nonce)

        banner_cmds = ""
        if seat is not None:
            phase_name = request.metadata.get("phase", request.agent_name)
            persona_name = (
                request.metadata.get("persona")
                or request.metadata.get("persona_name")
                or request.agent_name
            )
            banner = f"=== [seat:{seat.label}] job:{self.sprint_id} phase:{phase_name} agent:{persona_name} ==="
            banner_cmds = f"printf '%s\\n' {shlex.quote(banner)}\n"
            self._record_operation("seat_banner", seat=seat.label, banner=banner)

        script = f"""#!/usr/bin/env bash
set +e
{banner_cmds}command=(
{quoted_argv}
)
: > {shlex.quote(str(request.stdout_file))}
: > {shlex.quote(str(request.stderr_file))}
"${{command[@]}}" > >(tee -a {shlex.quote(str(request.stdout_file))}) 2> >(tee -a {shlex.quote(str(request.stderr_file))} >&2)
status=$?
wait
printf '%s' "$status" > {shlex.quote(str(exit_file))}
printf '\\n%s:%s\\n' {shlex.quote(marker)} "$status"
exit 0
"""
        wrapper_path.write_text(script, encoding="utf-8")
        wrapper_path.chmod(0o700)
        return wrapper_path, nonce, exit_file

    @staticmethod
    def completion_marker(nonce):
        return f"__HERMES_LAB_COMPLETE_{nonce}__"

    @classmethod
    def completion_regex(cls, nonce):
        return rf"(?m)^{re.escape(cls.completion_marker(nonce))}:[0-9]+$"

    @classmethod
    def parse_completion(cls, text, nonce):
        pattern = re.compile(cls.completion_regex(nonce))
        match = pattern.search(text)
        if match is None:
            return None
        return int(match.group(0).rsplit(":", 1)[1])

    @staticmethod
    def _extract_id(payload, path, label):
        value = payload
        try:
            for key in path:
                value = value[key]
        except (KeyError, TypeError) as exc:
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL", f"Herdr response omitted {label} ID"
            ) from exc
        if not isinstance(value, str) or not value:
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL", f"Herdr returned an invalid {label} ID"
            )
        return value

    def _run_json(
        self, args, failure_code, process_timeout=30, allow_empty_output=False
    ):
        command = [self.herdr_executable, *args]
        self._record_operation("herdr_call", target=args[0] if args else None)
        try:
            result = self._run_process(
                command,
                capture_output=True,
                text=True,
                timeout=process_timeout,
            )
        except FileNotFoundError as exc:
            raise SprintRunnerError(
                "FAILED_HERDR_EXECUTABLE_MISSING",
                f"Herdr executable was not found: {self.herdr_executable}",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SprintRunnerError(
                "FAILED_TIMEOUT", f"Herdr command timed out: {args[0]}"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown Herdr error").strip()
            raise SprintRunnerError(failure_code, f"Herdr command failed: {detail}")
        if allow_empty_output and not result.stdout.strip():
            return {}
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL",
                f"Herdr returned malformed JSON for {args[0]}",
            ) from exc
        if not isinstance(payload, dict):
            raise SprintRunnerError(
                "FAILED_HERDR_PROTOCOL", "Herdr JSON response was not an object"
            )
        return payload

    def _interrupt_pane(self, pane_id):
        try:
            self._run_json(
                ["pane", "send-keys", pane_id, "ctrl+c"],
                failure_code="FAILED_HERDR_COMMAND",
            )
        except SprintRunnerError:
            pass
        self._record_operation("pane_interrupt", pane_id=pane_id)

    def cleanup(self, success=False):
        if self.keep_workspace or self.workspace_id is None:
            return
        owned_workspace = self.workspace_id
        self._run_json(
            ["workspace", "close", owned_workspace],
            failure_code="FAILED_HERDR_COMMAND",
        )
        self._record_operation("workspace_close", workspace_id=owned_workspace)
        self.workspace_id = None
        self.root_pane_id = None
        self.created_pane_ids.clear()
        if self.seat_pool:
            for seat in self.seat_pool.seats.values():
                seat.pane_id = None
                seat.busy = False
            SeatPool.clear_pool(self.run_dir, self.sprint_id)
        self._write_runtime()

    def release_job(self, job):
        SeatPool.clear_pool(self.run_dir, self.sprint_id)

    def _record_operation(self, operation, **details):
        self.herdr_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            **details,
        }
        with self.commands_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_runtime(self):
        self.herdr_dir.mkdir(parents=True, exist_ok=True)
        seat_panes = {}
        if self.runtime_file.exists():
            try:
                data = json.loads(self.runtime_file.read_text(encoding="utf-8"))
                seat_panes = data.get("seat_panes", {})
            except Exception:
                pass
        if self.seat_pool:
            for seat in self.seat_pool.seats.values():
                if seat.pane_id is not None:
                    seat_panes[seat.label] = seat.pane_id
        payload = {
            "workspace_id": self.workspace_id,
            "root_pane_id": self.root_pane_id,
            "worker_pane_ids": list(self.created_pane_ids),
            "seat_panes": seat_panes,
            "keep_workspace": self.keep_workspace,
        }
        self.runtime_file.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )



def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _executable_exists(executable, which_func):
    if os.sep in str(executable):
        return os.access(executable, os.X_OK)
    return which_func(executable) is not None


def _safe_name(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")
    return cleaned or "worker"
