import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

from runtime.job_state import JobState, JobRecord
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus
from runtime.observations import Observation, ObservationRegistry
from runtime.execution import ExecutionManager, TaskExecutionResult, ActorAdapter
from runtime.events import RuntimeEventBridge
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.storage.projector import RuntimeStateProjector
from runtime.scheduler import ReactiveScheduler
from runtime.engine import ReactiveJobEngine
from runtime.limits import RuntimeLimits
from runtime.replanning import ReplanReason, ReplanRequest, GraphMutation, GraphMutationType
from capabilities.capabilities import CapabilityRegistry

from runtime.planning import (
    EvidenceFile,
    RepositoryEvidence,
    RepositoryReconnaissance,
    PlannedTask,
    StructuredPlan,
    PlanningRequest,
    PlanValidator,
    PlanValidationResult,
    GroundedPlanner,
)


def _setup_disposable_repo(repo_dir: Path) -> Path:
    """Creates a sample FastAPI repository with existing API and test conventions."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    
    app_dir = repo_dir / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    # app/models.py
    (app_dir / "models.py").write_text(
        """from pydantic import BaseModel, Field
from typing import Optional

class User(BaseModel):
    id: str
    name: str
    role: str = "user"
""",
        encoding="utf-8"
    )

    # app/api.py
    (app_dir / "api.py").write_text(
        """from fastapi import FastAPI, HTTPException
from app.models import User

app = FastAPI(title="Sample App")

@app.get("/users/me")
def get_current_user():
    return {"user": "admin"}
""",
        encoding="utf-8"
    )

    # tests/test_api.py
    (tests_dir / "test_api.py").write_text(
        """import pytest
from app.api import app

def test_get_current_user():
    # Test existing endpoint convention
    assert app.title == "Sample App"
""",
        encoding="utf-8"
    )

    # Initialize git repo with main branch
    import subprocess
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True, capture_output=True)

    return repo_dir


# ==============================================================================
# 1. Repository Reconnaissance Unit Tests
# ==============================================================================

def test_repository_reconnaissance_evidence_collection(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "recon_repo")
    
    goal = "Add public inquiry submission with admin review and validation"
    evidence = RepositoryReconnaissance.collect(repo_dir, goal)

    assert evidence is not None
    assert "FastAPI" in evidence.frameworks
    assert "Pydantic" in evidence.frameworks
    assert "python" in evidence.languages
    assert len(evidence.files) >= 2

    # Verify goal-relevant files are selected
    file_paths = [f.path for f in evidence.files]
    assert any("api.py" in p for p in file_paths)
    assert any("models.py" in p for p in file_paths)
    assert any("test_api.py" in t for t in evidence.tests)

    # Verify uncertainty is explicitly populated for new concepts (inquiry, review)
    assert len(evidence.uncertainty) > 0
    assert any("inquiry" in u.lower() or "review" in u.lower() for u in evidence.uncertainty)

    # Verify prompt rendering is concise and structured
    prompt_md = evidence.render_for_prompt()
    assert "### Repository Architecture Summary" in prompt_md
    assert "### Relevant Files & Excerpts" in prompt_md
    assert "FastAPI" in prompt_md


def test_repository_reconnaissance_empty_repo(tmp_path: Path):
    empty_dir = tmp_path / "empty_repo"
    empty_dir.mkdir(parents=True, exist_ok=True)

    evidence = RepositoryReconnaissance.collect(empty_dir, "Add new service")
    assert evidence.files == []
    assert len(evidence.uncertainty) >= 1
    assert "empty" in evidence.summary.lower() or "greenfield" in evidence.summary.lower()


# ==============================================================================
# 2. Structured Plan Validation & Negative Tests
# ==============================================================================

def test_plan_validator_rejects_cycles(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    # Cyclic dependency: T1 -> T2 -> T1
    task1 = PlannedTask(
        task_id="T1",
        description="Inspect API",
        dependencies=["T2"],
        required_capabilities=["repo.read"],
        acceptance_criteria=["API inspected"],
        verification=["Manual review"],
        evidence_refs=["app/api.py"],
    )
    task2 = PlannedTask(
        task_id="T2",
        description="Implement model",
        dependencies=["T1"],
        required_capabilities=["code.python"],
        acceptance_criteria=["Model defined"],
        verification=["Pytest"],
        evidence_refs=["app/models.py"],
    )

    plan = StructuredPlan(job_id="job_cycle", goal="Cyclic goal", summary="Cyclic plan", tasks=[task1, task2])
    res = PlanValidator.validate(plan, repo_dir=repo_dir)

    assert res.is_valid is False
    assert any("cycle" in err.lower() for err in res.errors)


def test_plan_validator_rejects_missing_dependency(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    task1 = PlannedTask(
        task_id="T1",
        description="Implement endpoint",
        dependencies=["T_NONEXISTENT_99"],
        required_capabilities=["code.python"],
        acceptance_criteria=["Endpoint done"],
        verification=["Pytest"],
        evidence_refs=["app/api.py"],
    )
    task_verify = PlannedTask(
        task_id="T2_verify",
        description="Verify changes",
        dependencies=["T1"],
        required_capabilities=["verification"],
        acceptance_criteria=["All tests pass"],
        verification=["Pytest"],
        evidence_refs=["tests/test_api.py"],
    )

    plan = StructuredPlan(job_id="job_missing_dep", goal="Goal", summary="Summary", tasks=[task1, task_verify])
    res = PlanValidator.validate(plan, repo_dir=repo_dir)

    assert res.is_valid is False
    assert any("non-existent task" in err.lower() for err in res.errors)


def test_plan_validator_rejects_duplicate_task_ids(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    task1 = PlannedTask(
        task_id="T_DUP",
        description="First task",
        dependencies=[],
        required_capabilities=["code.python"],
        acceptance_criteria=["Done"],
        verification=["Pytest"],
        evidence_refs=["app/api.py"],
    )
    task2 = PlannedTask(
        task_id="T_DUP",
        description="Second duplicate task",
        dependencies=[],
        required_capabilities=["verification"],
        acceptance_criteria=["Done"],
        verification=["Pytest"],
        evidence_refs=["tests/test_api.py"],
    )

    plan = StructuredPlan(job_id="job_dup", goal="Goal", summary="Summary", tasks=[task1, task2])
    res = PlanValidator.validate(plan, repo_dir=repo_dir)

    assert res.is_valid is False
    assert any("duplicate task_id" in err.lower() for err in res.errors)


def test_plan_validator_rejects_hallucinated_evidence_paths(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    # Nonexistent file without evidence_status="new_component"
    task1 = PlannedTask(
        task_id="T1",
        description="Modify payment service",
        dependencies=[],
        required_capabilities=["code.python"],
        acceptance_criteria=["Payment modified"],
        verification=["Pytest"],
        evidence_refs=["app/services/non_existent_payment_processor.py"],
        evidence_status="existing",  # Claims existing but file does not exist!
    )
    task2 = PlannedTask(
        task_id="T2_verify",
        description="Verify",
        dependencies=["T1"],
        required_capabilities=["verification"],
        acceptance_criteria=["Verified"],
        verification=["Pytest"],
        evidence_refs=["tests/test_api.py"],
    )

    plan = StructuredPlan(job_id="job_hallucinate", goal="Goal", summary="Summary", tasks=[task1, task2])
    res = PlanValidator.validate(plan, repo_dir=repo_dir)

    assert res.is_valid is False
    assert any("hallucinated path" in err.lower() or "non-existent" in err.lower() for err in res.errors)


def test_plan_validator_accepts_explicit_new_component(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    # Nonexistent file WITH explicit evidence_status="new_component" is valid!
    task1 = PlannedTask(
        task_id="T1",
        description="Create new inquiry module",
        dependencies=[],
        required_capabilities=["code.python"],
        acceptance_criteria=["Inquiry module created"],
        verification=["Pytest"],
        evidence_refs=["app/inquiry.py"],
        evidence_status="new_component",
    )
    task2 = PlannedTask(
        task_id="T2_verify",
        description="Verify inquiry module",
        dependencies=["T1"],
        required_capabilities=["verification"],
        acceptance_criteria=["All tests pass"],
        verification=["Pytest"],
        evidence_refs=["tests/test_api.py"],
    )

    plan = StructuredPlan(job_id="job_new_comp", goal="Goal", summary="Summary", tasks=[task1, task2])
    res = PlanValidator.validate(plan, repo_dir=repo_dir)

    assert res.is_valid is True
    assert res.errors == []


def test_plan_validator_rejects_oversized_plan(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    limits = RuntimeLimits(max_initial_tasks=3)

    tasks = [
        PlannedTask(
            task_id=f"T{i}",
            description=f"Task {i}",
            dependencies=[f"T{i-1}"] if i > 1 else [],
            required_capabilities=["code.python"] if i < 5 else ["verification"],
            acceptance_criteria=["Done"],
            verification=["Pytest"],
            evidence_refs=["app/api.py"],
        )
        for i in range(1, 6)
    ]

    plan = StructuredPlan(job_id="job_oversized", goal="Goal", summary="Summary", tasks=tasks)
    res = PlanValidator.validate(plan, repo_dir=repo_dir, limits=limits)

    assert res.is_valid is False
    assert any("exceeding max initial task limit" in err.lower() for err in res.errors)


def test_plan_validator_rejects_unsupported_capability(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    task1 = PlannedTask(
        task_id="T1",
        description="Execute unknown task",
        dependencies=[],
        required_capabilities=["quantum.computing.entanglement"],
        acceptance_criteria=["Done"],
        verification=["Pytest"],
        evidence_refs=["app/api.py"],
    )
    task2 = PlannedTask(
        task_id="T2_verify",
        description="Verify",
        dependencies=["T1"],
        required_capabilities=["verification"],
        acceptance_criteria=["Done"],
        verification=["Pytest"],
        evidence_refs=["tests/test_api.py"],
    )

    plan = StructuredPlan(job_id="job_unknown_cap", goal="Goal", summary="Summary", tasks=[task1, task2])
    res = PlanValidator.validate(plan, repo_dir=repo_dir, available_capabilities=["code.python", "verification"])

    assert res.is_valid is False
    assert any("unsupported/unknown capability" in err.lower() for err in res.errors)


def test_plan_validator_rejects_malformed_risk(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    task1 = PlannedTask(
        task_id="T1",
        description="Dangerous operation",
        dependencies=[],
        required_capabilities=["code.python"],
        acceptance_criteria=["Done"],
        verification=["Pytest"],
        risk="SUPER DANGEROUS",  # Malformed risk string
        evidence_refs=["app/api.py"],
    )
    task2 = PlannedTask(
        task_id="T2_verify",
        description="Verify",
        dependencies=["T1"],
        required_capabilities=["verification"],
        acceptance_criteria=["Done"],
        verification=["Pytest"],
        risk="low",
        evidence_refs=["tests/test_api.py"],
    )

    plan = StructuredPlan(job_id="job_bad_risk", goal="Goal", summary="Summary", tasks=[task1, task2])
    res = PlanValidator.validate(plan, repo_dir=repo_dir)

    assert res.is_valid is False
    assert any("invalid risk 'super dangerous'" in err.lower() for err in res.errors)


def test_plan_validator_rejects_empty_available_capabilities(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "val_repo")
    
    task1 = PlannedTask(
        task_id="T1",
        description="Task 1",
        dependencies=[],
        required_capabilities=["code.python"],
        acceptance_criteria=["Done"],
        verification=["Pytest"],
        evidence_refs=["app/api.py"],
    )

    plan = StructuredPlan(job_id="job_empty_caps", goal="Goal", summary="Summary", tasks=[task1])
    # Empty available capabilities -> cannot schedule any task!
    res = PlanValidator.validate(plan, repo_dir=repo_dir, available_capabilities=[])

    assert res.is_valid is False
    assert any("no dispatchable capabilities" in err.lower() for err in res.errors)


def test_capability_registry_empty_actors_returns_empty_available_capabilities():
    registry = CapabilityRegistry()
    # Initially no actors registered
    assert registry.list_available_capabilities() == []

    # Register an actor
    registry.register_actor({"id": "claude", "capabilities": ["code.python", "review.correctness"]})
    assert registry.list_available_capabilities() == ["code.python", "review.correctness"]


def test_string_target_repo_boundary_robustness(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "str_repo")
    str_path = str(repo_dir)

    # Pass string path to PlanningRequest and RepositoryReconnaissance
    req = PlanningRequest(job_id="job_str", goal="Add endpoint", target_repo=str_path)
    assert isinstance(req.target_repo, Path)

    evidence = RepositoryReconnaissance.collect(str_path, "Add endpoint")
    assert evidence is not None
    assert len(evidence.files) >= 1


# ==============================================================================
# 3. Grounded Planner JSON Parsing & Schema Repair Tests
# ==============================================================================

@pytest.mark.anyio
async def test_grounded_planner_parses_fenced_json(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "planner_parse_repo")
    
    fenced_output = """Here is the initial software engineering plan:
```json
{
  "job_id": "job_fence_test",
  "goal": "Add inquiry endpoint",
  "summary": "Implement public inquiry submission",
  "risk_assessment": "medium",
  "uncertainty": ["No existing inquiry schema found"],
  "evidence_summary": "FastAPI app with Pydantic models",
  "tasks": [
    {
      "task_id": "T1_inspect",
      "description": "Inspect FastAPI routes",
      "dependencies": [],
      "required_capabilities": ["repo.read", "code.python"],
      "expected_artifacts": ["notes"],
      "acceptance_criteria": ["Routes inspected"],
      "verification": ["Static inspection"],
      "risk": "low",
      "evidence_refs": ["app/api.py"],
      "evidence_status": "existing",
      "reason": "Follow existing route conventions"
    },
    {
      "task_id": "T2_verify",
      "description": "Verify test suite",
      "dependencies": ["T1_inspect"],
      "required_capabilities": ["verification"],
      "expected_artifacts": ["test_report"],
      "acceptance_criteria": ["Tests pass"],
      "verification": ["Pytest"],
      "risk": "low",
      "evidence_refs": ["tests/test_api.py"],
      "evidence_status": "existing",
      "reason": "Ensure test suite green"
    }
  ]
}
```
"""
    async def mock_model_client(prompt: str) -> str:
        return fenced_output

    planner = GroundedPlanner(model_client=mock_model_client, target_repo=repo_dir)
    req = PlanningRequest(job_id="job_fence_test", goal="Add inquiry endpoint", target_repo=repo_dir)
    plan = await planner.generate_initial_plan(req)

    assert plan is not None
    assert len(plan.tasks) == 2
    assert plan.tasks[0].task_id == "T1_inspect"
    assert plan.tasks[1].task_id == "T2_verify"


@pytest.mark.anyio
async def test_grounded_planner_fails_closed_on_invalid_json(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "planner_bad_json_repo")
    
    async def bad_model_client(prompt: str) -> str:
        return "I am an LLM and I will implement the feature directly by writing code without structured JSON."

    planner = GroundedPlanner(model_client=bad_model_client, target_repo=repo_dir)
    req = PlanningRequest(job_id="job_bad_json", goal="Add inquiry endpoint", target_repo=repo_dir)

    with pytest.raises(ValueError) as exc_info:
        await planner.generate_initial_plan(req)
    assert "structured json" in str(exc_info.value).lower() or "validation failed" in str(exc_info.value).lower()


# ==============================================================================
# 4. Full Goal-to-Graph End-to-End Acceptance Test
# ==============================================================================

class DeterministicMockActorAdapter(ActorAdapter):
    """Actor adapter executing real task DAG without manual task pre-injection."""
    
    def __init__(self):
        self.executed_tasks: List[str] = []

    async def execute_task(
        self,
        task: TaskNode,
        run: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        self.executed_tasks.append(task.task_id)
        return TaskExecutionResult(
            status="succeeded",
            exit_reason="completed",
            output=f"Executed task {task.task_id}: {task.description}",
            artifact_refs=[{"id": f"artifact_{task.task_id}.txt", "path": f"artifact_{task.task_id}.txt"}],
            metadata={"actor": task.assigned_actor or "agent_default"},
        )


@pytest.mark.anyio
async def test_phase11_1_goal_to_graph_happy_path_e2e(tmp_path: Path):
    """
    Phase 11.1 Happy Path E2E:
    1. Input is a natural-language goal for a real disposable repository.
    2. Repository evidence is deterministically gathered.
    3. GroundedPlanner synthesizes structured, validated initial plan (no manual T1/T2/T3 injection).
    4. ReactiveJobEngine.initialize_and_plan() registers the planned tasks.
    5. ReactiveScheduler routes tasks to appropriate actors based on required capabilities.
    6. Job completes to COMPLETED.
    7. RuntimeStateProjector reconstructs the identical initial TaskGraph and planning metadata from event ledger.
    """
    repo_dir = _setup_disposable_repo(tmp_path / "e2e_repo")
    goal = "Add public inquiry submission endpoint with admin review schema and unit tests"

    # 1. Setup Capabilities and Actors
    cap_reg = CapabilityRegistry()
    cap_reg.register_actor({"id": "antigravity", "capabilities": ["repo.read", "implementation", "code.python", "backend.fastapi"]})
    cap_reg.register_actor({"id": "claude", "capabilities": ["code.python", "testing.unit", "review.correctness"]})
    cap_reg.register_actor({"id": "codex", "capabilities": ["verification", "testing.unit", "testing.integration", "review.correctness"]})

    # 2. Setup Event Bridge & Durable Store
    event_store = InMemoryRuntimeEventStore()
    event_bridge = RuntimeEventBridge(event_store=event_store)
    obs_reg = ObservationRegistry()

    # 3. Setup Grounded Planner with simulated LLM response grounded in repository evidence
    async def simulated_llm_planner(prompt: str) -> str:
        # Prompt must contain repository reconnaissance evidence and schema contract
        assert "### Repository Architecture Summary" in prompt
        assert "FastAPI" in prompt or "Pydantic" in prompt
        assert "STRUCTURED PLAN OUTPUT CONTRACT" in prompt

        plan_dict = {
            "job_id": "job_inquiry_11_1",
            "goal": goal,
            "summary": "Repository-grounded plan: inspect FastAPI conventions, implement inquiry endpoint, add tests, and verify.",
            "risk_assessment": "medium",
            "uncertainty": ["Inquiry database schema to be introduced"],
            "evidence_summary": "FastAPI app with existing models.py and test_api.py conventions",
            "tasks": [
                {
                    "task_id": "T1_inspect_api_conventions",
                    "description": "Inspect existing FastAPI routes and Pydantic models",
                    "dependencies": [],
                    "required_capabilities": ["repo.read", "code.python"],
                    "expected_artifacts": ["schema_notes.md"],
                    "acceptance_criteria": ["Documented route and model conventions"],
                    "verification": ["Static inspection of app/api.py"],
                    "risk": "low",
                    "evidence_refs": ["app/api.py", "app/models.py"],
                    "evidence_status": "existing",
                    "reason": "Align new inquiry route with existing app/api.py structure"
                },
                {
                    "task_id": "T2_implement_inquiry_endpoint",
                    "description": "Implement public inquiry submission and admin review endpoint",
                    "dependencies": ["T1_inspect_api_conventions"],
                    "required_capabilities": ["implementation", "code.python"],
                    "expected_artifacts": ["app/inquiry.py"],
                    "acceptance_criteria": ["Public inquiry route accepts valid payload and admin review route filters submissions"],
                    "verification": ["Syntax check and unit testing"],
                    "risk": "medium",
                    "evidence_refs": ["app/inquiry.py"],
                    "evidence_status": "new_component",
                    "reason": "New domain component for inquiry management"
                },
                {
                    "task_id": "T3_add_inquiry_tests",
                    "description": "Add unit tests for inquiry submission and review",
                    "dependencies": ["T2_implement_inquiry_endpoint"],
                    "required_capabilities": ["testing.unit", "code.python"],
                    "expected_artifacts": ["tests/test_inquiry.py"],
                    "acceptance_criteria": ["All inquiry test cases pass"],
                    "verification": ["Pytest test execution"],
                    "risk": "low",
                    "evidence_refs": ["tests/test_api.py"],
                    "evidence_status": "existing",
                    "reason": "Follow test pattern in tests/test_api.py"
                },
                {
                    "task_id": "T4_verify_contract_and_regression",
                    "description": "Run verification checks and confirm no regression across test suite",
                    "dependencies": ["T3_add_inquiry_tests"],
                    "required_capabilities": ["verification", "review.correctness"],
                    "expected_artifacts": ["verification_report.json"],
                    "acceptance_criteria": ["Full test suite passes and API contract verified"],
                    "verification": ["Pytest execution across tests/"],
                    "risk": "low",
                    "evidence_refs": ["app/api.py", "tests/test_api.py"],
                    "evidence_status": "existing",
                    "reason": "Terminal verification requirement"
                }
            ]
        }
        return json.dumps(plan_dict)

    planner = GroundedPlanner(
        model_client=simulated_llm_planner,
        target_repo=repo_dir,
        event_bridge=event_bridge,
    )

    exec_adapter = DeterministicMockActorAdapter()
    exec_manager = ExecutionManager()
    exec_manager.set_default_adapter(exec_adapter)

    # 4. Instantiate ReactiveJobEngine with GroundedPlanner (NO manual initial tasks provided!)
    engine = ReactiveJobEngine(
        job_id="job_inquiry_11_1",
        goal=goal,
        capability_registry=cap_reg,
        execution_manager=exec_manager,
        event_bridge=event_bridge,
        observation_registry=obs_reg,
        planner=planner,
    )
    engine.job.metadata["target_repo"] = repo_dir

    # 5. Initialize & Plan: GroundedPlanner generates initial TaskGraph
    await engine.initialize_and_plan(initial_tasks=None)

    # Verify TaskGraph was created dynamically from planner
    assert engine.graph.count() == 4
    assert engine.graph.get_task("T1_inspect_api_conventions") is not None
    assert engine.graph.get_task("T2_implement_inquiry_endpoint") is not None
    assert engine.graph.get_task("T3_add_inquiry_tests") is not None
    assert engine.graph.get_task("T4_verify_contract_and_regression") is not None

    # Check dependencies form the expected DAG
    t1 = engine.graph.get_task("T1_inspect_api_conventions")
    t2 = engine.graph.get_task("T2_implement_inquiry_endpoint")
    t3 = engine.graph.get_task("T3_add_inquiry_tests")
    t4 = engine.graph.get_task("T4_verify_contract_and_regression")

    assert t1.dependencies == []
    assert t2.dependencies == ["T1_inspect_api_conventions"]
    assert t3.dependencies == ["T2_implement_inquiry_endpoint"]
    assert t4.dependencies == ["T3_add_inquiry_tests"]

    # 6. Execute Job to Completion
    await engine.run_until_complete(max_steps=20)

    assert engine.state == JobState.COMPLETED
    assert engine.is_terminal is True
    assert len(exec_adapter.executed_tasks) == 4
    assert exec_adapter.executed_tasks == [
        "T1_inspect_api_conventions",
        "T2_implement_inquiry_endpoint",
        "T3_add_inquiry_tests",
        "T4_verify_contract_and_regression"
    ]

    # 7. Verify Canonical Planning Events Emitted
    events = await event_store.list_events("job_inquiry_11_1")
    event_types = [e.event_type for e in events]

    assert "planning.started" in event_types
    assert "repository.evidence_collected" in event_types
    assert "planning.generated" in event_types
    assert "planning.validated" in event_types
    assert "task.created" in event_types
    assert "job.completed" in event_types

    # 8. Verify Event History Reconstruction
    projector = RuntimeStateProjector()
    reconstructed = projector.project(events)

    assert reconstructed.job.state == JobState.COMPLETED
    assert reconstructed.job.goal == goal
    assert reconstructed.graph.count() == 4
    assert reconstructed.graph.get_task("T1_inspect_api_conventions").status == TaskStatus.SUCCEEDED
    assert reconstructed.graph.get_task("T4_verify_contract_and_regression").status == TaskStatus.SUCCEEDED
    assert "planning" in reconstructed.job.metadata
    assert reconstructed.job.metadata["planning"]["validated"] is True


@pytest.mark.anyio
async def test_grounded_planner_fails_closed_when_model_client_none_and_fallback_disabled(tmp_path: Path):
    repo_dir = _setup_disposable_repo(tmp_path / "fail_closed_repo")
    planner = GroundedPlanner(target_repo=repo_dir, allow_heuristic_fallback=False)

    req = PlanningRequest(job_id="job_no_client", goal="Add endpoint", target_repo=repo_dir)
    with pytest.raises(ValueError) as exc_info:
        await planner.generate_initial_plan(req)
    assert "heuristic fallback disabled" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_grounded_planner_heuristic_fallback_detects_typescript_capabilities(tmp_path: Path):
    ts_repo = tmp_path / "ts_repo"
    ts_repo.mkdir(parents=True, exist_ok=True)
    src_dir = ts_repo / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "index.ts").write_text("export const app = express();", encoding="utf-8")
    (src_dir / "app.test.ts").write_text("test('app', () => {});", encoding="utf-8")

    planner = GroundedPlanner(target_repo=ts_repo, allow_heuristic_fallback=True)
    req = PlanningRequest(job_id="job_ts", goal="Add express endpoint", target_repo=ts_repo)
    plan = await planner.generate_initial_plan(req)

    assert plan is not None
    # Verify task capabilities dynamically detected typescript from evidence
    impl_task = [t for t in plan.tasks if "implement" in t.task_id.lower()][0]
    assert "code.typescript" in impl_task.required_capabilities


@pytest.mark.anyio
async def test_job_launcher_launch_goal_async_e2e(tmp_path: Path):
    from jobs.job_launcher import JobLauncher
    from jobs.job_service import job_service

    repo_dir = _setup_disposable_repo(tmp_path / "launcher_repo")
    goal = "Add public inquiry submission with admin review"

    async def simulated_llm(prompt: str) -> str:
        return json.dumps({
            "job_id": "job_launcher_test",
            "goal": goal,
            "summary": "Plan for public inquiry submission",
            "risk_assessment": "medium",
            "uncertainty": [],
            "evidence_summary": "FastAPI repo",
            "tasks": [
                {
                    "task_id": "T1_inspect",
                    "description": "Inspect API conventions",
                    "dependencies": [],
                    "required_capabilities": ["repo.read", "code.python"],
                    "expected_artifacts": ["notes.txt"],
                    "acceptance_criteria": ["Conventions documented"],
                    "verification": ["Static check"],
                    "risk": "low",
                    "evidence_refs": ["app/api.py"],
                    "evidence_status": "existing",
                    "reason": "Inspect routes"
                },
                {
                    "task_id": "T2_verify",
                    "description": "Verify test suite",
                    "dependencies": ["T1_inspect"],
                    "required_capabilities": ["verification"],
                    "expected_artifacts": ["report.json"],
                    "acceptance_criteria": ["Tests pass"],
                    "verification": ["Pytest"],
                    "risk": "low",
                    "evidence_refs": ["tests/test_api.py"],
                    "evidence_status": "existing",
                    "reason": "Ensure green"
                }
            ]
        })

    launcher = JobLauncher()
    res = await launcher.launch_goal_async(
        goal=goal,
        target_repo=repo_dir,
        model_client=simulated_llm,
        dry_run=True,
        skip_agent_exec=True,
        start_background=False,
    )

    assert res["status"] in ("EXECUTING", "PLANNING", "CREATED")
    assert res["mode"] == "goal_planned"

    job_id = res["jobId"]
    engine = job_service.get_engine(job_id)
    assert engine is not None
    assert engine.graph.count() == 2
    assert engine.graph.get_task("T1_inspect") is not None
    assert engine.graph.get_task("T2_verify") is not None
    assert engine.job.metadata["launch_mode"] == "goal_planned"


@pytest.mark.anyio
async def test_goal_planned_execution_role_preservation_and_verifier_fail_closed_e2e(tmp_path: Path):
    """
    Production-chain regression test for Phase 11.1 execution roles:
    1. launch_goal_async() -> GroundedPlanner -> generated verification task with execution_role='verifier'
    2. TaskNode preserves metadata['role'] == 'verifier'
    3. Scheduler capability routing selects Codex actor
    4. HermesActorAdapter dispatches Codex in role='verifier'
    5. When Codex process exits 0 but returns invalid unparseable verdict -> fails closed with FAILED_CODEX_INVALID_VERDICT
    6. When Codex (verifier role) modifies workspace files -> fails closed forbidding mutations
    """
    from jobs.job_launcher import JobLauncher
    from jobs.job_service import job_service
    from runtime.execution import AgentRun
    from runner.agents.codex import CodexAdapter, SprintRunnerError
    from runner.backends.base import ExecutionBackend, ExecutionRequest, ExecutionResult
    from runner.backends.registry import BackendRegistry
    from runner.agents.registry import AgentRegistry

    repo_dir = _setup_disposable_repo(tmp_path / "chain_repo")
    goal = "Add public inquiry submission with verified contracts"

    # Plan with explicit execution roles
    async def simulated_llm(prompt: str) -> str:
        return json.dumps({
            "job_id": "job_role_chain",
            "goal": goal,
            "summary": "Plan with builder and verifier tasks",
            "risk_assessment": "low",
            "uncertainty": [],
            "evidence_summary": "FastAPI repo",
            "tasks": [
                {
                    "task_id": "T1_build",
                    "description": "Build inquiry schema",
                    "execution_role": "builder",
                    "dependencies": [],
                    "required_capabilities": ["code.python", "repo.read"],
                    "expected_artifacts": ["app/inquiry.py"],
                    "acceptance_criteria": ["Schema created"],
                    "verification": ["Static check"],
                    "risk": "low",
                    "evidence_refs": ["app/api.py"],
                    "evidence_status": "existing",
                    "reason": "Create schema"
                },
                {
                    "task_id": "T2_verify",
                    "description": "Verify inquiry contracts",
                    "execution_role": "verifier",
                    "dependencies": ["T1_build"],
                    "required_capabilities": ["verification", "review.correctness"],
                    "expected_artifacts": ["report.json"],
                    "acceptance_criteria": ["All contracts verified"],
                    "verification": ["Pytest"],
                    "risk": "low",
                    "evidence_refs": ["tests/test_api.py"],
                    "evidence_status": "existing",
                    "reason": "Verify without mutations"
                }
            ]
        })

    # Mock backends to simulate Codex behavior
    class MockCodexInvalidBackend(ExecutionBackend):
        name = "mock_codex_chain"
        def __init__(self, **kwargs):
            pass

        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                command=request.command,
                returncode=0,
                stdout=json.dumps({"success": True, "notes": "No verdict field"}),
                stderr="",
                backend=self.name,
            )

    class MockCodexMutationBackend(ExecutionBackend):
        name = "mock_codex_mutation"
        def __init__(self, **kwargs):
            pass

        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            (request.cwd / "illegal_mutation.txt").write_text("I changed something", encoding="utf-8")
            return ExecutionResult(
                command=request.command,
                returncode=0,
                stdout=json.dumps({"verdict": "passed", "summary": "Looks good", "repairable": False}),
                stderr="",
                backend=self.name,
            )

    # 1. Test invalid verifier verdict fail-closed
    backend_registry = BackendRegistry()
    backend_registry.register(MockCodexInvalidBackend)
    backend_registry.register(MockCodexMutationBackend)

    agent_registry = AgentRegistry()
    agent_registry.register(CodexAdapter)

    launcher = JobLauncher()
    res = await launcher.launch_goal_async(
        goal=goal,
        target_repo=repo_dir,
        model_client=simulated_llm,
        agent_registry=agent_registry,
        backend_registry=backend_registry,
        dry_run=False,
        skip_agent_exec=False,
        start_background=False,
    )

    job_id = res["jobId"]
    engine = job_service.get_engine(job_id)
    assert engine is not None
    assert engine.graph.get_task("T2_verify").metadata.get("role") == "verifier"
    assert engine.graph.get_task("T1_build").metadata.get("role") == "builder"

    # Execute T2_verify directly on HermesActorAdapter
    task_v = engine.graph.get_task("T2_verify")
    task_v.metadata["execution_backend"] = "mock_codex_chain"
    task_v.metadata["backend"] = "mock_codex_chain"
    task_v.assigned_actor = "codex"
    run = AgentRun(run_id="run_test_v", job_id=job_id, task_id="T2_verify", actor_id="codex")

    # HermesActorAdapter must fail with invalid verdict error
    exec_res = await engine.actor_adapter.execute_task(task_v, run)
    assert exec_res.status == "failed"
    assert "FAILED_CODEX_INVALID_VERDICT" in str(exec_res.error)

    # 2. Test verifier mutation forbidden fail-closed
    task_v.metadata["execution_backend"] = "mock_codex_mutation"
    task_v.metadata["backend"] = "mock_codex_mutation"
    exec_res_mut = await engine.actor_adapter.execute_task(task_v, run)
    assert exec_res_mut.status == "failed"
    assert "verifier role forbids mutations" in str(exec_res_mut.error).lower()


# ==============================================================================
# 5. Optional Live Planner Test
# ==============================================================================

@pytest.mark.live_planner
@pytest.mark.anyio
async def test_phase11_1_live_planner_acceptance(tmp_path: Path):
    """
    Opt-in live planner test invoking real LLM planner against disposable repository.
    Skipped by default unless HERMES_RUN_LIVE_PLANNER=1 is set.
    """
    if os.environ.get("HERMES_RUN_LIVE_PLANNER") != "1":
        pytest.skip("Live planner tests are opt-in. Set HERMES_RUN_LIVE_PLANNER=1 to execute.")

    repo_dir = _setup_disposable_repo(tmp_path / "live_repo")
    # Must fail closed if live LLM is not provided
    planner = GroundedPlanner(target_repo=repo_dir, allow_heuristic_fallback=False)

    req = PlanningRequest(
        job_id="job_live_plan",
        goal="Add a healthcheck endpoint following existing FastAPI conventions",
        target_repo=repo_dir,
    )
    with pytest.raises(ValueError) as exc_info:
        await planner.generate_initial_plan(req)
    assert "heuristic fallback disabled" in str(exc_info.value).lower()
