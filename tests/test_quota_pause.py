import json
from datetime import datetime, timezone

import pytest

from runner.agents.base import reported_provider_error
from runtime.capacity import CapacityRegistry, ProviderFailureClass, ProviderFailureClassifier
from runtime.circuit_breaker import CircuitBreakerRegistry
from runtime.execution import TaskExecutionResult
from runtime.scheduler import DispatchDecision, ReactiveScheduler
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus

LIMIT = "Agent claude exited with code 1:\nProvider error: usage_limit_reached You've hit your session limit · resets 7:10pm (Asia/Ho_Chi_Minh)"


def test_claude_usage_limit_is_a_quota_with_a_reset_time():
    now = datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)  # 18:00 in Ho Chi Minh City
    assert ProviderFailureClassifier.seconds_until_reset(LIMIT, now=now) == 70 * 60
    failure, retry = ProviderFailureClassifier.classify(LIMIT)
    assert failure == ProviderFailureClass.TOKEN_QUOTA_EXHAUSTED and retry > 0


def test_the_provider_error_on_stdout_reaches_the_failure_message():
    stdout = json.dumps({"is_error": True, "api_error": "usage_limit_reached", "result": "You've hit your session limit"})
    assert reported_provider_error(stdout) == "usage_limit_reached You've hit your session limit"
    assert reported_provider_error(json.dumps({"result": "fine"})) is None
    assert reported_provider_error("plain text") is None


class LimitedExecution:
    async def execute(self, **kwargs):
        return TaskExecutionResult(status="failed", error=LIMIT)


@pytest.mark.anyio
async def test_a_quota_limited_task_waits_without_using_an_attempt():
    capacity = CapacityRegistry()
    scheduler = ReactiveScheduler(capacity_registry=capacity, circuit_registry=CircuitBreakerRegistry())
    graph = TaskGraph(job_id="j")
    # Only claude reviews code, so there is no alternative actor to reroute to.
    task = graph.add_task(TaskNode(task_id="t", job_id="j", required_capabilities=["review.code"], assigned_actor="claude"))
    task.status = TaskStatus.RUNNING
    task.attempt = 1

    await scheduler._execute_task_wrapper(task, "claude", DispatchDecision(task_id="t", dispatched=True, actor_id="claude", reason="test"),
                                          graph, LimitedExecution())

    assert task.status == TaskStatus.READY and task.attempt == 0
    provider = capacity.get_provider_for_actor("claude")
    assert not capacity.is_provider_available(provider)
