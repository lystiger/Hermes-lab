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
    source: str = "unknown"  # "provider_reported", "hermes_estimated", "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SoftCapacityThresholds:
    """Configurable soft-capacity and context pressure thresholds."""
    min_remaining_token_ratio: float = 0.15      # 15% remaining tokens trigger proactive reroute
    min_remaining_request_ratio: float = 0.10    # 10% remaining requests trigger proactive reroute
    context_pressure_ratio: float = 0.85         # 85% context window usage triggers handoff
    min_tokens_for_dispatch: int = 1000          # Minimum token headroom required


@dataclass
class TaskBudgetEstimate:
    """Lightweight resource estimate for dispatch planning."""
    expected_input_tokens: int = 0
    expected_output_tokens: int = 0
    expected_turns: int = 1
    confidence: float = 0.5


class UsageSnapshotNormalizer:
    """
    Normalizes raw provider API responses and HTTP rate-limit headers
    into authoritative UsageSnapshot records without fabricating missing quota.
    """

    @classmethod
    def normalize(
        cls,
        raw_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        provider_id: str = "unknown",
        model_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> UsageSnapshot:
        raw_data = raw_data or {}
        headers = headers or {}

        # Normalize header keys to lowercase
        norm_headers = {k.lower(): v for k, v in headers.items()}

        # 1. Parse token metrics from payload
        usage_dict = raw_data.get("usage") or raw_data.get("token_usage") or raw_data

        input_tok = (
            usage_dict.get("input_tokens")
            or usage_dict.get("prompt_tokens")
            or usage_dict.get("promptTokenCount")
            or 0
        )
        output_tok = (
            usage_dict.get("output_tokens")
            or usage_dict.get("completion_tokens")
            or usage_dict.get("candidatesTokenCount")
            or 0
        )

        cached_tok = (
            usage_dict.get("cached_tokens")
            or (usage_dict.get("prompt_tokens_details") or {}).get("cached_tokens")
            or usage_dict.get("cachedContentTokenCount")
            or 0
        )

        tokens_used = input_tok + output_tok

        # 2. Parse rate-limit headers (Never fabricate remaining quota if missing!)
        def _parse_int_header(*keys: str) -> Optional[int]:
            for k in keys:
                if k in norm_headers:
                    try:
                        return int(float(norm_headers[k]))
                    except (ValueError, TypeError):
                        pass
            return None

        requests_rem = _parse_int_header(
            "x-ratelimit-remaining-requests",
            "x-ratelimit-remaining-req",
            "ratelimit-remaining-requests",
        )
        tokens_rem = _parse_int_header(
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-remaining-tok",
            "ratelimit-remaining-tokens",
        )
        req_limit = _parse_int_header(
            "x-ratelimit-limit-requests",
            "ratelimit-limit-requests",
        )
        tok_limit = _parse_int_header(
            "x-ratelimit-limit-tokens",
            "ratelimit-limit-tokens",
        )

        # 3. Context metrics
        ctx_used = (
            raw_data.get("context_used")
            or raw_data.get("context_tokens")
            or usage_dict.get("total_context_used")
        )
        ctx_window = (
            raw_data.get("context_window")
            or raw_data.get("max_context_tokens")
            or usage_dict.get("context_window")
        )

        # 4. Quota reset
        reset_at = (
            norm_headers.get("x-ratelimit-reset")
            or norm_headers.get("x-ratelimit-reset-requests")
            or norm_headers.get("x-ratelimit-reset-tokens")
            or raw_data.get("reset_at")
        )

        has_provider_data = bool(headers) or bool(raw_data.get("usage")) or bool(raw_data.get("token_usage"))
        source = "provider_reported" if has_provider_data else "unknown"

        return UsageSnapshot(
            provider_id=provider_id,
            model_id=model_id or raw_data.get("model"),
            actor_id=actor_id,
            input_tokens=int(input_tok),
            output_tokens=int(output_tok),
            cached_tokens=int(cached_tok),
            requests_used=1 if tokens_used > 0 else 0,
            requests_remaining=requests_rem,
            request_limit=req_limit,
            tokens_used=int(tokens_used),
            tokens_remaining=tokens_rem,
            token_limit=tok_limit,
            context_window=int(ctx_window) if ctx_window is not None else None,
            context_used=int(ctx_used) if ctx_used is not None else None,
            reset_at=reset_at,
            source=source,
        )


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

    def __init__(self, thresholds: Optional[SoftCapacityThresholds] = None):
        self.thresholds = thresholds or SoftCapacityThresholds()
        self._provider_status: Dict[str, ProviderStatus] = {}
        self._provider_reset_at: Dict[str, datetime] = {}
        self._provider_status_reason: Dict[str, str] = {}
        self._actor_status: Dict[str, ActorStatus] = {}
        self._actor_provider_map: Dict[str, str] = {}
        self._usage_snapshots: Dict[str, UsageSnapshot] = {}
        self._job_token_usage: Dict[str, Dict[str, int]] = {}
        self._provider_success_count: Dict[str, int] = {}
        self._provider_failure_count: Dict[str, int] = {}
        self._provider_failure_breakdown: Dict[str, Dict[str, int]] = {}
        self._provider_throttling_count: Dict[str, int] = {}

    def set_thresholds(self, thresholds: SoftCapacityThresholds) -> None:
        self.thresholds = thresholds

    def check_soft_capacity(
        self,
        actor_id: str,
        task_budget: Optional[TaskBudgetEstimate] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether an actor has sufficient soft headroom before dispatch.
        Returns (is_healthy, reason_if_degraded).
        """
        provider_id = self.get_provider_for_actor(actor_id)
        status = self.get_provider_status(provider_id)
        if status not in (ProviderStatus.AVAILABLE, ProviderStatus.DEGRADED):
            return False, f"provider_{status.value}"

        usage = self._usage_snapshots.get(provider_id)
        if usage:
            # 1. Check remaining token ratio
            if usage.tokens_remaining is not None and usage.token_limit and usage.token_limit > 0:
                ratio = usage.tokens_remaining / usage.token_limit
                if ratio < self.thresholds.min_remaining_token_ratio:
                    return False, f"low_remaining_tokens ({ratio:.1%} < {self.thresholds.min_remaining_token_ratio:.0%})"

            # 2. Check remaining request ratio
            if usage.requests_remaining is not None and usage.request_limit and usage.request_limit > 0:
                req_ratio = usage.requests_remaining / usage.request_limit
                if req_ratio < self.thresholds.min_remaining_request_ratio:
                    return False, f"low_remaining_requests ({req_ratio:.1%} < {self.thresholds.min_remaining_request_ratio:.0%})"

            # 3. Check task budget estimate against remaining tokens
            if task_budget and usage.tokens_remaining is not None:
                expected_needed = task_budget.expected_input_tokens + task_budget.expected_output_tokens
                if expected_needed > 0 and usage.tokens_remaining < expected_needed:
                    return False, f"insufficient_tokens_for_budget (need {expected_needed}, have {usage.tokens_remaining})"

        return True, None

    def check_context_pressure(self, actor_id: str) -> Tuple[bool, Optional[float]]:
        """
        Checks if actor is under heavy context pressure nearing max context window.
        Returns (is_pressured, ratio).
        """
        provider_id = self.get_provider_for_actor(actor_id)
        status = self.get_provider_status(provider_id)
        if status in (ProviderStatus.CONTEXT_PRESSURE, ProviderStatus.CONTEXT_EXHAUSTED):
            return True, 1.0

        usage = self._usage_snapshots.get(provider_id)
        if usage and usage.context_used is not None and usage.context_window and usage.context_window > 0:
            ratio = usage.context_used / usage.context_window
            if ratio >= self.thresholds.context_pressure_ratio:
                return True, ratio

        return False, None

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
        self._provider_success_count[provider_id] = self._provider_success_count.get(provider_id, 0) + 1
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
        self._provider_failure_count[provider_id] = self._provider_failure_count.get(provider_id, 0) + 1
        breakdown = self._provider_failure_breakdown.setdefault(provider_id, {})
        breakdown[failure_class.value] = breakdown.get(failure_class.value, 0) + 1

        if failure_class == ProviderFailureClass.RATE_LIMITED:
            self._provider_throttling_count[provider_id] = self._provider_throttling_count.get(provider_id, 0) + 1
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

    def get_provider_telemetry(self, provider_id: str) -> Dict[str, Any]:
        snapshot = self._usage_snapshots.get(provider_id)
        status = self.get_provider_status(provider_id)
        successes = self._provider_success_count.get(provider_id, 0)
        failures = self._provider_failure_count.get(provider_id, 0)
        total_requests = successes + failures
        success_rate = (successes / total_requests) if total_requests > 0 else 1.0

        return {
            "provider_id": provider_id,
            "status": status.value,
            "status_reason": self._provider_status_reason.get(provider_id),
            "total_requests": total_requests,
            "success_count": successes,
            "failure_count": failures,
            "success_rate": round(success_rate, 4),
            "throttling_count": self._provider_throttling_count.get(provider_id, 0),
            "failure_breakdown": dict(self._provider_failure_breakdown.get(provider_id, {})),
            "usage": snapshot.to_dict() if snapshot else None,
        }

    def get_telemetry_report(self) -> Dict[str, Any]:
        all_providers = set(self._provider_status.keys()) | set(self._usage_snapshots.keys()) | set(self._provider_success_count.keys())
        providers_report = {pid: self.get_provider_telemetry(pid) for pid in all_providers}

        total_input = sum(s.input_tokens for s in self._usage_snapshots.values())
        total_output = sum(s.output_tokens for s in self._usage_snapshots.values())
        total_cached = sum(s.cached_tokens for s in self._usage_snapshots.values())
        total_tokens = sum(s.tokens_used for s in self._usage_snapshots.values())
        total_requests = sum(p["total_requests"] for p in providers_report.values())
        total_failures = sum(p["failure_count"] for p in providers_report.values())
        total_throttles = sum(p["throttling_count"] for p in providers_report.values())

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_providers": len(all_providers),
                "total_requests": total_requests,
                "total_failures": total_failures,
                "total_throttling_events": total_throttles,
                "total_tokens": total_tokens,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cached_tokens": total_cached,
            },
            "providers": providers_report,
            "jobs_tracked": len(self._job_token_usage),
        }

    def get_job_telemetry(self, job_id: str) -> Dict[str, Any]:
        usage = self.get_job_token_usage(job_id)
        return {
            "job_id": job_id,
            "tokens": usage,
        }

    def reset_telemetry(self) -> None:
        self._provider_status.clear()
        self._provider_reset_at.clear()
        self._provider_status_reason.clear()
        self._actor_status.clear()
        self._usage_snapshots.clear()
        self._job_token_usage.clear()
        self._provider_success_count.clear()
        self._provider_failure_count.clear()
        self._provider_failure_breakdown.clear()
        self._provider_throttling_count.clear()


default_capacity_registry = CapacityRegistry()
