from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("hermes.runtime.capacity")


class ProviderStatus(str, Enum):
    """Normalized health and availability state for an AI provider."""
    AVAILABLE = "available"
    DEGRADED = "degraded"
    THROTTLED = "throttled"
    QUOTA_EXHAUSTED = "quota_exhausted"
    CONTEXT_PRESSURE = "context_pressure"
    CONTEXT_EXHAUSTED = "context_exhausted"
    AUTH_FAILED = "auth_failed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ActorStatus(str, Enum):
    """Normalized readiness of an individual actor/agent."""
    READY = "ready"
    BUSY = "busy"
    COOLDOWN = "cooldown"
    BLOCKED_PROVIDER = "blocked_provider"
    BLOCKED_QUOTA = "blocked_quota"
    DISABLED = "disabled"


class ProviderFailureClass(str, Enum):
    """Authoritative taxonomy for classifying model and provider errors."""
    RATE_LIMITED = "rate_limited"
    TOKEN_QUOTA_EXHAUSTED = "token_quota_exhausted"
    CONTEXT_TOO_LARGE = "context_too_large"
    AUTHENTICATION = "authentication"
    BILLING = "billing"
    PROVIDER_OUTAGE = "provider_outage"
    MODEL_UNAVAILABLE = "model_unavailable"
    CONTENT_FILTER = "content_filter"
    NETWORK = "network"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


@dataclass
class UsageSnapshot:
    """Normalized token, request, and context usage telemetry."""
    provider_id: str
    model_id: Optional[str] = None
    actor_id: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    requests_used: int = 0
    requests_remaining: Optional[int] = None
    request_limit: Optional[int] = None
    tokens_used: int = 0
    tokens_remaining: Optional[int] = None
    token_limit: Optional[int] = None
    context_window: Optional[int] = None
    context_used: Optional[int] = None
    reset_at: Optional[str] = None
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "internal_accounting"  # "provider_headers", "provider_payload", "internal_accounting", "classified_error"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskBudgetEstimate:
    """Lightweight resource estimate for dispatch planning."""
    expected_input_tokens: int = 0
    expected_output_tokens: int = 0
    expected_turns: int = 1
    confidence: float = 0.5


class ProviderFailureClassifier:
    """
    Classifies raw HTTP errors, status codes, headers, and exceptions into
    the authoritative ProviderFailureClass taxonomy.
    """

    @classmethod
    def classify(
        cls,
        error: Union[Exception, str, Dict[str, Any]],
        status_code: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[ProviderFailureClass, Optional[float]]:
        """
        Returns (failure_class, retry_after_seconds).
        """
        headers = headers or {}
        retry_after = cls.extract_retry_after(headers)

        err_str = str(error).lower()
        if isinstance(error, dict):
            status_code = status_code or error.get("status_code") or error.get("status")
            err_str = f"{err_str} {str(error.get('message', ''))} {str(error.get('detail', ''))}".lower()

        # 1. Check HTTP status code
        if status_code == 429:
            if "quota" in err_str or "insufficient_quota" in err_str or "exceeded your current quota" in err_str:
                return ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED, retry_after
            return ProviderFailureClass.RATE_LIMITED, retry_after

        if status_code in (401, 403):
            return ProviderFailureClass.AUTHENTICATION, None

        if status_code == 402:
            return ProviderFailureClass.BILLING, None

        if status_code in (502, 503, 504):
            return ProviderFailureClass.PROVIDER_OUTAGE, retry_after

        # 2. Match error message signatures
        if "context_length_exceeded" in err_str or "maximum context length" in err_str or "too many tokens" in err_str or "context window" in err_str or "prompt too long" in err_str:
            return ProviderFailureClass.CONTEXT_TOO_LARGE, None

        if "model_not_found" in err_str or "unknown model" in err_str or ("model" in err_str and any(k in err_str for k in ("does not exist", "not found", "unavailable", "deprecated", "unsupported"))):
            return ProviderFailureClass.MODEL_UNAVAILABLE, None

        if "content_filter" in err_str or "safety" in err_str or "blocked by safety policy" in err_str or "responsible ai" in err_str:
            return ProviderFailureClass.CONTENT_FILTER, None

        if "rate limit" in err_str or "too many requests" in err_str or "resource has been exhausted (e.g. check quota)" in err_str:
            if "quota" in err_str or "credit balance" in err_str or "insufficient_quota" in err_str:
                return ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED, retry_after
            return ProviderFailureClass.RATE_LIMITED, retry_after

        if "quota exceeded" in err_str or "exceeded your quota" in err_str or "insufficient quota" in err_str or "billing" in err_str or "payment required" in err_str:
            return ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED, retry_after

        if "invalid api key" in err_str or "unauthorized" in err_str or "authentication" in err_str or "auth error" in err_str or "forbidden" in err_str:
            return ProviderFailureClass.AUTHENTICATION, None

        if "overloaded" in err_str or "capacity" in err_str or "service unavailable" in err_str or "bad gateway" in err_str or "gateway timeout" in err_str:
            return ProviderFailureClass.PROVIDER_OUTAGE, retry_after

        if "connection error" in err_str or "connection reset" in err_str or "connection refused" in err_str or "timeout" in err_str or "ssl error" in err_str or "remote disconnected" in err_str:
            return ProviderFailureClass.NETWORK, retry_after

        return ProviderFailureClass.UNKNOWN, None

    @classmethod
    def extract_retry_after(cls, headers: Dict[str, str]) -> Optional[float]:
        for k, v in headers.items():
            k_lower = k.lower()
            if k_lower in ("retry-after", "retry_after"):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
            elif k_lower in ("x-ratelimit-reset", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
                try:
                    val = float(v)
                    now_ts = datetime.now(timezone.utc).timestamp()
                    if val > now_ts:
                        return val - now_ts
                    return val
                except (ValueError, TypeError):
                    pass
        return None


class CapacityRegistry:
    """
    Authoritative normalized registry for provider health, quota availability,
    token usage telemetry, and actor readiness.
    """

    def __init__(self):
        self._provider_status: Dict[str, ProviderStatus] = {}
        self._provider_reset_at: Dict[str, datetime] = {}
        self._provider_status_reason: Dict[str, str] = {}
        self._actor_status: Dict[str, ActorStatus] = {}
        self._actor_provider_map: Dict[str, str] = {}
        self._usage_snapshots: Dict[str, UsageSnapshot] = {}
        self._job_token_usage: Dict[str, Dict[str, int]] = {}

    def register_actor_provider(self, actor_id: str, provider_id: str) -> None:
        self._actor_provider_map[actor_id] = provider_id
        if provider_id not in self._provider_status:
            self._provider_status[provider_id] = ProviderStatus.AVAILABLE

    def get_provider_for_actor(self, actor_id: str) -> str:
        return self._actor_provider_map.get(actor_id, actor_id)

    def get_provider_status(self, provider_id: str) -> ProviderStatus:
        # Check if throttled/cooldown has expired
        if provider_id in self._provider_reset_at:
            if datetime.now(timezone.utc) >= self._provider_reset_at[provider_id]:
                self._provider_status[provider_id] = ProviderStatus.AVAILABLE
                self._provider_reset_at.pop(provider_id, None)
                self._provider_status_reason.pop(provider_id, None)
        return self._provider_status.get(provider_id, ProviderStatus.AVAILABLE)

    def set_provider_status(
        self,
        provider_id: str,
        status: ProviderStatus,
        reason: Optional[str] = None,
        reset_in_seconds: Optional[float] = None,
    ) -> None:
        self._provider_status[provider_id] = status
        if reason:
            self._provider_status_reason[provider_id] = reason
        if reset_in_seconds and reset_in_seconds > 0:
            self._provider_reset_at[provider_id] = datetime.now(timezone.utc) + timedelta(seconds=reset_in_seconds)
        elif status == ProviderStatus.AVAILABLE:
            self._provider_reset_at.pop(provider_id, None)
            self._provider_status_reason.pop(provider_id, None)

    def record_provider_success(self, provider_id: str, usage: Optional[UsageSnapshot] = None) -> None:
        current = self.get_provider_status(provider_id)
        if current in (ProviderStatus.THROTTLED, ProviderStatus.DEGRADED, ProviderStatus.UNKNOWN):
            self.set_provider_status(provider_id, ProviderStatus.AVAILABLE)
        if usage:
            self._usage_snapshots[provider_id] = usage

    def record_provider_failure(
        self,
        provider_id: str,
        failure_class: ProviderFailureClass,
        retry_after_seconds: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> None:
        if failure_class == ProviderFailureClass.RATE_LIMITED:
            self.set_provider_status(
                provider_id,
                ProviderStatus.THROTTLED,
                reason=reason or "Rate limited",
                reset_in_seconds=retry_after_seconds or 60.0,
            )
        elif failure_class in (ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED, ProviderFailureClass.BILLING):
            self.set_provider_status(
                provider_id,
                ProviderStatus.QUOTA_EXHAUSTED,
                reason=reason or "Quota exhausted",
                reset_in_seconds=retry_after_seconds,
            )
        elif failure_class == ProviderFailureClass.CONTEXT_TOO_LARGE:
            self.set_provider_status(
                provider_id,
                ProviderStatus.CONTEXT_EXHAUSTED,
                reason=reason or "Context window exhausted",
            )
        elif failure_class == ProviderFailureClass.AUTHENTICATION:
            self.set_provider_status(
                provider_id,
                ProviderStatus.AUTH_FAILED,
                reason=reason or "Authentication failure",
            )
        elif failure_class == ProviderFailureClass.PROVIDER_OUTAGE:
            self.set_provider_status(
                provider_id,
                ProviderStatus.UNAVAILABLE,
                reason=reason or "Provider outage",
                reset_in_seconds=retry_after_seconds or 120.0,
            )

    def record_usage(
        self,
        provider_id: str,
        job_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        model_id: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        source: str = "internal_accounting",
    ) -> UsageSnapshot:
        total_tokens = input_tokens + output_tokens
        existing = self._usage_snapshots.get(provider_id)
        if existing:
            new_input = existing.input_tokens + input_tokens
            new_output = existing.output_tokens + output_tokens
            new_cached = existing.cached_tokens + cached_tokens
            new_total = existing.tokens_used + total_tokens
            new_requests = existing.requests_used + 1
            snapshot = UsageSnapshot(
                provider_id=provider_id,
                model_id=model_id or existing.model_id,
                actor_id=actor_id or existing.actor_id,
                input_tokens=new_input,
                output_tokens=new_output,
                cached_tokens=new_cached,
                requests_used=new_requests,
                tokens_used=new_total,
                source=source,
            )
        else:
            snapshot = UsageSnapshot(
                provider_id=provider_id,
                model_id=model_id,
                actor_id=actor_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                requests_used=1,
                tokens_used=total_tokens,
                source=source,
            )
        self._usage_snapshots[provider_id] = snapshot

        if job_id:
            job_totals = self._job_token_usage.setdefault(job_id, {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "total_tokens": 0})
            job_totals["input_tokens"] += input_tokens
            job_totals["output_tokens"] += output_tokens
            job_totals["cached_tokens"] += cached_tokens
            job_totals["total_tokens"] += total_tokens

        return snapshot

    def get_usage(self, provider_id: str) -> Optional[UsageSnapshot]:
        return self._usage_snapshots.get(provider_id)

    def get_job_token_usage(self, job_id: str) -> Dict[str, int]:
        return dict(self._job_token_usage.get(job_id, {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "total_tokens": 0}))

    def is_provider_available(self, provider_id: str) -> bool:
        status = self.get_provider_status(provider_id)
        return status in (ProviderStatus.AVAILABLE, ProviderStatus.DEGRADED)

    def is_actor_available(self, actor_id: str) -> bool:
        provider_id = self.get_provider_for_actor(actor_id)
        return self.is_provider_available(provider_id)


default_capacity_registry = CapacityRegistry()
