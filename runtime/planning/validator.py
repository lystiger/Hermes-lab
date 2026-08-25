from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from runtime.limits import RuntimeLimits
from runtime.planning.contracts import StructuredPlan, PlannedTask


@dataclass
class PlanValidationResult:
    """Outcome of deterministic plan validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class PlanValidator:
    """
    Deterministic fail-closed validator for initial structured plans.
    Enforces acyclicity, valid dependencies, capability requirements,
    evidence groundedness, verification strategies, and runtime bounds.
    """

    @classmethod
    def validate(
        cls,
        plan: StructuredPlan,
        repo_dir: Optional[Path] = None,
        available_capabilities: Optional[List[str]] = None,
        limits: Optional[RuntimeLimits] = None,
    ) -> PlanValidationResult:
        errors: List[str] = []
        warnings: List[str] = []
        limits = limits or RuntimeLimits()
        if repo_dir is not None:
            repo_dir = Path(repo_dir).resolve()

        # 1. Non-empty plan
        if not plan.tasks:
            errors.append("Plan contains zero tasks.")
            return PlanValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 2. Bound on initial task count
        max_tasks = limits.max_initial_tasks
        if len(plan.tasks) > max_tasks:
            errors.append(f"Plan contains {len(plan.tasks)} tasks, exceeding max initial task limit of {max_tasks}.")

        # 3. Duplicate and empty task IDs
        task_id_set: Set[str] = set()
        task_map: Dict[str, PlannedTask] = {}
        for t in plan.tasks:
            tid = (t.task_id or "").strip()
            if not tid:
                errors.append("Plan contains a task with an empty task_id.")
                continue
            if tid in task_id_set:
                errors.append(f"Duplicate task_id '{tid}' found in plan.")
            task_id_set.add(tid)
            task_map[tid] = t

            # Empty description
            if not (t.description or "").strip():
                errors.append(f"Task '{tid}' has an empty description.")

            # Valid risk values
            if t.risk not in ("low", "medium", "high"):
                errors.append(f"Task '{tid}' has invalid risk '{t.risk}'; must be 'low', 'medium', or 'high'.")

            # Mandatory capabilities
            if not t.required_capabilities:
                errors.append(f"Task '{tid}' does not declare any required_capabilities.")
            elif available_capabilities is not None:
                if len(available_capabilities) == 0:
                    errors.append(f"Task '{tid}' cannot be satisfied: no dispatchable capabilities are currently available.")
                else:
                    avail_set = set(available_capabilities)
                    for cap in t.required_capabilities:
                        # Match exact or prefix (e.g. 'code.python' matches 'code.python')
                        if cap not in avail_set and not any(cap.startswith(a) or a.startswith(cap) for a in avail_set):
                            errors.append(f"Task '{tid}' requires unsupported/unknown capability '{cap}'.")

            # Non-trivial task completion evidence (acceptance criteria or verification)
            has_verification = bool(t.verification or t.acceptance_criteria)
            if not has_verification and "inspect" not in tid.lower() and "scaffold" not in tid.lower():
                errors.append(f"Task '{tid}' lacks verification strategy and acceptance criteria.")

            # Groundedness: check for hallucinated evidence paths
            if repo_dir and repo_dir.exists() and t.evidence_refs:
                for ref_path in t.evidence_refs:
                    ref_clean = str(ref_path).strip()
                    if not ref_clean or ref_clean.lower() == "new_component":
                        continue
                    full_p = repo_dir / ref_clean
                    if not full_p.exists() and t.evidence_status != "new_component":
                        errors.append(
                            f"Task '{tid}' references non-existent repository path '{ref_clean}' "
                            f"without declaring evidence_status='new_component' (hallucinated path)."
                        )

        # 4. Dependency validity & Acyclicity (Topological Sort / DFS)
        dep_graph: Dict[str, List[str]] = {}
        for tid, t in task_map.items():
            dep_graph[tid] = []
            for dep in t.dependencies:
                dep_clean = str(dep).strip()
                if not dep_clean:
                    continue
                if dep_clean == tid:
                    errors.append(f"Task '{tid}' cannot depend on itself (self-cycle).")
                elif dep_clean not in task_map:
                    errors.append(f"Task '{tid}' depends on non-existent task '{dep_clean}'.")
                else:
                    dep_graph[tid].append(dep_clean)

        # Cycle detection
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        def has_cycle(curr: str, path: List[str]) -> bool:
            visited[curr] = 1
            for neighbor in dep_graph.get(curr, []):
                if visited.get(neighbor, 0) == 1:
                    cycle_path = " -> ".join(path + [neighbor])
                    errors.append(f"Dependency cycle detected in plan: {cycle_path}")
                    return True
                if visited.get(neighbor, 0) == 0:
                    if has_cycle(neighbor, path + [neighbor]):
                        return True
            visited[curr] = 2
            return False

        for tid in task_map:
            if visited.get(tid, 0) == 0:
                has_cycle(tid, [tid])

        # 5. Terminal verification strategy: at least one task must be verification or test-oriented
        has_plan_verification = any(
            any("verify" in c.lower() or "test" in c.lower() or "review" in c.lower() for c in t.required_capabilities)
            or "verify" in t.task_id.lower() or "test" in t.task_id.lower()
            or bool(t.verification)
            for t in plan.tasks
        )
        if not has_plan_verification and len(plan.tasks) > 1:
            errors.append("Plan lacks a terminal verification or test strategy for proposed changes.")

        is_valid = len(errors) == 0
        return PlanValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
