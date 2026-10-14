import subprocess

from agents.errors import SprintRunnerError

from . import events
from .base import ExecutionBackend, ExecutionResult


class SubprocessBackend(ExecutionBackend):
    name = "subprocess"

    def __init__(self, run_process=None, sprint_id=None, event_sink=None, **kwargs):
        self._run_process = run_process or subprocess.run
        self.sprint_id = sprint_id
        self.event_sink = event_sink

    def execute(self, request):
        trace = self.trace(self.sprint_id)
        trace.started(f"Subprocess started for agent '{request.agent_name}'")
        try:
            return self._execute(request, trace)
        except BaseException as exc:
            trace.fail(exc)
            raise

    def _execute(self, request, trace):
        # subprocess.run does not expose the child's pid, so the resource id is the execution id.
        trace.bind(resource=events.resource("process", trace.execution_id, request.agent_name))
        trace.event(events.RESOURCE_ACQUIRED, f"Process slot for agent '{request.agent_name}'")
        try:
            trace.event(events.RESOURCE_READY, "Command argv is complete")
            trace.event(events.RUNNING, "Worker process running")
            try:
                process = self._run_process(
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
            trace.event(events.RESOURCE_RELEASED, "Process ended")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
