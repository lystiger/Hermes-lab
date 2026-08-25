import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from runtime.task_graph import TaskNode
from capabilities.capabilities import CapabilityRegistry, default_capability_registry
from runtime.capacity import CapacityRegistry, default_capacity_registry, ProviderStatus
from runtime.circuit_breaker import CircuitBreakerRegistry, default_circuit_registry

logger = logging.getLogger("hermes.runtime.routing")


class ReroutePolicy:
    """
    Capability-based task rerouting and failover selector.
    Identifies healthy, capable alternative actors when a primary actor/provider
    encounters capacity limits, outages, or rate-limiting.
    """

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        capacity_registry: Optional[CapacityRegistry] = None,
        circuit_registry: Optional[CircuitBreakerRegistry] = None,
    ):
        self.capability_registry = capability_registry or default_capability_registry
        self.capacity_registry = capacity_registry or default_capacity_registry
        self.circuit_registry = circuit_registry or default_circuit_registry

    def find_alternative_actor(
        self,
        task: TaskNode,
        failed_actor: Optional[str] = None,
        excluded_actors: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Pure capability-based search for a healthy candidate actor.
        NEVER uses hardcoded provider chains.
        """
        excluded: Set[str] = set(excluded_actors or [])
        if failed_actor:
            excluded.add(failed_actor)

        # 1. Query capability registry for all actors matching task requirements
        candidates = self.capability_registry.find_actors(
            required_capabilities=task.required_capabilities,
            excluded_actors=list(excluded),
        )
        if not candidates:
            logger.warning("No alternative actors satisfy capabilities %s for task %s",
                           task.required_capabilities, task.task_id)
            return None

        # 2. Filter candidates through circuit breakers and capacity registry
        for profile, score, info in candidates:
            actor_id = str(getattr(profile, "id", profile.get("id") if isinstance(profile, dict) else profile))
            if actor_id in excluded:
                continue

            # Check circuit breaker
            if not self.circuit_registry.allow_request(actor_id):
                logger.debug("Candidate actor '%s' rejected: circuit breaker OPEN", actor_id)
                continue

            # Check provider capacity & quota
            if not self.capacity_registry.is_actor_available(actor_id):
                provider_id = self.capacity_registry.get_provider_for_actor(actor_id)
                status = self.capacity_registry.get_provider_status(provider_id)
                logger.debug("Candidate actor '%s' rejected: provider '%s' in state %s",
                             actor_id, provider_id, status.value)
                continue

            # Check soft capacity headroom
            is_soft_healthy, soft_reason = self.capacity_registry.check_soft_capacity(actor_id)
            if not is_soft_healthy:
                logger.debug("Candidate actor '%s' rejected: low soft capacity (%s)", actor_id, soft_reason)
                continue

            # Suitable alternative found
            logger.info("Found alternative capable actor '%s' (score: %.2f) for task %s",
                        actor_id, score, task.task_id)
            return actor_id

        logger.warning("All capable alternative actors for task %s are currently throttled/busy/in-cooldown", task.task_id)
        return None


default_reroute_policy = ReroutePolicy()
