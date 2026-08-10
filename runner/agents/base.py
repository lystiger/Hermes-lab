from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from backends.base import ExecutionRequest

from .errors import SprintRunnerError


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
                    metadata={"phase": context.phase.get("name", "")},
                )
            )
        finally:
            self.cleanup(context)

        context.runner.logger.info(
            "Agent %s process completed via %s with exit code %s",
            self.name,
            result.backend,
            result.returncode,
        )

        if result.returncode != 0:
            stderr = result.stderr or ""
            if "permission denied" in stderr.lower():
                raise SprintRunnerError(
                    "FAILED_PERMISSION_DENIED",
                    f"Agent {self.name} permission denied:\n{stderr}",
                )
            raise SprintRunnerError(
                "FAILED_AGENT_EXECUTION",
                f"Agent {self.name} exited with code {result.returncode}:\n{stderr}",
            )

        self.validate_result(result, context)
        return result

    @abstractmethod
    def validate_result(self, result, context):
        """Raise SprintRunnerError when an ostensibly successful result is invalid."""
