import json

from .base import AgentAdapter, argv_safe_prompt
from .errors import SprintRunnerError
from .denials import check_denials


_CLAUDE_MUTATING_GIT_SUBCOMMANDS = (
    "add",
    "am",
    "checkout",
    "cherry-pick",
    "clean",
    "commit",
    "fetch",
    "merge",
    "notes",
    "pull",
    "push",
    "rebase",
    "replace",
    "reset",
    "revert",
    "rm",
    "stash",
    "switch",
    "symbolic-ref",
    "tag",
    "update-ref",
    "worktree",
)

CLAUDE_GIT_MUTATION_DENIALS = tuple(
    pattern
    for subcommand in _CLAUDE_MUTATING_GIT_SUBCOMMANDS
    for pattern in (f"Bash(git {subcommand})", f"Bash(git {subcommand}:*)")
) + (
    "Bash(git branch --copy:*)",
    "Bash(git branch --delete:*)",
    "Bash(git branch --move:*)",
    "Bash(git branch -C:*)",
    "Bash(git branch -D:*)",
    "Bash(git branch -M:*)",
    "Bash(git branch -c:*)",
    "Bash(git branch -d:*)",
    "Bash(git branch -m:*)",
    "Bash(git remote add:*)",
    "Bash(git remote remove:*)",
    "Bash(git remote rename:*)",
    "Bash(git remote set-url:*)",
)


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def build_command(self, prompt, options, worktree=None):
        options = self.model_options(options)
        allowed_tools = options.get("allowed_tools", ["Bash", "Edit", "Write"])
        if isinstance(allowed_tools, str):
            allowed_tools = [allowed_tools]
        extra_denials = options.get("disallowed_tools", [])
        if isinstance(extra_denials, str):
            extra_denials = [extra_denials]
        disallowed_tools = tuple(
            dict.fromkeys((*CLAUDE_GIT_MUTATION_DENIALS, *extra_denials))
        )
        command = [
            "claude",
            "-p",
            argv_safe_prompt(prompt),
            "--max-turns",
            str(options.get("max_turns", 30)),
            "--permission-mode",
            options.get("permission_mode", "dontAsk"),
            "--output-format",
            options.get("output_format", "json"),
            "--allowedTools",
            ",".join(dict.fromkeys(allowed_tools)),
            "--disallowedTools",
            ",".join(disallowed_tools),
        ]

        if options.get("model"):
            command[3:3] = ["--model", options["model"]]
        return command

    @staticmethod
    def parse_json(stdout_text, stderr_text="", options=None, metadata=None, phase=None, worktree=None):
        stderr_denials = [line for line in stderr_text.splitlines() if "permission denied" in line.lower()]
        cleaned = stdout_text.strip()
        if not cleaned:
            check_denials(stderr_denials, False, options, metadata, phase, worktree)
            raise SprintRunnerError("FAILED_CLAUDE_EMPTY_OUTPUT", "Claude emitted no output")

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            data = None
            for line in reversed([line.strip() for line in cleaned.splitlines() if line.strip()]):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if not isinstance(data, dict):
            check_denials(stderr_denials, False, options, metadata, phase, worktree)
            raise SprintRunnerError(
                "FAILED_CLAUDE_INVALID_JSON",
                f"Failed to parse JSON response from Claude: {cleaned[:200]}",
            )
        check_denials((data.get("permission_denials") or []) + stderr_denials,
                      bool(str(data.get("result") or "").strip()) and data.get("type") == "result"
                      and data.get("subtype") == "success" and data.get("is_error") is False, options, metadata, phase, worktree)
        if data.get("type") != "result":
            raise SprintRunnerError(
                "FAILED_CLAUDE_ERROR",
                f"Claude output type is '{data.get('type')}', expected 'result'",
            )
        subtype = data.get("subtype")
        if subtype == "max_turns_exceeded" or "max_turns" in str(subtype).lower():
            raise SprintRunnerError(
                "FAILED_CLAUDE_MAX_TURNS", f"Claude reached maximum turn limit: {subtype}"
            )
        if subtype != "success":
            raise SprintRunnerError(
                "FAILED_CLAUDE_ERROR",
                f"Claude output subtype is '{subtype}', expected 'success'",
            )
        if data.get("is_error") is not False:
            message = data.get("error") or data.get("message") or f"is_error is {data.get('is_error')}"
            raise SprintRunnerError(
                "FAILED_CLAUDE_ERROR",
                f"Claude execution returned is_error={data.get('is_error')}: {message}",
            )
        return data

    def validate_result(self, result, context):
        data = self.parse_json(result.stdout or "", result.stderr or "",
                               getattr(context, "options", {}), getattr(result, "runtime_metadata", None),
                               getattr(context, "phase", {}), getattr(context, "worktree", None))
        if isinstance(data, dict):
            if not hasattr(result, "runtime_metadata") or result.runtime_metadata is None:
                result.runtime_metadata = {}
            if "usage" in data:
                result.runtime_metadata["usage"] = data["usage"]
            if "model" in data:
                result.runtime_metadata["model"] = data["model"]
            if "context_used" in data:
                result.runtime_metadata["context_used"] = data["context_used"]
            if "context_window" in data:
                result.runtime_metadata["context_window"] = data["context_window"]
            if "tokens_remaining" in data:
                result.runtime_metadata["tokens_remaining"] = data["tokens_remaining"]
            if "token_limit" in data:
                result.runtime_metadata["token_limit"] = data["token_limit"]
