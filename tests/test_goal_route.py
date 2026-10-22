import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from jobs.job_launcher import JobLauncher
from jobs.job_service import job_service
from orchestrator.chat import ChatReply
from runtime.planning.claude_client import PLANNER_SYSTEM_PROMPT, claude_planner_client


def make_repo(path: Path) -> Path:
    (path / "app").mkdir(parents=True)
    (path / "app" / "api.py").write_text("def route():\n    return 1\n")
    for argv in (["git", "init", "-b", "main"], ["git", "config", "user.name", "T"],
                 ["git", "config", "user.email", "t@example.com"], ["git", "add", "."],
                 ["git", "commit", "-m", "init"]):
        subprocess.run(argv, cwd=path, check=True, capture_output=True)
    return path


def plan_json(goal):
    task = {"dependencies": [], "required_capabilities": ["repo.read", "code.python"], "expected_artifacts": ["x"],
            "acceptance_criteria": ["x"], "verification": ["x"], "risk": "low", "evidence_refs": ["app/api.py"],
            "evidence_status": "existing", "reason": "x"}
    return json.dumps({"goal": goal, "summary": "s", "risk_assessment": "low", "uncertainty": [], "evidence_summary": "e",
                       "tasks": [
                           {**task, "task_id": "build_api", "description": "Build the API", "execution_role": "builder"},
                           {**task, "task_id": "harden_api", "description": "Harden the API", "execution_role": "hardener",
                            "dependencies": ["build_api"]},
                           {**task, "task_id": "verify_api", "description": "Verify the API", "execution_role": "verifier",
                            "dependencies": ["harden_api"], "required_capabilities": ["verification"]},
                       ]})


class FakeProvider:
    def __init__(self):
        self.calls = []

    def reply(self, system_prompt, messages, model, effort):
        self.calls.append((system_prompt, messages, model, effort))
        return ChatReply(text="{}", usage=None)


@pytest.mark.anyio
async def test_planner_client_sends_the_prompt_with_model_and_effort():
    provider = FakeProvider()
    client = claude_planner_client("claude-opus-5-5", "high", provider=provider)
    assert await client("PLAN THIS") == "{}"
    system, messages, model, effort = provider.calls[0]
    assert (system, model, effort) == (PLANNER_SYSTEM_PROMPT, "claude-opus-5-5", "high")
    assert messages == [{"role": "user", "content": "PLAN THIS"}]


def test_planner_client_rejects_unknown_model():
    with pytest.raises(ValueError):
        claude_planner_client("gpt-4", "high")


@pytest.mark.anyio
async def test_engine_job_phases_carry_the_planned_role_not_the_agent(tmp_path):
    repo = make_repo(tmp_path / "repo")
    goal = "Add an API"

    async def model(prompt):
        return plan_json(goal)

    res = await JobLauncher().launch_goal_async(goal=goal, target_repo=repo, model_client=model,
                                                dry_run=True, skip_agent_exec=True, start_background=False)
    phases = {p.id: p for p in job_service.get_job(res["jobId"]).phases}
    assert {k: p.role for k, p in phases.items()} == {"build_api": "builder", "harden_api": "hardener", "verify_api": "verifier"}


def test_goal_route_rejects_a_target_outside_the_projects_root(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "GOAL_REPOS_ROOT", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    outside = make_repo(tmp_path / "elsewhere")
    response = TestClient(main.app).post("/jobs/goal", json={"goal": "x", "targetRepo": str(outside)})
    assert response.status_code == 400
    assert "directly under" in response.json()["detail"]


def test_goal_route_returns_the_job_and_plans_in_the_background(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    make_repo(root / "Repo")
    monkeypatch.setattr(main, "GOAL_REPOS_ROOT", root)
    started = {}

    def fake_background(**kwargs):
        started.update(kwargs)
        return {"jobId": "run_x", "goal": kwargs["goal"], "status": "CREATED", "mode": "goal_planned"}

    monkeypatch.setattr(main.job_launcher, "launch_goal_background", fake_background)
    response = TestClient(main.app).post("/jobs/goal", json={"goal": "Build it", "targetRepo": "Repo", "dryRun": True})
    assert response.status_code == 202
    body = response.json()
    assert body["jobId"] == "run_x" and body["plannerModel"] == "claude-opus-5-5" and body["plannerEffort"] == "high"
    assert started["target_repo"] == (root / "Repo").resolve()
    assert started["allow_heuristic_fallback"] is False and started["dry_run"] is True
