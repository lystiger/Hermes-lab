import subprocess
from pathlib import Path
from types import SimpleNamespace

from jobs.job_finalizer import finalize_completed_job, prune_merged_job_branches
from runtime.task_graph import TaskGraph, TaskNode, TaskStatus


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(tmp_path):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.name", "T"], ["config", "user.email", "t@x"],
                 ["remote", "add", "origin", str(origin)]):
        git(repo, *args)
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "init")
    git(repo, "push", "-q", "origin", "main")
    return repo


def fake_engine(job_id):
    graph = TaskGraph(job_id=job_id)
    graph.add_task(TaskNode(task_id="build", job_id=job_id, assigned_actor="claude", status=TaskStatus.SUCCEEDED,
                            metadata={"role": "builder"}))
    graph.add_task(TaskNode(task_id="verify", job_id=job_id, assigned_actor="codex", status=TaskStatus.SUCCEEDED,
                            metadata={"role": "verifier", "verification_summary": "all checks pass", "findings": []}))
    job = SimpleNamespace(job_id=job_id, goal="Add a tooltip", branch=f"job/{job_id}/integration", repair_count=1)
    return SimpleNamespace(job=job, graph=graph)


def test_a_completed_job_is_recorded_and_its_worktrees_cleaned(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_AUTO_PR", "0")
    repo, job = make_repo(tmp_path), "run_1"
    wt_root = tmp_path / "worktrees" / job
    git(repo, "worktree", "add", "-q", "-b", f"job/{job}/integration", str(wt_root / "integration"))
    git(repo, "worktree", "add", "-q", "-b", f"task/{job}/build", str(wt_root / "build"))
    lysstack = tmp_path / "LysStack"
    (lysstack / "operating_system").mkdir(parents=True)
    run_dir = tmp_path / "runs" / job
    run_dir.mkdir(parents=True)

    result = finalize_completed_job(fake_engine(job), repo, wt_root, run_dir, lysstack_root=lysstack)

    assert result["worktreesRemoved"] == 2 and not wt_root.exists()
    branches = git(repo, "branch", "--format=%(refname:short)").split()
    assert f"job/{job}/integration" in branches and f"task/{job}/build" not in branches
    log = (lysstack / "operating_system" / "run-log.md").read_text()
    assert f"## {job}" in log and "after 1 repair cycle(s)" in log and "build (builder, claude)" in log
    assert (run_dir / "finalize.json").exists()


def test_integration_branches_already_in_main_are_pruned_locally_and_on_origin(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-qb", "job/run_2/integration")
    (repo / "b.txt").write_text("b\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "work")
    git(repo, "push", "-q", "origin", "job/run_2/integration")
    git(repo, "checkout", "-q", "main")
    git(repo, "branch", "-q", "job/run_3/integration")  # nothing new, but also in main
    git(repo, "checkout", "-qb", "job/run_4/integration")
    (repo / "c.txt").write_text("c\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "unmerged")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge run_2", "job/run_2/integration")
    git(repo, "push", "-q", "origin", "main")

    pruned = prune_merged_job_branches(repo)

    assert sorted(pruned) == ["job/run_2/integration", "job/run_3/integration"]
    assert git(repo, "branch", "--list", "job/*").split() == ["job/run_4/integration"]
    assert "job/run_2/integration" not in git(repo, "ls-remote", "--heads", "origin")


def test_a_dry_run_is_only_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_AUTO_PR", "1")
    repo, job = make_repo(tmp_path), "run_dry"
    wt_root = tmp_path / "worktrees" / job
    git(repo, "worktree", "add", "-q", "-b", f"job/{job}/integration", str(wt_root / "integration"))
    lysstack = tmp_path / "LysStack"
    (lysstack / "operating_system").mkdir(parents=True)
    run_dir = tmp_path / "runs" / job  # a dry run never creates its run dir
    result = finalize_completed_job(fake_engine(job), repo, wt_root, run_dir, lysstack_root=lysstack, review=False)
    assert (run_dir / "finalize.json").exists()
    assert result["prUrl"] is None and result["runLog"] is None and result["worktreesRemoved"] == 1
    assert not (lysstack / "operating_system" / "run-log.md").exists()
    assert "job/run_dry/integration" not in git(repo, "ls-remote", "--heads", "origin")


def test_finalized_jobs_are_listed_for_review_and_dry_runs_are_not(tmp_path, monkeypatch):
    from jobs.job_finalizer import list_reviews

    monkeypatch.setenv("HERMES_AUTO_PR", "0")
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    for job, review in (("run_real", True), ("run_dry", False)):
        finalize_completed_job(fake_engine(job), repo, tmp_path / "wt" / job, runs / job,
                               lysstack_root=tmp_path / "nowhere", review=review)
    [item] = list_reviews(runs)
    assert item["jobId"] == "run_real" and item["goal"] == "Add a tooltip" and item["repairs"] == 1
    assert item["verdict"]["summary"] == "all checks pass" and item["prUrl"] is None
    assert [t["id"] for t in item["tasks"]] == ["build", "verify"]
