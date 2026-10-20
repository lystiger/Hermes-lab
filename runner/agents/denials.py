"""Shared permission-denial policy. Scope violations always fail closed."""
import json
import re
import shlex
from pathlib import Path

from .errors import SprintRunnerError


def denial_text(value):
    if isinstance(value, dict):
        tool_input = value.get("tool_input") or value.get("input") or value
        if isinstance(tool_input, dict):
            return str(tool_input.get("command") or tool_input.get("file_path") or json.dumps(tool_input))
        return str(tool_input)
    return str(value)


def denial_lines(stderr):
    """Stderr lines that report a denial. Diff-shaped lines echo file content, not denials."""
    return [
        line for line in (stderr or "").splitlines()
        if "permission denied" in line.lower() and line[:1] not in (" ", "\t", "+", "-", "@")
    ]


def check_denials(denials, usable, options=None, metadata=None, phase=None, worktree=None):
    strict = bool((phase or {}).get("fail_on_permission_denial") or (options or {}).get("fail_on_permission_denial"))
    options = {**(phase or {}), **(options or {})}
    texts = [denial_text(d) for d in denials]
    if metadata is not None and texts:
        metadata["permission_denial_count"] = len(texts)
        observations = metadata.setdefault("observations", [])
        observations.extend({"kind": "permission_denial", "content": t[:300],
                             "metadata": {"command": t[:300], "count": len(texts)}} for t in texts)
    scope = any(_git_mutation(t) or re.search(
        r"outside.*(worktree|workspace|allowed|permitted|sandbox)|scope violation", t, re.I) for t in texts)
    if worktree is not None:
        root = Path(worktree).resolve()
        for denial in denials:
            if not isinstance(denial, dict):
                continue
            tool = str(denial.get("tool_name") or denial.get("name") or "").lower()
            payload = denial.get("tool_input") or denial.get("input") or denial
            if isinstance(payload, dict) and payload.get("command"):
                scope = scope or _outside_shell_write(str(payload["command"]), root)
            if isinstance(payload, dict) and any(word in tool for word in ("write", "edit", "create", "delete")):
                path = payload.get("file_path") or payload.get("path") or payload.get("target_file")
                if path and not (root / str(path)).resolve().is_relative_to(root):
                    scope = True
    if texts and (scope or not usable or len(texts) > int(options.get("permission_denial_ceiling", 20))
                  or strict):
        raise SprintRunnerError("FAILED_PERMISSION_DENIED", f"Permission denials ({len(texts)}): {texts}")


def _git_mutation(text):
    mutating = {"add", "am", "checkout", "cherry-pick", "clean", "commit", "fetch",
                "merge", "notes", "pull", "push", "rebase", "replace", "reset", "revert",
                "rm", "stash", "switch", "symbolic-ref", "tag", "update-ref", "worktree",
                "init", "clone", "gc", "prune", "repack", "maintenance", "apply"}
    for match in re.finditer(r"\bgit\s+", text):
        try:
            lexer = shlex.shlex(text[match.end():], posix=True, punctuation_chars=";&|()")
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:
            return True  # malformed denied Git commands cannot be established as read-only
        while words and words[0].startswith("-"):
            option = words.pop(0)
            if option in {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"} and words:
                words.pop(0)
        if not words:
            continue
        command, *args = words
        command = command.split(":", 1)[0]
        if command in mutating:
            return True
        if command == "branch" and any(a in {"-c", "-C", "-d", "-D", "-m", "-M", "--copy", "--delete", "--move"} for a in args):
            return True
        if command == "remote" and args and args[0] in {"add", "remove", "rm", "rename", "set-url", "set-head", "prune", "update"}:
            return True
        if command == "config" and not any(a in {"--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list"} for a in args):
            return True
    return False


def _outside_shell_write(command, root):
    """Recognize literal shell write targets; resolve symlinks against the task boundary."""
    candidates = re.findall(r"(?:>>?|\btee\s+)\s*([^\s;|&]+)", command)
    for segment in re.split(r"[;|&]", command):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        if words and words[0] in {"touch", "mkdir", "rm", "rmdir", "cp", "mv", "install", "truncate", "chmod", "chown"}:
            targets = [word for word in words[1:] if not word.startswith("-")]
            candidates.extend(targets[-1:] if words[0] in {"cp", "install"} else targets)
    for target in candidates:
        target = target.strip("\"'")
        if target.startswith(("/", "..")) and not (root / target).resolve().is_relative_to(root):
            return True
    return False
