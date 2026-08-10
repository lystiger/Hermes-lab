import subprocess

from agents.errors import SprintRunnerError

from .base import ExecutionBackend, ExecutionResult


class SubprocessBackend(ExecutionBackend):
    name = "subprocess"

    def __init__(self, run_process=None, **kwargs):
        self._run_process = run_process or subprocess.run

    def execute(self, request):
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
        return ExecutionResult(
            command=tuple(request.command),
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            backend=self.name,
            runtime_metadata={},
        )


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
