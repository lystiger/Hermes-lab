from datetime import datetime, timezone
import pytest

from runtime.capacity import (
    ProviderStatus,
    ActorStatus,
    ProviderFailureClass,
    ProviderFailureClassifier,
    CapacityRegistry,
    UsageSnapshot,
)


def test_classify_429_as_rate_limited():
    """
    Test S: HTTP 429 is classified as RATE_LIMITED (or TOKEN_QUOTA_EXHAUSTED if quota message).
    """
    failure_class, retry_after = ProviderFailureClassifier.classify(
        error="Too Many Requests: rate limit exceeded",
        status_code=429,
        headers={"Retry-After": "30"},
    )
    assert failure_class == ProviderFailureClass.RATE_LIMITED
    assert retry_after == 30.0


def test_classify_429_quota_exhaustion():
    """
    Test T: Quota exhaustion classified as TOKEN_QUOTA_EXHAUSTED and marks provider unavailable.
    """
    failure_class, _ = ProviderFailureClassifier.classify(
        error="You have exceeded your current quota, please check your plan and billing details.",
        status_code=429,
    )
    assert failure_class == ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED

    reg = CapacityRegistry()
    reg.register_actor_provider("claude_actor", "anthropic")
    reg.record_provider_failure(
        provider_id="anthropic",
        failure_class=failure_class,
        reason="Quota exhausted",
    )

    assert reg.get_provider_status("anthropic") == ProviderStatus.QUOTA_EXHAUSTED
    assert reg.is_provider_available("anthropic") is False
    assert reg.is_actor_available("claude_actor") is False


def test_extract_retry_after_headers():
    """
    Test U: Retry-After and x-ratelimit-reset headers are correctly parsed.
    """
    headers = {"retry-after": "45.5"}
    retry_after = ProviderFailureClassifier.extract_retry_after(headers)
    assert retry_after == 45.5

    now_ts = datetime.now(timezone.utc).timestamp()
    headers_reset = {"x-ratelimit-reset": str(now_ts + 60)}
    retry_reset = ProviderFailureClassifier.extract_retry_after(headers_reset)
    assert retry_reset is not None
    assert 58 <= retry_reset <= 62


def test_classify_context_limit_error():
    """
    Test V: Context length exhaustion is classified as CONTEXT_TOO_LARGE.
    """
    failure_class, _ = ProviderFailureClassifier.classify(
        error="maximum context length is 128000 tokens, however you requested 135000 tokens",
    )
    assert failure_class == ProviderFailureClass.CONTEXT_TOO_LARGE


def test_unknown_usage_stays_unknown_not_fabricated():
    """
    Test W: Unknown usage fields remain None or UNKNOWN without inventing limits.
    """
    snap = UsageSnapshot(provider_id="custom_provider")
    assert snap.tokens_remaining is None
    assert snap.token_limit is None
    assert snap.requests_remaining is None
    assert snap.source in ("unknown", "internal_accounting")


def test_usage_aggregation_counts_tokens_and_jobs():
    """
    Test X: Input, output, and cached tokens are aggregated across calls and jobs accurately.
    """
    reg = CapacityRegistry()
    reg.record_usage(
        provider_id="openai",
        job_id="job_1",
        actor_id="gpt4",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=200,
    )
    reg.record_usage(
        provider_id="openai",
        job_id="job_1",
        actor_id="gpt4",
        input_tokens=2000,
        output_tokens=800,
        cached_tokens=400,
    )

    usage = reg.get_usage("openai")
    assert usage.input_tokens == 3000
    assert usage.output_tokens == 1300
    assert usage.cached_tokens == 600
    assert usage.tokens_used == 4300
    assert usage.requests_used == 2

    job_usage = reg.get_job_token_usage("job_1")
    assert job_usage["input_tokens"] == 3000
    assert job_usage["output_tokens"] == 1300
    assert job_usage["total_tokens"] == 4300
