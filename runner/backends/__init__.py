"""Execution backends for Hermes sprint workers."""

from .base import ExecutionBackend, ExecutionRequest, ExecutionResult
from .herdr_backend import HerdrBackend
from .openrig_backend import OpenRigBackend
from .registry import BackendRegistry, default_backend_registry
from .subprocess_backend import SubprocessBackend

__all__ = [
    "BackendRegistry",
    "ExecutionBackend",
    "ExecutionRequest",
    "ExecutionResult",
    "HerdrBackend",
    "OpenRigBackend",
    "SubprocessBackend",
    "default_backend_registry",
]
