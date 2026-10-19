import subprocess
import os
import signal
import threading
import time

from agents.errors import SprintRunnerError

from . import events
from .base import ExecutionBackend, ExecutionResult


class SubprocessBackend(ExecutionBackend):
    name = "subprocess"

    def __init__(self, run_process=None, sprint_id=None, event_sink=None, **kwargs):
        self._run_process = run_process
        self._local = threading.local()
        self.cancel_event = kwargs.get("cancel_event") or threading.Event()
        self.cancel_grace_seconds = float(kwargs.get("cancel_grace_seconds", os.environ.get("HERMES_CANCEL_GRACE_SECONDS", 5)))
        self.sprint_id = sprint_id
        self.event_sink = event_sink

    def _run_owned(self, command, cwd, capture_output, text, timeout):
        from .execution_registry import default_execution_registry
        if self.cancel_event.is_set():
            raise SprintRunnerError("FAILED_CANCELLED", "Execution cancelled before launch")
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=text, start_new_session=True)
        execution_id = self._local.trace.execution_id
        default_execution_registry.register_execution(
            execution_id, self.sprint_id, process, self.cancel_event.set)
        deadline = time.monotonic() + timeout
        try:
            while True:
                if self.cancel_event.is_set():
                    self._stop_group(process)
                    stdout, stderr = process.communicate()
                    self._local.request.stdout_file.write_text(stdout or "", encoding="utf-8")
                    self._local.request.stderr_file.write_text(stderr or "", encoding="utf-8")
                    raise SprintRunnerError("FAILED_CANCELLED", "Execution cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._stop_group(process, grace_seconds=0)
                    stdout, stderr = process.communicate()
                    raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
                try:
                    stdout, stderr = process.communicate(timeout=min(.1, remaining))
                    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if process.poll() is None:
                self._stop_group(process)
                process.communicate()
            default_execution_registry.unregister_execution(execution_id)

    def _stop_group(self, process, grace_seconds=None):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + (self.cancel_grace_seconds if grace_seconds is None else grace_seconds)
        while time.monotonic() < deadline:
            process.poll()  # reap the leader before checking whether the group remains
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.02)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def execute(self, request):
        trace = self.trace(self.sprint_id, cancel_codes=("FAILED_CANCELLED",))
        self._local.trace = trace
        self._local.request = request
        trace.started(f"Subprocess started for agent '{request.agent_name}'")
        try:
            return self._execute(request, trace)
        except BaseException as exc:
            trace.fail(exc)
            raise

    def _execute(self, request, trace):
        # Stable resource identity across launch and release; the registry owns the Popen handle.
        trace.bind(resource=events.resource("process", trace.execution_id, request.agent_name))
        trace.event(events.RESOURCE_ACQUIRED, f"Process slot for agent '{request.agent_name}'")
        try:
            trace.event(events.RESOURCE_READY, "Command argv is complete")
            trace.event(events.RUNNING, "Worker process running")
            try:
                process = (self._run_process or self._run_owned)(
                    list(request.command),
                    cwd=request.cwd,
                    capture_output=True,
                    text=True,
                    timeout=request.timeout_seconds,
                )
            except FileNotFoundError as exc:
                raise SprintRunnerError(
                    "FAILED_AGENT_EXECUTABLE_MISSING",
                    f"Executable for agent '{request.agent_name}' was not found: "
                    f"{request.command[0]}",
                ) from exc
            except subprocess.TimeoutExpired as exc:
                request.stdout_file.write_text(_as_text(exc.stdout), encoding="utf-8")
                request.stderr_file.write_text(_as_text(exc.stderr), encoding="utf-8")
                raise SprintRunnerError(
                    "FAILED_TIMEOUT",
                    f"Agent {request.agent_name} timed out after "
                    f"{request.timeout_seconds} seconds",
                ) from exc

            stdout = process.stdout or ""
            stderr = process.stderr or ""
            request.stdout_file.write_text(stdout, encoding="utf-8")
            request.stderr_file.write_text(stderr, encoding="utf-8")
            trace.finish(f"Process exited with code {process.returncode}")
            return ExecutionResult(
                command=tuple(request.command),
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                backend=self.name,
                runtime_metadata={},
            )
        except BaseException as exc:
            trace.fail(exc)
            raise
        finally:
            trace.event(events.RESOURCE_RELEASED, "Process cancelled" if self.cancel_event.is_set() else "Process ended")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
