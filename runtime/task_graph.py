from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger("hermes.runtime.task_graph")


class TaskStatus(str, Enum):
    """Runtime execution status of an individual task node."""
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


@dataclass
class TaskNode:
    """An individual unit of work within the dynamic task graph."""
    task_id: str
    job_id: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    assigned_actor: Optional[str] = None
    parent_task_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    attempt: int = 0
    max_attempts: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifact_refs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[Union[Dict[str, Any], str]] = None
    superseded_by: Optional[str] = None
    supersede_reason: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status.upper())
        self.required_capabilities = [str(c).strip() for c in self.required_capabilities if str(c).strip()]
        self.dependencies = [str(d).strip() for d in self.dependencies if str(d).strip()]

    @property
    def is_active(self) -> bool:
        return self.status in {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING}

    @property
    def is_terminal(self) -> bool:
        return self.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SUPERSEDED}

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["taskId"] = self.task_id
        data["jobId"] = self.job_id
        data["requiredCapabilities"] = self.required_capabilities
        data["assignedActor"] = self.assigned_actor
        data["createdAt"] = self.created_at
        data["startedAt"] = self.started_at
        data["completedAt"] = self.completed_at
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskNode":
        st = data.get("status", "PENDING")
        return cls(
            task_id=str(data.get("task_id") or data.get("taskId") or data.get("id", "")),
            job_id=str(data.get("job_id") or data.get("jobId", "")),
            description=str(data.get("description") or data.get("name") or data.get("task", "")),
            status=TaskStatus(st.upper()) if isinstance(st, str) else st,
            dependencies=list(data.get("dependencies") or []),
            required_capabilities=list(data.get("required_capabilities") or data.get("requiredCapabilities") or []),
            assigned_actor=data.get("assigned_actor") or data.get("assignedActor") or data.get("assigned_agent"),
            parent_task_id=data.get("parent_task_id") or data.get("parentTaskId"),
            created_at=data.get("created_at") or data.get("createdAt", datetime.now(timezone.utc).isoformat()),
            started_at=data.get("started_at") or data.get("startedAt"),
            completed_at=data.get("completed_at") or data.get("completedAt"),
            attempt=int(data.get("attempt", 0)),
            max_attempts=int(data.get("max_attempts") or data.get("maxAttempts", 2)),
            metadata=dict(data.get("metadata") or {}),
            artifact_refs=list(data.get("artifact_refs") or data.get("artifactRefs") or data.get("artifacts") or []),
            error=data.get("error"),
            superseded_by=data.get("superseded_by") or data.get("supersededBy"),
            supersede_reason=data.get("supersede_reason") or data.get("supersedeReason"),
        )


class TaskGraph:
    """
    Mutable, incremental dependency task graph for reactive job execution.
    Allows dynamic expansion, addition/removal of dependencies, and task superseding.
    """

    def __init__(self, job_id: Optional[str] = None):
        self.job_id = job_id or ""
        self._tasks: Dict[str, TaskNode] = {}

    def add_task(self, task: Union[TaskNode, Dict[str, Any]]) -> TaskNode:
        if isinstance(task, dict):
            node = TaskNode.from_dict(task)
        else:
            node = task

        if node.task_id in self._tasks:
            raise ValueError(
                f"Task '{node.task_id}' already exists in task graph. Duplicate task IDs are forbidden."
            )

        if not node.job_id and self.job_id:
            node.job_id = self.job_id

        self._tasks[node.task_id] = node
        return node

    def _has_path(self, start_id: str, target_id: str) -> bool:
        """Helper to determine if target_id is reachable from start_id via dependencies."""
        visited = set()
        queue = [start_id]
        while queue:
            curr = queue.pop(0)
            if curr == target_id:
                return True
            if curr in visited:
                continue
            visited.add(curr)
            node = self._tasks.get(curr)
            if node:
                for dep_id in node.dependencies:
                    if dep_id not in visited:
                        queue.append(dep_id)
        return False

    def add_dependency(self, task_id: str, depends_on_task_id: str) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"Task '{task_id}' not found in task graph")
        if depends_on_task_id not in self._tasks:
            raise KeyError(f"Dependency task '{depends_on_task_id}' not found in task graph")
        if task_id == depends_on_task_id:
            raise ValueError(f"Task '{task_id}' cannot depend on itself")

        # Cycle detection: check if depends_on_task_id already reaches task_id
        if self._has_path(depends_on_task_id, task_id):
            raise ValueError(
                f"Dependency cycle detected: adding '{task_id}' -> '{depends_on_task_id}' creates a circular dependency."
            )

        task = self._tasks[task_id]
        if depends_on_task_id not in task.dependencies:
            task.dependencies.append(depends_on_task_id)

    def get_task(self, task_id: str) -> Optional[TaskNode]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[TaskNode]:
        return list(self._tasks.values())

    def remove_task(self, task_id: str) -> Optional[TaskNode]:
        if task_id not in self._tasks:
            return None

        # Safe removal invariant: ensure no remaining tasks depend on task_id
        dependents = [t for t in self._tasks.values() if task_id in t.dependencies]
        if dependents:
            dep_ids = [t.task_id for t in dependents]
            raise ValueError(
                f"Cannot remove task '{task_id}': dependent task(s) {dep_ids} exist. Use supersede_task() instead."
            )

        return self._tasks.pop(task_id, None)

    def mark_ready(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        if task.status not in {TaskStatus.SUCCEEDED, TaskStatus.SUPERSEDED, TaskStatus.CANCELLED}:
            task.status = TaskStatus.READY

    def mark_running(self, task_id: str, actor_id: Optional[str] = None) -> None:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        now_iso = datetime.now(timezone.utc).isoformat()
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or now_iso
        if actor_id:
            task.assigned_actor = actor_id
        task.attempt += 1

    def mark_success(
        self,
        task_id: str,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        task.status = TaskStatus.SUCCEEDED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.error = None
        if artifacts:
            task.artifact_refs.extend(artifacts)
        if metadata:
            task.metadata.update(metadata)

    def mark_failure(
        self,
        task_id: str,
        error: Optional[Union[Dict[str, Any], str]] = None,
        allow_retry: bool = True,
    ) -> None:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        now_iso = datetime.now(timezone.utc).isoformat()
        task.error = error

        if allow_retry and task.attempt < task.max_attempts:
            # Mark ready for retry attempt
            task.status = TaskStatus.READY
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = now_iso

    def mark_blocked(self, task_id: str, reason: Optional[str] = None) -> None:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        task.status = TaskStatus.BLOCKED
        if reason:
            task.metadata["blocked_reason"] = reason

    def mark_cancelled(self, task_id: str, reason: Optional[str] = None) -> None:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        if reason:
            task.metadata["cancelled_reason"] = reason

    def supersede_task(
        self,
        task_id: str,
        superseded_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Marks a task as superseded so it is excluded from completion checks."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        task.status = TaskStatus.SUPERSEDED
        task.superseded_by = superseded_by
        task.supersede_reason = reason
        task.completed_at = datetime.now(timezone.utc).isoformat()

    def find_ready_tasks(self) -> List[TaskNode]:
        """
        Determines all tasks eligible for immediate execution.
        A task is ready if:
        1. It is currently in READY status, OR
        2. It is PENDING and all its dependencies are SUCCEEDED (or SUPERSEDED).
        """
        ready_tasks = []
        for task in self._tasks.values():
            if task.status == TaskStatus.READY:
                ready_tasks.append(task)
            elif task.status == TaskStatus.PENDING:
                dependencies_satisfied = True
                for dep_id in task.dependencies:
                    dep = self._tasks.get(dep_id)
                    if not dep or dep.status not in {TaskStatus.SUCCEEDED, TaskStatus.SUPERSEDED}:
                        dependencies_satisfied = False
                        break
                if dependencies_satisfied:
                    ready_tasks.append(task)
        return ready_tasks

    def find_blocked_tasks(self) -> List[TaskNode]:
        """
        Identifies active tasks whose dependencies have failed, blocked, or been cancelled.
        """
        blocked_tasks = []
        for task in self._tasks.values():
            if task.status in {TaskStatus.PENDING, TaskStatus.READY}:
                for dep_id in task.dependencies:
                    dep = self._tasks.get(dep_id)
                    if not dep or dep.status in {TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED}:
                        blocked_tasks.append(task)
                        break
        return blocked_tasks

    def find_dependency_blocked_tasks(self) -> List[TaskNode]:
        """
        Identifies active tasks whose dependencies have failed, blocked, or been cancelled.
        """
        return self.find_blocked_tasks()

    def has_running_tasks(self) -> bool:
        """Returns True if any task is actively RUNNING."""
        return any(t.status == TaskStatus.RUNNING for t in self._tasks.values())

    def has_runnable_tasks(self) -> bool:
        """Returns True if any task is ready for execution."""
        return len(self.find_ready_tasks()) > 0

    def is_stalled(self) -> bool:
        """
        Returns True if execution cannot naturally progress:
        - No tasks are currently RUNNING
        - No tasks are RUNNABLE / READY
        - The graph is NOT all completed
        - Incomplete work remains (dependency-blocked or failed tasks)
        """
        if self.has_running_tasks() or self.has_runnable_tasks():
            return False
        if self.is_all_completed():
            return False
        # If there are active tasks in graph that cannot run
        incomplete = [
            t for t in self._tasks.values()
            if t.status not in {TaskStatus.SUCCEEDED, TaskStatus.SUPERSEDED, TaskStatus.CANCELLED}
        ]
        return len(incomplete) > 0

    def is_all_completed(self) -> bool:
        """Returns True if the graph is non-empty and all non-superseded, non-cancelled tasks are SUCCEEDED."""
        active_nodes = [t for t in self._tasks.values() if t.status not in {TaskStatus.SUPERSEDED, TaskStatus.CANCELLED}]
        if not active_nodes:
            return False
        return all(t.status == TaskStatus.SUCCEEDED for t in active_nodes)

    def has_active_tasks(self) -> bool:
        """
        Returns True if runnable or running work exists.
        Does NOT return True for permanently dependency-blocked pending tasks.
        """
        return self.has_running_tasks() or self.has_runnable_tasks()

    def has_failed_tasks(self) -> bool:
        """Returns True if any active task is in FAILED status."""
        return any(t.status == TaskStatus.FAILED for t in self._tasks.values())

    def count(self) -> int:
        return len(self._tasks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "tasks": [t.to_dict() for t in self._tasks.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskGraph":
        graph = cls(job_id=data.get("job_id") or data.get("jobId"))
        for t_data in data.get("tasks", []):
            graph.add_task(TaskNode.from_dict(t_data))
        return graph
