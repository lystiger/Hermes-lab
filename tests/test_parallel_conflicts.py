"""Two parallel tasks that change the same lines: the second merge conflicts."""
import subprocess

import pytest

from runtime.hermes_adapter import HermesActorAdapter, MergeConflictError
from runtime.task_graph import TaskNode
from tests.test_goal_route import make_repo


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def job(tmp_path):
    repo = make_repo(tmp_path / "repo")
    adapter = HermesActorAdapter(target_repo=repo, worktree_root=tmp_path / "wt", run_dir=tmp_path / "run",
                                 job_id="j", base_ref="main", target_branch="job/j/integration")
    adapter.ensure_integration_worktree()

    def task_worktree(task_id):
        # Both start from the same integration HEAD, as parallel tasks do.
        path = adapter._ensure_worktree(tmp_path / "wt" / task_id, branch=f"task/j/{task_id}",
                                        base_branch="job/j/integration")
        adapter.sync_task_worktree_from_integration(path)
        return path

    yield adapter, task_worktree
    for path in (tmp_path / "wt").iterdir():
        subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, capture_output=True)


def node(task_id):
    return TaskNode(task_id=task_id, job_id="j", description=f"task {task_id}")


def test_a_conflicting_merge_fails_the_task_and_leaves_integration_clean(job):
    adapter, task_worktree = job
    a, b = task_worktree("a"), task_worktree("b")
    (a / "app" / "api.py").write_text("def route():\n    return 'a'\n")
    (b / "app" / "api.py").write_text("def route():\n    return 'b'\n")
    adapter._commit_and_integrate_changes(a, node("a"), role="builder")

    with pytest.raises(MergeConflictError) as err:
        adapter._commit_and_integrate_changes(b, node("b"), role="builder")

    assert "app/api.py" in str(err.value) and err.value.files == ["app/api.py"]
    integration = adapter.worktree_root / "integration"
    assert git(integration, "status", "--porcelain") == ""
    assert (integration / "app" / "api.py").read_text() == "def route():\n    return 'a'\n"


def test_later_tasks_still_merge_after_a_conflict(job):
    adapter, task_worktree = job
    a, b, c = task_worktree("a"), task_worktree("b"), task_worktree("c")
    (a / "app" / "api.py").write_text("def route():\n    return 'a'\n")
    (b / "app" / "api.py").write_text("def route():\n    return 'b'\n")
    (c / "app" / "other.py").write_text("x = 1\n")
    adapter._commit_and_integrate_changes(a, node("a"), role="builder")
    with pytest.raises(MergeConflictError):
        adapter._commit_and_integrate_changes(b, node("b"), role="builder")

    adapter._commit_and_integrate_changes(c, node("c"), role="builder")

    assert (adapter.worktree_root / "integration" / "app" / "other.py").exists()


def test_the_retry_starts_from_the_other_tasks_work(job):
    adapter, task_worktree = job
    a, b = task_worktree("a"), task_worktree("b")
    (a / "app" / "api.py").write_text("def route():\n    return 'a'\n")
    (b / "app" / "api.py").write_text("def route():\n    return 'b'\n")
    adapter._commit_and_integrate_changes(a, node("a"), role="builder")
    with pytest.raises(MergeConflictError):
        adapter._commit_and_integrate_changes(b, node("b"), role="builder")

    retry = task_worktree("b")
    assert (retry / "app" / "api.py").read_text() == "def route():\n    return 'a'\n"
    (retry / "app" / "api.py").write_text("def route():\n    return 'a' + 'b'\n")
    adapter._commit_and_integrate_changes(retry, node("b"), role="builder")
    assert "'a' + 'b'" in (adapter.worktree_root / "integration" / "app" / "api.py").read_text()
