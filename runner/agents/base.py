import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backends.base import ExecutionRequest

from .errors import SprintRunnerError

try:
    import sys
    CONTROL_DIR = Path(__file__).resolve().parent.parent
    if str(CONTROL_DIR) not in sys.path:
        sys.path.insert(0, str(CONTROL_DIR))
    from control_plane.event_publisher import default_publisher
except Exception:
    try:
        from runner.control_plane.event_publisher import default_publisher
    except Exception:
        default_publisher = None


@dataclass(frozen=True)
class AgentContext:
    runner: Any
    phase: Mapping[str, Any]
    worktree: Path
    prompt: str
    options: Mapping[str, Any]
    stdout_file: Path
    stderr_file: Path
    timeout_seconds: int
    backend: Any


class AgentAdapter(ABC):
    """Small boundary around one agent CLI and its result contract."""

    name = ""

    @abstractmethod
    def build_command(self, prompt, options, worktree=None):
        """Return the argv used to invoke this agent."""

    def prepare(self, context):
        pass

    def cleanup(self, context):
        pass

    def execute(self, context):
        command = self.build_command(context.prompt, context.options, context.worktree)
        context.runner.logger.info(
            "Launching agent process: %s in worktree %s",
            command[0],
            context.worktree.name,
        )

        phase_name = context.phase.get("name", "")
        start_time = time.monotonic()
        sprint_id = getattr(context.runner, "sprint_id", None)

        if default_publisher:
            default_publisher.publish(
                source_id=self.name,
                source_kind="agent",
                kind="agent.started",
                detail=f"Executing phase {phase_name or self.name} in worktree {context.worktree.name}",
                job_id=sprint_id,
                metadata={"command": command[0], "phase": phase_name},
            )

        try:
            self.prepare(context)
            result = context.backend.execute(
                ExecutionRequest(
                    agent_name=self.name,
                    command=tuple(command),
                    cwd=context.worktree,
                    timeout_seconds=context.timeout_seconds,
                    stdout_file=context.stdout_file,
                    stderr_file=context.stderr_file,
                    metadata={"phase": phase_name},
                )
            )
        except Exception as exc:
            duration_s = f"{time.monotonic() - start_time:.2f}s"
            if default_publisher:
                default_publisher.publish(
                    source_id=self.name,
                    source_kind="agent",
                    kind="agent.failed",
                    detail=f"Agent {self.name} raised exception: {str(exc)}",
                    duration=duration_s,
                    job_id=sprint_id,
                    metadata={"phase": phase_name, "error": str(exc)},
                )
            raise
        finally:
            self.cleanup(context)

        duration_s = f"{time.monotonic() - start_time:.2f}s"
        context.runner.logger.info(
            "Agent %s process completed via %s with exit code %s",
            self.name,
            result.backend,
            result.returncode,
        )

        if result.returncode != 0:
            stderr = result.stderr or ""
            if default_publisher:
                default_publisher.publish(
                    source_id=self.name,
                    source_kind="agent",
                    kind="agent.failed",
                    detail=f"Agent {self.name} exited with code {result.returncode}",
                    duration=duration_s,
                    job_id=sprint_id,
                    metadata={"phase": phase_name, "returncode": result.returncode},
                )

            if "permission denied" in stderr.lower():
                raise SprintRunnerError(
                    "FAILED_PERMISSION_DENIED",
                    f"Agent {self.name} permission denied:\n{stderr}",
                )
            raise SprintRunnerError(
                "FAILED_AGENT_EXECUTION",
                f"Agent {self.name} exited with code {result.returncode}:\n{stderr}",
            )

        try:
            self.validate_result(result, context)
        except Exception as exc:
            if default_publisher:
                default_publisher.publish(
                    source_id=self.name,
                    source_kind="agent",
                    kind="agent.failed",
                    detail=f"Agent {self.name} validation failed: {str(exc)}",
                    duration=duration_s,
                    job_id=sprint_id,
                    metadata={"phase": phase_name, "error": str(exc)},
                )
            raise

        if default_publisher:
            default_publisher.publish(
                source_id=self.name,
                source_kind="agent",
                kind="agent.finished",
                detail=f"Phase {phase_name or self.name} completed successfully",
                duration=duration_s,
                job_id=sprint_id,
                metadata={"phase": phase_name, "returncode": 0},
            )

        return result

    @abstractmethod
    def validate_result(self, result, context):
        """Raise SprintRunnerError when an ostensibly successful result is invalid."""
