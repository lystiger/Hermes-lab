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


def argv_safe_prompt(prompt):
    """Keep a prompt from being parsed as a CLI option.

    The persona block starts with "--- ...", and the agent CLIs reject a
    positional or flag value that begins with "-" (claude: unknown option,
    codex: unexpected argument). Lead with a plain line in that case.
    """
    if prompt.startswith("-"):
        return "Instructions:\n" + prompt
    return prompt


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
            phase_metadata = {"phase": phase_name, "prompt": context.prompt}
            if isinstance(context.phase, dict):
                if "priority" in context.phase:
                    phase_metadata["priority"] = context.phase["priority"]
                if "persona" in context.phase:
                    phase_metadata["persona"] = context.phase["persona"]
                elif "role" in context.phase:
                    phase_metadata["persona"] = context.phase["role"]
            result = context.backend.execute(
                ExecutionRequest(
                    agent_name=self.name,
                    command=tuple(command),
                    cwd=context.worktree,
                    timeout_seconds=context.timeout_seconds,
                    stdout_file=context.stdout_file,
                    stderr_file=context.stderr_file,
                    # Sessionful backends deliver the prompt directly instead of via argv.
                    metadata=phase_metadata,
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
                # The adapter decides whether denials exhausted the task or violated scope.
                # A recovered denial must not relabel an unrelated nonzero process exit.
                self.validate_result(result, context)
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
