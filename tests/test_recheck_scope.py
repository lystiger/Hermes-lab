"""Tests for Change 4: Recheck task description and prompt scope.

Change 4 specification:
1. In runtime/engine.py _repair_failed_verdict:
   The recheck task description says:
   - confirm each earlier finding is resolved,
   - and review the changes made by the repair task,
   - without re-reviewing anything the repair did not change.
2. In runtime/hermes_adapter.py (_prepare_effective_prompt):
   The recheck prompt includes the repair task's diff:
   - changed files and their diff from the repair commit,
   - capped at 400 lines,
   - with a visible note when the diff is cut.
"""

import re
import subprocess
from pathlib import Path
from typing import Optional

import pytest

from runtime.engine import ReactiveJobEngine
from runtime.events import RuntimeEventBridge
from runtime.execution import TaskExecutionResult
from runtime.hermes_adapter import HermesActorAdapter
from runtime.limits import RuntimeLimits
from runtime.storage.in_memory_store import InMemoryRuntimeEventStore
from runtime.task_graph import TaskNode, TaskStatus


class OptInPlanner:
    repairs_failed_verdicts = True

    async def plan(self, request):
        raise AssertionError("not used")


def _make_engine(role: str = "verifier"):
    engine = ReactiveJobEngine(
        job_id=f"job_recheck_{role}",
        goal=f"Test recheck scope for {role}",
        planner=OptInPlanner(),
        limits=RuntimeLimits(max_repairs_per_job=3),
        event_bridge=RuntimeEventBridge(event_store=InMemoryRuntimeEventStore()),
    )
    engine.graph.add_task(
        TaskNode(
            task_id="build",
            job_id=f"job_recheck_{role}",
            description="build components",
            status=TaskStatus.SUCCEEDED,
            metadata={"role": "builder"},
        )
    )
    check_task = engine.graph.add_task(
        TaskNode(
            task_id=f"check_{role}",
            job_id=f"job_recheck_{role}",
            description="Verify widget accessibility across the app",
            dependencies=["build"],
            required_capabilities=["verification"],
            assigned_actor="codex",
            metadata={"role": role},
        )
    )
    return engine, check_task


def _failed_verdict(findings=None, summary="tests failed"):
    if findings is None:
        findings = ["button-1 missing aria-label", "button-2 missing aria-label"]
    return TaskExecutionResult(
        status="failed",
        error=summary,
        metadata={
            "verdict": "failed",
            "verification_summary": summary,
            "findings": findings,
            "repairable": True,
        },
    )


def _create_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    for argv in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "Hermes Tester"],
        ["git", "config", "user.email", "tester@example.com"],
        ["git", "add", "."],
        ["git", "commit", "-m", "init"],
    ):
        subprocess.run(argv, cwd=path, check=True, capture_output=True)
    return path


def _commit_file(repo: Path, filepath: str, content: str, message: str) -> str:
    target = repo / filepath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", filepath], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True)
    return res.stdout.strip()


def _extract_repair_diff_section(prompt: str) -> str:
    """Finds the repair task diff section in the recheck prompt.

    Looks for a section bounded by '--- ...REPAIR... ---' or a section mentioning
    repair changes / repair diff.
    """
    lines = prompt.splitlines()
    in_section = False
    section_lines = []

    for line in lines:
        stripped = line.strip()
        if not in_section:
            if stripped.startswith("---") and not stripped.startswith("--- END"):
                header_lower = stripped.lower()
                if "repair" in header_lower and any(w in header_lower for w in ("diff", "change", "what")):
                    in_section = True
                    section_lines.append(line)
        else:
            section_lines.append(line)
            if stripped.startswith("--- END") or (stripped.startswith("---") and "end" in stripped.lower()):
                break

    if section_lines:
        return "\n".join(section_lines)

    match = re.search(
        r"---[^\n]*repair[^\n]*(?:diff|change|what)[^\n]*---.*?(?:--- END[^\n]*---|\Z)",
        prompt,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(0)
    return ""


@pytest.mark.parametrize("role", ["verifier", "security"])
@pytest.mark.anyio
async def test_recheck_task_description_says_confirm_earlier_findings_and_review_repair_changes(role: str):
    """The recheck task description created in _repair_failed_verdict must say:
    - confirm each earlier finding is resolved,
    - and review the changes made by the repair task,
    - without re-reviewing anything the repair did not change.
    """
    engine, check_task = _make_engine(role=role)
    findings = ["button-1 missing aria-label", "button-2 missing aria-label"]
    handled = await engine._repair_failed_verdict(check_task, _failed_verdict(findings=findings))
    assert handled is True

    recheck_task = engine.graph.get_task(f"recheck_check_{role}_1")
    assert recheck_task is not None

    desc = recheck_task.description.lower()

    assert "confirm each earlier finding is resolved" in desc, (
        f"Recheck description must say 'confirm each earlier finding is resolved'.\n"
        f"Got:\n{recheck_task.description}"
    )
    assert "review the changes made by the repair task" in desc, (
        f"Recheck description must say 'review the changes made by the repair task'.\n"
        f"Got:\n{recheck_task.description}"
    )
    assert "without re-reviewing anything the repair did not change" in desc, (
        f"Recheck description must say 'without re-reviewing anything the repair did not change'.\n"
        f"Got:\n{recheck_task.description}"
    )


@pytest.mark.anyio
async def test_recheck_task_description_scope_in_subsequent_cycle():
    """Subsequent recheck cycles (e.g. cycle 2) must also include the scope instructions."""
    engine, check_task = _make_engine(role="verifier")
    await engine._repair_failed_verdict(check_task, _failed_verdict(["defect 1"]))

    recheck_1 = engine.graph.get_task("recheck_check_verifier_1")
    assert recheck_1 is not None

    handled = await engine._repair_failed_verdict(recheck_1, _failed_verdict(["defect 2"]))
    assert handled is True

    recheck_2 = engine.graph.get_task("recheck_check_verifier_2")
    assert recheck_2 is not None

    desc = recheck_2.description.lower()

    assert "confirm each earlier finding is resolved" in desc, (
        f"Recheck description in cycle 2 must say 'confirm each earlier finding is resolved'.\n"
        f"Got:\n{recheck_2.description}"
    )
    assert "review the changes made by the repair task" in desc, (
        f"Recheck description in cycle 2 must say 'review the changes made by the repair task'.\n"
        f"Got:\n{recheck_2.description}"
    )
    assert "without re-reviewing anything the repair did not change" in desc, (
        f"Recheck description in cycle 2 must say 'without re-reviewing anything the repair did not change'.\n"
        f"Got:\n{recheck_2.description}"
    )


def test_recheck_prompt_includes_repair_diff_and_changed_files(tmp_path):
    """The recheck prompt must include the repair task's diff (changed files and diff from repair commit)."""
    repo = _create_git_repo(tmp_path / "repo")
    repair_content = (
        "def fix_button():\n"
        "    return '<button aria-label=\"submit\">OK</button>'\n"
    )
    repair_sha = _commit_file(repo, "app/widget.py", repair_content, "fix: repair widget aria-label")

    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "wt",
        run_dir=tmp_path / "run",
        base_ref="main",
    )

    repair_task = TaskNode(
        task_id="repair_check_verifier_1",
        job_id="job_recheck",
        description="Fix the findings",
        status=TaskStatus.SUCCEEDED,
        metadata={"role": "builder", "commit_sha": repair_sha},
    )
    recheck_task = TaskNode(
        task_id="recheck_check_verifier_1",
        job_id="job_recheck",
        description="Verify widget accessibility after repair",
        dependencies=[repair_task.task_id],
        metadata={
            "role": "verifier",
            "repair_root": "check_verifier",
            "repair_task_id": repair_task.task_id,
            "repair_commit": repair_sha,
            "prior_findings": ["button-1 missing aria-label"],
        },
    )

    prompt = adapter._prepare_effective_prompt(
        task=recheck_task,
        actor_id="codex",
        role="verifier",
        worktree_path=repo,
        context={"engine": None, "job": {"goal": "test"}},
        tasks=[repair_task, recheck_task],
    )

    repair_section = _extract_repair_diff_section(prompt)
    assert repair_section, (
        f"Recheck prompt must include a section for the repair task's diff.\nGot prompt:\n{prompt}"
    )
    assert "app/widget.py" in repair_section, (
        f"Repair diff section must list changed file 'app/widget.py'.\nGot section:\n{repair_section}"
    )
    assert "fix_button" in repair_section or 'aria-label="submit"' in repair_section, (
        f"Repair diff section must include diff content from the repair commit.\nGot section:\n{repair_section}"
    )
    assert not any(cut_word in repair_section.lower() for cut_word in ("diff cut", "cut at 400")), (
        f"Repair diff under 400 lines must not include a diff cut note.\nGot section:\n{repair_section}"
    )


def test_recheck_prompt_repair_diff_capped_at_400_lines(tmp_path):
    """The repair diff in the recheck prompt must be capped at 400 lines, with a visible note when cut."""
    repo = _create_git_repo(tmp_path / "repo")
    diff_lines = [f"LINE_{i:03d} = 'payload_{i}'" for i in range(1, 451)]
    large_content = "\n".join(diff_lines) + "\n"
    repair_sha = _commit_file(repo, "app/large.py", large_content, "fix: large repair changes")

    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "wt",
        run_dir=tmp_path / "run",
        base_ref="main",
    )

    repair_task = TaskNode(
        task_id="repair_check_verifier_1",
        job_id="job_recheck",
        description="Fix the findings",
        status=TaskStatus.SUCCEEDED,
        metadata={"role": "builder", "commit_sha": repair_sha},
    )
    recheck_task = TaskNode(
        task_id="recheck_check_verifier_1",
        job_id="job_recheck",
        description="Verify large component after repair",
        dependencies=[repair_task.task_id],
        metadata={
            "role": "verifier",
            "repair_root": "check_verifier",
            "repair_task_id": repair_task.task_id,
            "repair_commit": repair_sha,
            "prior_findings": ["large component broken"],
        },
    )

    prompt = adapter._prepare_effective_prompt(
        task=recheck_task,
        actor_id="codex",
        role="verifier",
        worktree_path=repo,
        context={"engine": None, "job": {"goal": "test"}},
        tasks=[repair_task, recheck_task],
    )

    repair_section = _extract_repair_diff_section(prompt)
    assert repair_section, (
        f"Recheck prompt must include a section for the repair task's diff.\nGot prompt:\n{prompt}"
    )
    assert any(cut_word in repair_section.lower() for cut_word in ("cut", "truncated", "capped")), (
        f"Repair diff exceeding 400 lines must have a visible note when cut.\nGot section:\n{repair_section}"
    )
    assert "LINE_010" in repair_section, (
        f"Lines within the 400-line cap (LINE_010) must be included in repair diff.\nGot section:\n{repair_section}"
    )
    assert "LINE_440" not in repair_section, (
        f"Lines beyond the 400-line cap (LINE_440) must be excluded from repair diff.\nGot section:\n{repair_section}"
    )


def test_recheck_prompt_repair_diff_scoped_to_repair_commit_only(tmp_path):
    """The repair diff section must include only changes from the repair commit, not earlier tasks."""
    repo = _create_git_repo(tmp_path / "repo")
    _commit_file(repo, "app/prior_feature.py", "def prior(): pass\n", "feat: prior builder task")
    repair_sha = _commit_file(repo, "app/repair_fix.py", "def repair(): return True\n", "fix: repair task commit")

    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "wt",
        run_dir=tmp_path / "run",
        base_ref="main",
    )

    repair_task = TaskNode(
        task_id="repair_check_verifier_1",
        job_id="job_recheck",
        description="Fix the findings",
        status=TaskStatus.SUCCEEDED,
        metadata={"role": "builder", "commit_sha": repair_sha},
    )
    recheck_task = TaskNode(
        task_id="recheck_check_verifier_1",
        job_id="job_recheck",
        description="Verify repair fix",
        dependencies=[repair_task.task_id],
        metadata={
            "role": "verifier",
            "repair_root": "check_verifier",
            "repair_task_id": repair_task.task_id,
            "repair_commit": repair_sha,
            "prior_findings": ["prior repair needed"],
        },
    )

    prompt = adapter._prepare_effective_prompt(
        task=recheck_task,
        actor_id="codex",
        role="verifier",
        worktree_path=repo,
        context={"engine": None, "job": {"goal": "test"}},
        tasks=[repair_task, recheck_task],
    )

    repair_section = _extract_repair_diff_section(prompt)
    assert repair_section, (
        f"Recheck prompt must include a section for the repair task's diff.\nGot prompt:\n{prompt}"
    )
    assert "app/repair_fix.py" in repair_section, (
        f"Repair diff section must include changed file 'app/repair_fix.py'.\nGot section:\n{repair_section}"
    )
    assert "app/prior_feature.py" not in repair_section, (
        f"Repair diff section must NOT include files from prior tasks ('app/prior_feature.py').\n"
        f"Got section:\n{repair_section}"
    )


def test_non_recheck_verifier_prompt_has_no_repair_diff(tmp_path):
    """An initial verifier task prompt (not a recheck) must not include a repair diff section."""
    repo = _create_git_repo(tmp_path / "repo")
    adapter = HermesActorAdapter(
        target_repo=repo,
        worktree_root=tmp_path / "wt",
        run_dir=tmp_path / "run",
        base_ref="main",
    )
    initial_check_task = TaskNode(
        task_id="check_verifier",
        job_id="job_initial",
        description="Verify initial deliverable",
        dependencies=[],
        metadata={"role": "verifier"},
    )
    prompt = adapter._prepare_effective_prompt(
        task=initial_check_task,
        actor_id="codex",
        role="verifier",
        worktree_path=repo,
    )
    repair_section = _extract_repair_diff_section(prompt)
    assert not repair_section, (
        f"Initial verifier task prompt must not contain a repair diff section.\nGot section:\n{repair_section}"
    )
