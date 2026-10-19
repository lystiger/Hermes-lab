"""Execution backends for Hermes sprint workers."""

from .base import ExecutionBackend, ExecutionRequest, ExecutionResult
from .herdr_backend import HerdrBackend, Seat, SeatPool
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
    "Seat",
    "SeatPool",
    "SubprocessBackend",
    "default_backend_registry",
]
