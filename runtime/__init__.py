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
    ProductionPlannerAdapter,
    BoundedReplanner,
)
from runtime.events import RuntimeEventBridge
from runtime.scheduler import ReactiveScheduler, DispatchDecision
from runtime.engine import ReactiveJobEngine
from runtime.hermes_adapter import HermesActorAdapter, HermesVerifierAdapter, HermesPlannerAdapter
from runtime.capacity import (
    ProviderStatus,
    ActorStatus,
    ProviderFailureClass,
    UsageSnapshot,
    ProviderFailureClassifier,
    CapacityRegistry,
    default_capacity_registry,
)
from runtime.circuit_breaker import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerRegistry,
    default_circuit_registry,
)
from runtime.lease import (
    JobLease,
    JobLeaseStore,
    InMemoryJobLeaseStore,
    PostgresJobLeaseStore,
    JobLeaseManager,
)
from runtime.recovery import (
    RecoveryDisposition,
    RecoveryMetrics,
    InterruptedTaskReconciler,
    RecoveryManager,
)
from runtime.routing import (
    ReroutePolicy,
    default_reroute_policy,
)
from runtime.planning import (
    EvidenceFile,
    RepositoryEvidence,
    RepositoryReconnaissance,
    PlannedTask,
    StructuredPlan,
    PlanningRequest,
    PlanValidator,
    PlanValidationResult,
    GroundedPlanner,
)

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
    "ProductionPlannerAdapter",
    "BoundedReplanner",
    "RuntimeEventBridge",
    "ReactiveScheduler",
    "DispatchDecision",
    "ReactiveJobEngine",
    "HermesActorAdapter",
    "HermesVerifierAdapter",
    "HermesPlannerAdapter",
    "ProviderStatus",
    "ActorStatus",
    "ProviderFailureClass",
    "UsageSnapshot",
    "ProviderFailureClassifier",
    "CapacityRegistry",
    "default_capacity_registry",
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "default_circuit_registry",
    "JobLease",
    "JobLeaseStore",
    "InMemoryJobLeaseStore",
    "PostgresJobLeaseStore",
    "JobLeaseManager",
    "RecoveryDisposition",
    "RecoveryMetrics",
    "InterruptedTaskReconciler",
    "RecoveryManager",
    "ReroutePolicy",
    "default_reroute_policy",
    "EvidenceFile",
    "RepositoryEvidence",
    "RepositoryReconnaissance",
    "PlannedTask",
    "StructuredPlan",
    "PlanningRequest",
    "PlanValidator",
    "PlanValidationResult",
    "GroundedPlanner",
]
