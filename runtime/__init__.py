"""
LysStack Reactive Runtime Spine (Phase 8).
Provides an event-driven, mutable, capability-aware execution runtime.
"""

from runtime.job_state import (
    JobState,
    JobRecord,
    InvalidStateTransitionError,
    LEGAL_JOB_TRANSITIONS,
    TERMINAL_JOB_STATES,
)
from runtime.task_graph import (
    TaskStatus,
    TaskNode,
    TaskGraph,
)
from runtime.observations import (
    Observation,
    ObservationRegistry,
    default_observation_registry,
)
from runtime.execution import (
    AgentRunStatus,
    AgentRun,
    TaskExecutionResult,
    ActorAdapter,
    CallableActorAdapter,
    ExecutionManager,
)
from runtime.verification import (
    VerificationStatus,
    VerificationCheck,
    VerificationResult,
    VerifierAdapter,
    CallableVerifierAdapter,
    DefaultPassVerifierAdapter,
)
from runtime.limits import RuntimeLimits
from runtime.replanning import (
    GraphMutationType,
    GraphMutation,
    ReplanReason,
    ReplanRequest,
    ReplanResult,
    PlannerAdapter,
    CallablePlannerAdapter,
    BoundedReplanner,
)
from runtime.events import RuntimeEventBridge
from runtime.scheduler import ReactiveScheduler, DispatchDecision
from runtime.engine import ReactiveJobEngine
from runtime.hermes_adapter import HermesActorAdapter, HermesVerifierAdapter

__all__ = [
    "JobState",
    "JobRecord",
    "InvalidStateTransitionError",
    "LEGAL_JOB_TRANSITIONS",
    "TERMINAL_JOB_STATES",
    "TaskStatus",
    "TaskNode",
    "TaskGraph",
    "Observation",
    "ObservationRegistry",
    "default_observation_registry",
    "AgentRunStatus",
    "AgentRun",
    "TaskExecutionResult",
    "ActorAdapter",
    "CallableActorAdapter",
    "ExecutionManager",
    "VerificationStatus",
    "VerificationCheck",
    "VerificationResult",
    "VerifierAdapter",
    "CallableVerifierAdapter",
    "DefaultPassVerifierAdapter",
    "RuntimeLimits",
    "GraphMutationType",
    "GraphMutation",
    "ReplanReason",
    "ReplanRequest",
    "ReplanResult",
    "PlannerAdapter",
    "CallablePlannerAdapter",
    "BoundedReplanner",
    "RuntimeEventBridge",
    "ReactiveScheduler",
    "DispatchDecision",
    "ReactiveJobEngine",
    "HermesActorAdapter",
    "HermesVerifierAdapter",
]
