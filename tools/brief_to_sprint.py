"""Turn a LysStack active task into a Hermes sprint specification.

The brief supplies the sprint identity, the pinned base commit, the target repository
and the bounded context files. Phases and verification are project-specific, so they
come from a template sprint spec.
"""

import argparse
import copy
import json
import os
import re
import subprocess
from pathlib import Path

CONTEXT_MAX_BYTES = 131072
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class BriefError(ValueError):
    """The brief cannot be turned into a runnable sprint."""


def _field(text, label):
    match = re.search(rf"^- \*\*{re.escape(label)}:\*\*\s*(.+)$", text, re.MULTILINE)
    if not match:
        raise BriefError(f"Brief has no '{label}' field")
    return match.group(1).strip()


def _section(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def parse_task(text):
    """Read the fields the sprint needs from operating_system/active_task.md."""
    target = _section(text, "Target")
    repository = re.search(r"\*\*Repository:\*\*\s*`([^`]+)`", target)
    baseline = re.search(r"\*\*Pinned baseline:\*\*\s*`([^`]+)`", target)
    if not repository or not baseline:
        raise BriefError("Brief Target section needs a Repository and a Pinned baseline")
    goal_lines = [line.strip() for line in _section(text, "Goal").splitlines() if line.strip()]
    goal_summary = goal_lines[0] if goal_lines else ""
    context_files = re.findall(r"^- `([^`]+)`", _section(text, "Bounded Context Files"), re.MULTILINE)
    if not context_files:
        raise BriefError("Brief lists no bounded context files")
    return {
        "task_id": _field(text, "Task ID"),
        "status": _field(text, "Status"),
        "repository": repository.group(1),
        "baseline": baseline.group(1),
        "goal": goal_summary,
        "context_files": context_files,
    }


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def check_target(repo, repository, baseline):
    """The local clone must be the brief's repository and must contain the pinned commit."""
    remote = _git(repo, "remote", "get-url", "origin")
    if remote.returncode != 0:
        raise BriefError(f"{repo} is not a git clone with an origin remote")
    if repository.split("/")[-1] not in remote.stdout:
        raise BriefError(f"{repo} origin is {remote.stdout.strip()}, brief expects {repository}")
    if not SHA_PATTERN.match(baseline):
        raise BriefError("Pinned baseline must be a full 40-character commit SHA")
    if _git(repo, "cat-file", "-e", f"{baseline}^{{commit}}").returncode != 0:
        raise BriefError(f"Pinned baseline {baseline} is not in {repo}")


def build_spec(task, template, lysstack, target_repo, spec_dir):
    """Return a sprint spec for the task, with paths relative to the spec's directory."""
    if task["status"] != "Ready":
        raise BriefError(f"Task {task['task_id']} is '{task['status']}', only 'Ready' tasks can run")
    missing = [name for name in task["context_files"] if not (lysstack / name).is_file()]
    if missing:
        raise BriefError(f"Context files missing from {lysstack}: {', '.join(missing)}")

    sprint_id = task["task_id"].lower()
    template_id = template["sprint_id"]
    spec = copy.deepcopy(template)
    spec["sprint_id"] = sprint_id
    spec["name"] = f"{task['task_id']}: {task['goal']}".rstrip(": ")
    spec["target_repo"] = os.path.relpath(target_repo, spec_dir)
    spec["base_ref"] = task["baseline"]
    spec["target_branch"] = template["target_branch"].replace(template_id, sprint_id)
    spec["worktree_root"] = template["worktree_root"].replace(template_id, sprint_id)
    spec["context"] = {
        "root": os.path.relpath(lysstack, spec_dir),
        "max_bytes": template.get("context", {}).get("max_bytes", CONTEXT_MAX_BYTES),
        "files": ["AGENTS.md"] + [f for f in task["context_files"] if f != "AGENTS.md"],
    }
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a Hermes sprint spec from a LysStack task brief")
    parser.add_argument("--task", required=True, type=Path, help="Path to LysStack operating_system/active_task.md")
    parser.add_argument("--template", required=True, type=Path, help="Sprint spec that supplies phases and verification")
    parser.add_argument("--target-repo", required=True, type=Path, help="Local clone of the brief's repository")
    parser.add_argument("--out", required=True, type=Path, help="Where to write the generated sprint spec")
    args = parser.parse_args(argv)

    task_path = args.task.resolve()
    lysstack = task_path.parent.parent
    task = parse_task(task_path.read_text(encoding="utf-8"))
    check_target(args.target_repo, task["repository"], task["baseline"])
    template = json.loads(args.template.read_text(encoding="utf-8"))
    spec = build_spec(task, template, lysstack, args.target_repo.resolve(), args.out.resolve().parent)
    args.out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} for {task['task_id']} at {task['baseline']}")
    print(f"Next: run the dry run and require DRY_RUN_READY: runner/run-hermes-sprint.py --spec {args.out} --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
