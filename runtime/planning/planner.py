import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from runtime.task_graph import TaskNode
from runtime.limits import RuntimeLimits
from runtime.replanning import (
    PlannerAdapter,
    ProductionPlannerAdapter,
    ReplanRequest,
    ReplanResult,
    ReplanReason,
    GraphMutation,
    GraphMutationType,
)
from runtime.planning.contracts import PlannedTask, StructuredPlan, PlanningRequest
from runtime.planning.reconnaissance import RepositoryEvidence, RepositoryReconnaissance
from runtime.planning.validator import PlanValidator, PlanValidationResult

logger = logging.getLogger("hermes.runtime.planning")


PLAN_JSON_SCHEMA_PROMPT = """
Your output MUST be a single valid JSON object with this exact structure:

{
  "job_id": "<job_id>",
  "goal": "<goal>",
  "summary": "<high-level summary of the planned engineering steps>",
  "risk_assessment": "low" | "medium" | "high",
  "uncertainty": ["<uncertainty item 1>", "..."],
  "evidence_summary": "<summary of repository evidence used>",
  "tasks": [
    {
      "task_id": "<unique_task_id>",
      "description": "<detailed action description>",
      "dependencies": ["<dep_task_id>"],
      "required_capabilities": ["backend.python", "testing.unit", ...],
      "expected_artifacts": ["<artifact 1>", "..."],
      "acceptance_criteria": ["<criterion 1>", "..."],
      "verification": ["<verification step 1>", "..."],
      "risk": "low" | "medium" | "high",
      "evidence_refs": ["<path/in/repo.py>"],
      "evidence_status": "existing" | "new_component",
      "reason": "<rationale grounded in repository evidence>"
    }
  ]
}

Rules:
1. Do not hardcode specific agent names (e.g. Antigravity, Claude, Codex) in required_capabilities; use open capability descriptors (e.g. 'backend.python', 'api.rest', 'testing.unit', 'verification').
2. Every implementation task must reference existing repository files in evidence_refs OR declare evidence_status='new_component'.
3. Dependencies must form a valid directed acyclic graph (DAG) without circular references.
4. The plan must contain a terminal verification or test strategy.
"""


class GroundedPlanner(PlannerAdapter):
    """
    Repository-grounded goal-to-graph initial planner.
    Performs static reconnaissance over the target repository, synthesizes evidence,
    and produces a validated, structured TaskGraph DAG before execution.
    """

    def __init__(
        self,
        model_client: Optional[Callable] = None,
        reconnaissance: Optional[RepositoryReconnaissance] = None,
        validator: Optional[PlanValidator] = None,
        limits: Optional[RuntimeLimits] = None,
        target_repo: Optional[Path] = None,
        event_bridge: Any = None,
    ):
        self.model_client = model_client
        self.reconnaissance = reconnaissance or RepositoryReconnaissance()
        self.validator = validator or PlanValidator()
        self.limits = limits or RuntimeLimits()
        self.target_repo = target_repo
        self.event_bridge = event_bridge
        self._replanner_delegate = ProductionPlannerAdapter(limits=self.limits)

    async def generate_initial_plan(self, request: PlanningRequest) -> StructuredPlan:
        """
        Generates and validates a structured plan from a goal and repository evidence.
        """
        repo_dir = request.target_repo or self.target_repo or Path.cwd()

        # 1. Emit planning.started event
        if self.event_bridge and hasattr(self.event_bridge, "emit_planning_started"):
            try:
                await self.event_bridge.emit_planning_started(
                    job_id=request.job_id,
                    goal=request.goal,
                    constraints=request.constraints,
                    repo_dir=str(repo_dir),
                )
            except Exception as e:
                logger.debug("Failed emitting planning.started: %s", e)

        # 2. Gather repository evidence
        evidence = request.evidence
        if evidence is None:
            evidence = self.reconnaissance.collect(
                repo_dir=repo_dir,
                goal=request.goal,
                constraints=request.constraints,
                limits=self.limits,
            )
            request.evidence = evidence

        # Emit repository.evidence_collected event
        if self.event_bridge and hasattr(self.event_bridge, "emit_repository_evidence_collected"):
            try:
                await self.event_bridge.emit_repository_evidence_collected(
                    job_id=request.job_id,
                    file_count=len(evidence.files),
                    summary=evidence.summary,
                    uncertainty=evidence.uncertainty,
                )
            except Exception as e:
                logger.debug("Failed emitting repository.evidence_collected: %s", e)

        # 3. Generate plan
        raw_plan_dict = None
        if self.model_client:
            prompt = self._build_planning_prompt(request, evidence)
            import inspect
            if inspect.iscoroutinefunction(self.model_client):
                raw_response = await self.model_client(prompt)
            else:
                raw_response = self.model_client(prompt)

            raw_plan_dict = self._parse_json_response(raw_response)
        else:
            # Deterministic heuristic plan generation grounded in evidence
            raw_plan_dict = self._generate_heuristic_grounded_plan(request, evidence)

        if not raw_plan_dict or not isinstance(raw_plan_dict, dict):
            err_msg = "Planner output could not be parsed as structured JSON"
            if self.event_bridge and hasattr(self.event_bridge, "emit_planning_failed"):
                try:
                    await self.event_bridge.emit_planning_failed(job_id=request.job_id, error=err_msg, reasons=[err_msg])
                except Exception:
                    pass
            raise ValueError(err_msg)

        plan = StructuredPlan.from_dict(raw_plan_dict)
        plan.job_id = request.job_id
        plan.goal = request.goal

        # 4. Deterministic validation
        val_res: PlanValidationResult = self.validator.validate(
            plan=plan,
            repo_dir=repo_dir,
            available_capabilities=request.available_capabilities,
            limits=self.limits,
        )

        if not val_res.is_valid:
            logger.warning("Plan validation failed for job %s: %s", request.job_id, val_res.errors)
            if self.event_bridge and hasattr(self.event_bridge, "emit_planning_failed"):
                try:
                    await self.event_bridge.emit_planning_failed(
                        job_id=request.job_id,
                        error="Plan validation failed",
                        reasons=val_res.errors,
                    )
                except Exception:
                    pass
            raise ValueError(f"Plan validation failed: {'; '.join(val_res.errors)}")

        # 5. Emit planning.generated and planning.validated
        if self.event_bridge:
            if hasattr(self.event_bridge, "emit_planning_generated"):
                try:
                    await self.event_bridge.emit_planning_generated(
                        job_id=request.job_id,
                        task_count=len(plan.tasks),
                        summary=plan.summary,
                        plan_dict=plan.to_dict(),
                    )
                except Exception as e:
                    logger.debug("Failed emitting planning.generated: %s", e)

            if hasattr(self.event_bridge, "emit_planning_validated"):
                try:
                    await self.event_bridge.emit_planning_validated(
                        job_id=request.job_id,
                        task_count=len(plan.tasks),
                        valid=True,
                    )
                except Exception as e:
                    logger.debug("Failed emitting planning.validated: %s", e)

        return plan

    async def plan(self, request: ReplanRequest) -> ReplanResult:
        """
        Unified planner interface: handles initial planning or delegates replanning.
        """
        reason_str = str(request.reason.value if hasattr(request.reason, "value") else request.reason).lower()

        if reason_str == "initial_plan":
            repo_dir = getattr(request, "target_repo", None) or self.target_repo or Path.cwd()
            constraints = getattr(request, "constraints", [])
            avail_caps = getattr(request, "available_capabilities", [])

            plan_req = PlanningRequest(
                job_id=request.job_id,
                goal=request.goal,
                target_repo=repo_dir,
                constraints=constraints,
                available_capabilities=avail_caps,
                limits=self.limits,
            )

            try:
                structured_plan = await self.generate_initial_plan(plan_req)
                mutations = []
                for pt in structured_plan.tasks:
                    node = pt.to_task_node(job_id=request.job_id, max_attempts=self.limits.max_task_attempts)
                    mutations.append(
                        GraphMutation(
                            mutation_type=GraphMutationType.ADD_TASK,
                            task=node,
                            reason=pt.reason or f"Planned initial task for goal: {request.goal[:60]}",
                        )
                    )
                return ReplanResult(
                    mutations=mutations,
                    explanation=structured_plan.summary or "Initial repository-grounded plan generated successfully",
                    should_continue=True,
                )
            except Exception as e:
                logger.exception("Initial planning error for job %s: %s", request.job_id, e)
                return ReplanResult(
                    mutations=[],
                    explanation=f"Initial planning failed: {str(e)}",
                    should_continue=False,
                )

        # Non-initial replan -> delegate to ProductionPlannerAdapter
        return await self._replanner_delegate.plan(request)

    def _build_planning_prompt(self, request: PlanningRequest, evidence: RepositoryEvidence) -> str:
        prompt_parts = [
            f"# ENGINEERING GOAL\n{request.goal}\n",
        ]
        if request.constraints:
            prompt_parts.append("# CONSTRAINTS\n" + "\n".join(f"- {c}" for c in request.constraints) + "\n")

        prompt_parts.append("# REPOSITORY RECONNAISSANCE EVIDENCE\n" + evidence.render_for_prompt() + "\n")
        prompt_parts.append("# STRUCTURED PLAN OUTPUT CONTRACT\n" + PLAN_JSON_SCHEMA_PROMPT)
        return "\n\n".join(prompt_parts)

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        cleaned = text.strip() if isinstance(text, str) else ""
        if not cleaned:
            return None

        # 1. Direct JSON
        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                return json.loads(cleaned)
            except Exception:
                pass

        # 2. Markdown code block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        return None

    def _generate_heuristic_grounded_plan(self, request: PlanningRequest, evidence: RepositoryEvidence) -> Dict[str, Any]:
        """
        Deterministic, grounded initial plan generator when external LLM is not provided.
        Synthesizes a 4-step decomposition referencing actual evidence files.
        """
        top_files = [f.path for f in evidence.files[:3]]
        test_files = [t for t in evidence.tests[:2]]

        primary_ref = top_files[0] if top_files else "app.py"
        test_ref = test_files[0] if test_files else "tests/test_app.py"
        status = "existing" if evidence.files else "new_component"

        tasks = [
            {
                "task_id": "T1_inspect_conventions",
                "description": f"Inspect existing architecture and contracts for: {request.goal}",
                "dependencies": [],
                "required_capabilities": ["repo.read", "code.python"],
                "expected_artifacts": ["architecture_notes"],
                "acceptance_criteria": ["Identified relevant module contracts and schemas"],
                "verification": ["Static inspection of module exports"],
                "risk": "low",
                "evidence_refs": top_files if top_files else [primary_ref],
                "evidence_status": status,
                "reason": f"Analyze existing patterns in {', '.join(top_files) if top_files else primary_ref} before mutation.",
            },
            {
                "task_id": "T2_implement_feature",
                "description": f"Implement core feature logic for: {request.goal}",
                "dependencies": ["T1_inspect_conventions"],
                "required_capabilities": ["implementation", "code.python"],
                "expected_artifacts": ["feature_implementation"],
                "acceptance_criteria": [f"Feature {request.goal} implemented conforming to repository conventions"],
                "verification": ["Syntax check and unit test execution"],
                "risk": "medium",
                "evidence_refs": [primary_ref],
                "evidence_status": status,
                "reason": f"Grounded implementation extending {primary_ref}.",
            },
            {
                "task_id": "T3_add_tests",
                "description": f"Add targeted unit tests and edge cases for: {request.goal}",
                "dependencies": ["T2_implement_feature"],
                "required_capabilities": ["testing.unit", "code.python"],
                "expected_artifacts": ["unit_tests"],
                "acceptance_criteria": ["New tests assert expected behavior and error handling"],
                "verification": ["Run pytest suite"],
                "risk": "low",
                "evidence_refs": [test_ref],
                "evidence_status": "existing" if test_files else "new_component",
                "reason": f"Extend test coverage in {test_ref}.",
            },
            {
                "task_id": "T4_verify_integration",
                "description": f"Verify integration and regression freedom for: {request.goal}",
                "dependencies": ["T3_add_tests"],
                "required_capabilities": ["verification", "review.correctness"],
                "expected_artifacts": ["verification_report"],
                "acceptance_criteria": ["All unit tests pass and no regression introduced"],
                "verification": ["Pytest test execution and contract check"],
                "risk": "low",
                "evidence_refs": [primary_ref, test_ref],
                "evidence_status": status,
                "reason": "Final independent verification of feature and test suite.",
            },
        ]

        return {
            "job_id": request.job_id,
            "goal": request.goal,
            "summary": f"Repository-grounded plan for '{request.goal}' with inspection, implementation, testing, and verification.",
            "risk_assessment": "medium",
            "uncertainty": evidence.uncertainty,
            "evidence_summary": evidence.summary,
            "tasks": tasks,
        }
