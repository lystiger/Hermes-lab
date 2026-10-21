import json
import subprocess

import pytest

from tools.brief_to_sprint import BriefError, check_target, main, parse_task

BRIEF = """# Active Task

## Assignment

- **Task ID:** UG-001
- **Status:** {status}
- **Project:** Unigreen

## Goal

Execute the governed Hermes vertical slice: **Staff Inquiry Review Workspace**.

## Target

- **Repository:** `lystiger/Unigreen`
- **Pinned baseline:** `{baseline}`

## Bounded Context Files

- `projects/unigreen/architecture.md`
- `operating_system/active_task.md`

## Scope

- Something else
"""

TEMPLATE = {
    "sprint_id": "unigreen-inquiry-v1",
    "name": "template",
    "target_repo": "../../Unigreen",
    "base_ref": "0" * 40,
    "target_branch": "hermes/unigreen-inquiry-v1/integration",
    "worktree_root": "../../hermes-worktrees/unigreen-inquiry-v1",
    "runs_root": "../../hermes-runs",
    "phases": [{"name": "builder", "role": "builder", "agent": "codex"}],
    "verification": [{"name": "pytest", "command": ["pytest"]}],
}


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def clone(tmp_path):
    repo = tmp_path / "clones" / "Unigreen"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
    _git(repo, "remote", "add", "origin", "https://github.com/lystiger/Unigreen.git")
    return repo, _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def lysstack(tmp_path):
    root = tmp_path / "LysStack"
    (root / "operating_system").mkdir(parents=True)
    (root / "projects" / "unigreen").mkdir(parents=True)
    (root / "projects" / "unigreen" / "architecture.md").write_text("arch\n")
    (root / "AGENTS.md").write_text("# AGENTS\n")
    return root


def _write_brief(lysstack, baseline, status="Ready"):
    task = lysstack / "operating_system" / "active_task.md"
    task.write_text(BRIEF.format(baseline=baseline, status=status))
    return task


def test_parse_task_reads_identity_baseline_and_context(lysstack):
    task = parse_task(BRIEF.format(baseline="a" * 40, status="Ready"))

    assert task["task_id"] == "UG-001"
    assert task["status"] == "Ready"
    assert task["repository"] == "lystiger/Unigreen"
    assert task["baseline"] == "a" * 40
    assert task["goal"].startswith("Execute the governed Hermes vertical slice")
    assert task["context_files"] == ["projects/unigreen/architecture.md", "operating_system/active_task.md"]


def test_brief_without_a_pinned_baseline_is_refused():
    with pytest.raises(BriefError, match="Pinned baseline"):
        parse_task(BRIEF.replace("- **Pinned baseline:**", "- **Other:**").format(baseline="x", status="Ready"))


def test_generates_a_spec_pinned_to_the_brief_baseline(clone, lysstack, tmp_path):
    repo, head = clone
    task = _write_brief(lysstack, head)
    template = tmp_path / "template.json"
    template.write_text(json.dumps(TEMPLATE))
    out = tmp_path / "sprints" / "ug-001.json"
    out.parent.mkdir()

    assert main(["--task", str(task), "--template", str(template), "--target-repo", str(repo), "--out", str(out)]) == 0

    spec = json.loads(out.read_text())
    assert spec["sprint_id"] == "ug-001"
    assert spec["base_ref"] == head
    assert spec["target_branch"] == "hermes/ug-001/integration"
    assert spec["worktree_root"] == "../../hermes-worktrees/ug-001"
    assert spec["phases"] == TEMPLATE["phases"]
    assert spec["verification"] == TEMPLATE["verification"]
    assert spec["context"]["files"] == ["AGENTS.md", "projects/unigreen/architecture.md", "operating_system/active_task.md"]
    assert (out.parent / spec["context"]["root"] / "AGENTS.md").is_file()
    assert (out.parent / spec["context"]["root"] / "operating_system" / "active_task.md").is_file()
    assert (out.parent / spec["target_repo"]).resolve() == repo.resolve()


def test_a_task_that_is_not_ready_is_refused(clone, lysstack, tmp_path):
    repo, head = clone
    task = _write_brief(lysstack, head, status="Blocked")
    template = tmp_path / "template.json"
    template.write_text(json.dumps(TEMPLATE))

    with pytest.raises(BriefError, match="only 'Ready'"):
        main(["--task", str(task), "--template", str(template), "--target-repo", str(repo), "--out", str(tmp_path / "x.json")])


def test_a_baseline_missing_from_the_clone_is_refused(clone, lysstack):
    repo, _ = clone
    with pytest.raises(BriefError, match="is not in"):
        check_target(repo, "lystiger/Unigreen", "f" * 40)


def test_a_clone_of_another_repository_is_refused(clone):
    repo, head = clone
    _git(repo, "remote", "set-url", "origin", "https://github.com/lystiger/SomethingElse.git")
    with pytest.raises(BriefError, match="brief expects"):
        check_target(repo, "lystiger/Unigreen", head)


def test_a_missing_context_file_is_refused(clone, lysstack, tmp_path):
    repo, head = clone
    task = _write_brief(lysstack, head)
    (lysstack / "projects" / "unigreen" / "architecture.md").unlink()
    template = tmp_path / "template.json"
    template.write_text(json.dumps(TEMPLATE))

    with pytest.raises(BriefError, match="Context files missing"):
        main(["--task", str(task), "--template", str(template), "--target-repo", str(repo), "--out", str(tmp_path / "x.json")])
