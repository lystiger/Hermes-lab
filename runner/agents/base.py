import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backends.base import ExecutionRequest

from .errors import SprintRunnerError

try:
    import sys
    ROOT_DIR = Path(__file__).resolve().parent.parent.parent
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from event_bus import event_bus
except Exception:
    event_bus = None


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

        if event_bus:
            event_bus.publish(
                source_id=self.name,
                source_kind="agent",
                kind="agent.started",
                detail=f"Executing phase {phase_name or self.name} in worktree {context.worktree.name}",
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
            if event_bus:
                event_bus.publish(
                    source_id=self.name,
                    source_kind="agent",
                    kind="agent.failed",
                    detail=f"Agent {self.name} raised exception: {str(exc)}",
                    duration=duration_s,
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
            if event_bus:
                event_bus.publish(
                    source_id=self.name,
                    source_kind="agent",
                    kind="agent.failed",
                    detail=f"Agent {self.name} exited with code {result.returncode}",
                    duration=duration_s,
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
            if event_bus:
                event_bus.publish(
                    source_id=self.name,
                    source_kind="agent",
                    kind="agent.failed",
                    detail=f"Agent {self.name} validation failed: {str(exc)}",
                    duration=duration_s,
                    metadata={"phase": phase_name, "error": str(exc)},
                )
            raise

        if event_bus:
            event_bus.publish(
                source_id=self.name,
                source_kind="agent",
                kind="agent.finished",
                detail=f"Phase {phase_name or self.name} completed successfully",
                duration=duration_s,
                metadata={"phase": phase_name, "returncode": 0},
            )

        return result

    @abstractmethod
    def validate_result(self, result, context):
        """Raise SprintRunnerError when an ostensibly successful result is invalid."""
