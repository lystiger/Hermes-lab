import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union

from runtime.task_graph import TaskNode
from runtime.observations import Observation

logger = logging.getLogger("hermes.runtime.execution")


class AgentRunStatus(str, Enum):
    """Lifecycle states of an individual agent execution run."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class AgentRun:
    """Authoritative record of a single task execution run by an actor."""
    run_id: str
    job_id: str
    task_id: str
    actor_id: str
    status: AgentRunStatus = AgentRunStatus.INITIALIZING
    attempt: int = 1
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None
    exit_reason: Optional[str] = None
    artifact_refs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[Union[Dict[str, Any], str]] = None
    delegation_decision: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentRun":
        st = data.get("status", "initializing")
        return cls(
            run_id=str(data.get("run_id") or data.get("runId") or data.get("id", "")),
            job_id=str(data.get("job_id") or data.get("jobId", "")),
            task_id=str(data.get("task_id") or data.get("taskId", "")),
            actor_id=str(data.get("actor_id") or data.get("actorId", "")),
            status=AgentRunStatus(st.lower()) if isinstance(st, str) else st,
            attempt=int(data.get("attempt", 1)),
            started_at=data.get("started_at") or data.get("startedAt", datetime.now(timezone.utc).isoformat()),
            finished_at=data.get("finished_at") or data.get("finishedAt"),
            exit_reason=data.get("exit_reason") or data.get("exitReason"),
            artifact_refs=list(data.get("artifact_refs") or data.get("artifactRefs") or []),
            error=data.get("error"),
            delegation_decision=data.get("delegation_decision") or data.get("delegationDecision"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class TaskExecutionResult:
    """The structured outcome of an actor task execution."""
    status: str = "succeeded"  # "succeeded" | "failed"
    exit_reason: Optional[str] = None
    output: Optional[Any] = None
    artifact_refs: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    error: Optional[Union[Dict[str, Any], str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "exit_reason": self.exit_reason,
            "output": self.output,
            "artifact_refs": self.artifact_refs,
            "observations": [o.to_dict() if hasattr(o, "to_dict") else o for o in self.observations],
            "error": self.error,
            "metadata": self.metadata,
        }


class ActorAdapter:
    """Base interface for executing tasks on registered actors."""

    async def execute_task(
        self,
        task: TaskNode,
        run: AgentRun,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        raise NotImplementedError


class CallableActorAdapter(ActorAdapter):
    """Adapter wrapping a synchronous or asynchronous callable function."""

    def __init__(self, func: Callable):
        self.func = func

    async def execute_task(
        self,
        task: TaskNode,
        run: AgentRun,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        import inspect
        ctx = context or {}
        if inspect.iscoroutinefunction(self.func):
            res = await self.func(task, run, ctx)
        else:
            res = self.func(task, run, ctx)

        if isinstance(res, TaskExecutionResult):
            return res
        if isinstance(res, dict):
            return TaskExecutionResult(
                status=res.get("status", "succeeded"),
                exit_reason=res.get("exit_reason"),
                artifact_refs=res.get("artifact_refs", []),
                observations=res.get("observations", []),
                error=res.get("error"),
                metadata=res.get("metadata", {}),
            )
        return TaskExecutionResult(status="succeeded", exit_reason=str(res))


class ExecutionManager:
    """Manages actor execution runs and execution adapters."""

    def __init__(self):
        self._adapters: Dict[str, ActorAdapter] = {}
        self._default_adapter: Optional[ActorAdapter] = None
        self._runs: Dict[str, AgentRun] = {}

    def register_adapter(self, actor_id: str, adapter: Union[ActorAdapter, Callable]) -> None:
        if isinstance(adapter, ActorAdapter):
            self._adapters[actor_id] = adapter
        elif callable(adapter):
            self._adapters[actor_id] = CallableActorAdapter(adapter)
        else:
            raise TypeError(f"Adapter must be ActorAdapter or callable, got {type(adapter)}")

    def set_default_adapter(self, adapter: Union[ActorAdapter, Callable]) -> None:
        if isinstance(adapter, ActorAdapter):
            self._default_adapter = adapter
        elif callable(adapter):
            self._default_adapter = CallableActorAdapter(adapter)
        else:
            raise TypeError(f"Adapter must be ActorAdapter or callable, got {type(adapter)}")

    def get_run(self, run_id: str) -> Optional[AgentRun]:
        return self._runs.get(run_id)

    def list_runs_for_job(self, job_id: str) -> List[AgentRun]:
        runs = [r for r in self._runs.values() if r.job_id == job_id]
        runs.sort(key=lambda r: r.started_at)
        return runs

    def list_runs_for_task(self, task_id: str) -> List[AgentRun]:
        runs = [r for r in self._runs.values() if r.task_id == task_id]
        runs.sort(key=lambda r: r.started_at)
        return runs

    async def execute(
        self,
        task: TaskNode,
        actor_id: str,
        delegation_decision: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        event_bridge: Any = None,
    ) -> TaskExecutionResult:
        run_id = f"run_{int(time.time() * 1000)}_{len(self._runs) + 1:04d}"
        run = AgentRun(
            run_id=run_id,
            job_id=task.job_id,
            task_id=task.task_id,
            actor_id=actor_id,
            status=AgentRunStatus.RUNNING,
            attempt=task.attempt,
            delegation_decision=delegation_decision,
        )
        self._runs[run_id] = run

        if event_bridge:
            event_bridge.emit_agent_started(run=run, task=task)

        adapter = self._adapters.get(actor_id) or self._default_adapter
        if not adapter:
            error_msg = f"No execution adapter registered for actor '{actor_id}' and no default adapter configured"
            run.status = AgentRunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc).isoformat()
            run.exit_reason = "missing_adapter"
            run.error = error_msg
            if event_bridge:
                event_bridge.emit_agent_failed(run=run, task=task, error=error_msg)
            return TaskExecutionResult(status="failed", error=error_msg, exit_reason="missing_adapter")

        # Resolve timeout
        timeout_seconds = None
        if isinstance(task.metadata, dict) and task.metadata.get("timeout_seconds"):
            try:
                timeout_seconds = float(task.metadata["timeout_seconds"])
            except (ValueError, TypeError):
                pass
        elif isinstance(context, dict) and context.get("timeout_seconds"):
            try:
                timeout_seconds = float(context["timeout_seconds"])
            except (ValueError, TypeError):
                pass

        try:
            if timeout_seconds and timeout_seconds > 0:
                result = await asyncio.wait_for(
                    adapter.execute_task(task=task, run=run, context=context),
                    timeout=timeout_seconds,
                )
            else:
                result = await adapter.execute_task(task=task, run=run, context=context)

            run.finished_at = datetime.now(timezone.utc).isoformat()

            if result.status == "succeeded":
                run.status = AgentRunStatus.SUCCEEDED
                run.exit_reason = result.exit_reason or "normal_completion"
                run.artifact_refs.extend(result.artifact_refs)
                if event_bridge:
                    event_bridge.emit_agent_finished(run=run, task=task, result=result)
            else:
                run.status = AgentRunStatus.FAILED
                run.exit_reason = result.exit_reason or "execution_failure"
                run.error = result.error
                if event_bridge:
                    event_bridge.emit_agent_failed(run=run, task=task, error=str(result.error))

            return result

        except asyncio.TimeoutError:
            error_msg = f"Task execution timed out after {timeout_seconds} seconds"
            run.status = AgentRunStatus.TIMED_OUT
            run.finished_at = datetime.now(timezone.utc).isoformat()
            run.exit_reason = "timeout"
            run.error = error_msg
            logger.warning("Task %s on actor %s timed out after %s seconds", task.task_id, actor_id, timeout_seconds)
            if event_bridge and hasattr(event_bridge, "emit_agent_timed_out"):
                event_bridge.emit_agent_timed_out(run=run, task=task, timeout_seconds=timeout_seconds)
            elif event_bridge:
                event_bridge.emit_agent_failed(run=run, task=task, error=error_msg)
            return TaskExecutionResult(status="failed", error=error_msg, exit_reason="timeout")

        except Exception as exc:
            run.status = AgentRunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc).isoformat()
            run.exit_reason = "exception"
            run.error = str(exc)
            logger.exception("Exception executing task %s on actor %s: %s", task.task_id, actor_id, exc)
            if event_bridge:
                event_bridge.emit_agent_failed(run=run, task=task, error=str(exc))
            return TaskExecutionResult(status="failed", error=str(exc), exit_reason="exception")
