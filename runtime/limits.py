from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass
class RuntimeLimits:
    """Configurable boundaries to prevent infinite execution and resource exhaustion."""
    max_replans_per_job: int = 3
    max_repairs_per_job: int = 3
    max_task_attempts: int = 2
    max_runtime_depth: int = 5
    max_subagent_depth: int = 2
    max_tasks_per_job: int = 50
    concurrency_limit: int = 4

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeLimits":
        return cls(
            max_replans_per_job=int(data.get("max_replans_per_job") or data.get("maxReplansPerJob", 3)),
            max_repairs_per_job=int(data.get("max_repairs_per_job") or data.get("maxRepairsPerJob", 3)),
            max_task_attempts=int(data.get("max_task_attempts") or data.get("maxTaskAttempts", 2)),
            max_runtime_depth=int(data.get("max_runtime_depth") or data.get("maxRuntimeDepth", 5)),
            max_subagent_depth=int(data.get("max_subagent_depth") or data.get("maxSubagentDepth", 2)),
            max_tasks_per_job=int(data.get("max_tasks_per_job") or data.get("maxTasksPerJob", 50)),
            concurrency_limit=int(data.get("concurrency_limit") or data.get("concurrencyLimit", 4)),
        )
