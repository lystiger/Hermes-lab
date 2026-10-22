"""Closes the loop for a completed goal-planned job.

1. Push the job's integration branch and open a pull request against main for human review
   (HERMES_AUTO_PR=0 turns this off). Hermes never merges: the PR is the review step.
2. Append a run record to LysStack (operating_system/run-log.md, left uncommitted for Lystiger, like
   design decisions).
3. Remove the job's worktrees and task branches. The integration branch stays: it is the PR's source.
Integration branches whose work is already in origin/main are deleted, locally and on origin, by
prune_merged_job_branches, which also runs here.
"""

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.task_usage import read_job_usage

logger = logging.getLogger("hermes.job_finalizer")


def _git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=check, timeout=300)


def summarize(engine: Any, run_dir: Path) -> Dict[str, Any]:
    """What the PR and the run record report: tasks, the last verdict, repairs and cost."""
    tasks = []
    verdict = None
    for t in engine.graph.list_tasks():
        meta = t.metadata or {}
        tasks.append({"id": t.task_id, "role": meta.get("role") or meta.get("execution_role") or "?",
                      "agent": t.assigned_actor or "-", "status": t.status.value})
        if meta.get("role") in ("verifier", "security") and t.status.value == "succeeded":
            verdict = {"task": t.task_id, "summary": meta.get("verification_summary"), "findings": meta.get("findings") or []}
    return {"job_id": engine.job.job_id, "goal": engine.job.goal, "branch": engine.job.branch,
            "repairs": engine.job.repair_count, "tasks": tasks, "verdict": verdict, "usage": read_job_usage(run_dir)}


def pr_body(summary: Dict[str, Any]) -> str:
    lines = [f"Built by Hermes goal-planned job `{summary['job_id']}`. Needs a human review before merging.",
             "", "**Goal**", "", summary["goal"], "", "**Tasks**", ""]
    lines += [f"- `{t['id']}`: {t['role']}, {t['agent']}, {t['status']}" for t in summary["tasks"]]
    v = summary.get("verdict")
    if v:
        lines += ["", f"**Verification** ({v['task']}): {v.get('summary') or 'passed'}"]
        lines += [f"- {f}" for f in v.get("findings", [])]
    lines += ["", f"**Repair cycles:** {summary['repairs']}"]
    usage = summary.get("usage")
    if usage:
        cost = f"${usage['costUsd']:.4f}" if usage.get("costUsd") is not None else "not reported"
        lines += [f"**Tokens:** {usage['tokens']['total_tokens']:,} total, Claude cost {cost}"]
    return "\n".join(lines)


def open_pull_request(repo: Path, branch: str, summary: Dict[str, Any]) -> Optional[str]:
    """Pushes the branch and opens (or finds) its PR. Returns the URL, or None when it could not."""
    if os.environ.get("HERMES_AUTO_PR", "1") == "0" or not shutil.which("gh"):
        return None
    if _git(repo, "remote", "get-url", "origin").returncode != 0:
        return None
    push = _git(repo, "push", "-q", "origin", branch)
    if push.returncode != 0:
        logger.warning("Could not push %s: %s", branch, push.stderr.strip()[:300])
        return None
    title = f"hermes: {summary['goal'].splitlines()[0][:72]}"
    created = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title,
                              "--body", pr_body(summary)], cwd=repo, capture_output=True, text=True, timeout=120)
    if created.returncode == 0:
        return created.stdout.strip().splitlines()[-1]
    existing = subprocess.run(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"], cwd=repo,
                              capture_output=True, text=True, timeout=60)
    if existing.returncode == 0 and existing.stdout.strip():
        return existing.stdout.strip()
    logger.warning("Could not open a PR for %s: %s", branch, created.stderr.strip()[:300])
    return None


def record_run(lysstack_root: Path, summary: Dict[str, Any], pr_url: Optional[str]) -> Optional[Path]:
    """Appends a run record to LysStack's run log (uncommitted)."""
    log = lysstack_root / "operating_system" / "run-log.md"
    if not log.parent.is_dir():
        return None
    if not log.exists():
        log.write_text("# Hermes run log\n\nCompleted goal-planned runs, recorded by Hermes. Review and commit.\n",
                       encoding="utf-8")
    usage = summary.get("usage") or {}
    cost = usage.get("costUsd")
    entry = [
        "", f"## {summary['job_id']}", "",
        f"- **Date:** {datetime.now(timezone.utc).date().isoformat()}",
        f"- **Goal:** {summary['goal'].splitlines()[0][:200]}",
        "- **Result:** completed, verified" + (f" after {summary['repairs']} repair cycle(s)" if summary["repairs"] else ""),
        f"- **Branch:** `{summary['branch']}`",
        f"- **Review:** {pr_url or 'no PR opened'}",
        f"- **Tasks:** " + ", ".join(f"{t['id']} ({t['role']}, {t['agent']})" for t in summary["tasks"]),
        f"- **Cost:** " + (f"${cost:.4f} Claude, " if cost is not None else "") +
        f"{(usage.get('tokens') or {}).get('total_tokens', 0):,} tokens",
    ]
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n".join(entry) + "\n")
    return log


def clean_job_worktrees(repo: Path, worktree_root: Path, job_id: str) -> int:
    """Removes the job's worktrees and its task branches; keeps the integration branch. Returns worktrees removed."""
    removed = 0
    listing = _git(repo, "worktree", "list", "--porcelain").stdout
    for block in listing.split("\n\n"):
        path = next((line[9:] for line in block.splitlines() if line.startswith("worktree ")), None)
        if path and Path(path).resolve().is_relative_to(worktree_root.resolve()):
            if _git(repo, "worktree", "remove", "--force", path).returncode == 0:
                removed += 1
    _git(repo, "worktree", "prune")
    branches = _git(repo, "branch", "--format=%(refname:short)", "--list", f"task/{job_id}/*").stdout.split()
    for b in branches:
        _git(repo, "branch", "-D", b)
    shutil.rmtree(worktree_root, ignore_errors=True)
    return removed


def prune_merged_job_branches(repo: Path, keep: Optional[str] = None) -> List[str]:
    """Deletes job integration branches whose work is already in origin/main, locally and on origin.
    `keep` is the branch of the job being finalized, whose PR was just opened."""
    if _git(repo, "fetch", "-q", "origin", "main").returncode != 0:
        return []
    pruned = []
    for b in _git(repo, "branch", "--format=%(refname:short)", "--list", "job/*/integration").stdout.split():
        if b == keep or _git(repo, "merge-base", "--is-ancestor", b, "origin/main").returncode != 0:
            continue
        # A branch checked out in a worktree cannot be deleted; its job is still being cleaned.
        if _git(repo, "branch", "-d", b).returncode == 0:
            _git(repo, "push", "-q", "origin", "--delete", b)
            pruned.append(b)
    return pruned


def finalize_completed_job(engine: Any, repo: Path, worktree_root: Path, run_dir: Path,
                           lysstack_root: Optional[Path] = None, review: bool = True) -> Dict[str, Any]:
    """review=False (a dry run: no agent changed anything) only cleans up: no PR, no run record."""
    summary = summarize(engine, run_dir)
    pr_url = record = None
    if review:
        pr_url = open_pull_request(repo, engine.job.branch, summary)
        lysstack = lysstack_root or Path(os.environ.get("HERMES_LYSSTACK_ROOT", Path.home() / "Projects" / "LysStack"))
        record = record_run(lysstack, summary, pr_url)
    removed = clean_job_worktrees(repo, worktree_root, engine.job.job_id)
    pruned = prune_merged_job_branches(repo, keep=engine.job.branch)
    result = {"prUrl": pr_url, "runLog": str(record) if record else None, "worktreesRemoved": removed, "pruned": pruned}
    run_dir.mkdir(parents=True, exist_ok=True)  # a dry run never created it
    (run_dir / "finalize.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Finalized job %s: %s", engine.job.job_id, result)
    return result
