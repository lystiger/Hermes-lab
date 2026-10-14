from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .events import ExecutionTrace


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
    # D-009 sink, passed as the `event_sink=` constructor kwarg. None means no-op.
    # Subclasses assign it in __init__; the class default covers subclasses that don't.
    event_sink = None

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Host a worker process and return its captured result."""

    def trace(self, job_id=None, *, cancel_codes=()):
        """Start a D-009 lifecycle trace for one execute() call, bound to this backend's sink."""
        return ExecutionTrace(self.name, self.event_sink, job_id, cancel_codes=cancel_codes)

    def cleanup(self, success=False):
        """Release only runtime resources owned by this backend instance."""

    def release_job(self, job):
        """Release resources pooled for `job` now, at job end. Default: nothing is pooled."""
