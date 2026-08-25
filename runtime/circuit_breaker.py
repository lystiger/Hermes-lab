from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("hermes.runtime.circuit_breaker")


class CircuitState(str, Enum):
    """Circuit breaker states preventing cascading failures to unavailable providers."""
    CLOSED = "closed"        # Normal operation: traffic allowed
    OPEN = "open"            # Failing: traffic blocked during cooldown
    HALF_OPEN = "half_open"  # Probing: trial traffic permitted to test recovery


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    cooldown_seconds: float = 60.0
    half_open_success_threshold: int = 1


class CircuitBreaker:
    """
    Per-provider/actor circuit breaker managing state transitions between
    CLOSED, OPEN, and HALF_OPEN.
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        on_state_change: Optional[Callable[[str, CircuitState, CircuitState], Any]] = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_state_change = datetime.now(timezone.utc)
        self._opened_at: Optional[datetime] = None
        self._probes_in_flight = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at:
            cooldown_expiry = self._opened_at + timedelta(seconds=self.config.cooldown_seconds)
            if datetime.now(timezone.utc) >= cooldown_expiry:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    def _transition_to(self, new_state: CircuitState) -> None:
        if self._state == new_state:
            return
        prev_state = self._state
        self._state = new_state
        self._last_state_change = datetime.now(timezone.utc)

        if new_state == CircuitState.OPEN:
            self._opened_at = datetime.now(timezone.utc)
            self._consecutive_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._opened_at = None
            self._probes_in_flight = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._probes_in_flight = 0
            self._consecutive_successes = 0

        logger.info("CircuitBreaker '%s' transitioned %s -> %s", self.name, prev_state.value, new_state.value)
        if self.on_state_change:
            try:
                self.on_state_change(self.name, prev_state, new_state)
            except Exception as exc:
                logger.debug("Error in circuit breaker callback: %s", exc)

    def allow_request(self) -> bool:
        current_state = self.state
        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.HALF_OPEN:
            if self._probes_in_flight < self.config.half_open_success_threshold:
                self._probes_in_flight += 1
                return True
            return False
        else:  # OPEN
            return False

    def record_success(self) -> None:
        current_state = self.state
        if current_state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.config.half_open_success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif current_state == CircuitState.CLOSED:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        current_state = self.state
        if current_state == CircuitState.HALF_OPEN:
            # Probe failed -> reopen immediately
            self._transition_to(CircuitState.OPEN)
        elif current_state == CircuitState.CLOSED:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def trip_open(self, cooldown_seconds: Optional[float] = None) -> None:
        """Manually trip circuit into OPEN state."""
        if cooldown_seconds:
            self.config.cooldown_seconds = cooldown_seconds
        self._transition_to(CircuitState.OPEN)

    def reset(self) -> None:
        """Manually reset circuit into CLOSED state."""
        self._transition_to(CircuitState.CLOSED)


class CircuitBreakerRegistry:
    """Registry managing CircuitBreaker instances for all providers and actors."""

    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None):
        self.default_config = default_config or CircuitBreakerConfig()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._listeners: list = []

    def add_listener(self, listener: Callable[[str, CircuitState, CircuitState], Any]) -> None:
        self._listeners.append(listener)

    def _notify_listeners(self, name: str, prev: CircuitState, new: CircuitState) -> None:
        for listener in self._listeners:
            try:
                listener(name, prev, new)
            except Exception as exc:
                logger.debug("Circuit listener error: %s", exc)

    def get_breaker(self, target_id: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        if target_id not in self._breakers:
            self._breakers[target_id] = CircuitBreaker(
                name=target_id,
                config=config or self.default_config,
                on_state_change=self._notify_listeners,
            )
        return self._breakers[target_id]

    def allow_request(self, target_id: str) -> bool:
        breaker = self.get_breaker(target_id)
        return breaker.allow_request()

    def record_success(self, target_id: str) -> None:
        breaker = self.get_breaker(target_id)
        breaker.record_success()

    def record_failure(self, target_id: str) -> None:
        breaker = self.get_breaker(target_id)
        breaker.record_failure()


default_circuit_registry = CircuitBreakerRegistry()
