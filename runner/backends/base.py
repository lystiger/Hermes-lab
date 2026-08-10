from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ExecutionRequest:
    agent_name: str
    command: Sequence[str]
    cwd: Path
    timeout_seconds: int
    stdout_file: Path
    stderr_file: Path
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    command: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    backend: str
    runtime_metadata: Mapping[str, Any] = field(default_factory=dict)


class ExecutionBackend(ABC):
    name = ""

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Host a worker process and return its captured result."""

    def cleanup(self, success=False):
        """Release only runtime resources owned by this backend instance."""
