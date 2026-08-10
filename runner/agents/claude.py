import json

from .base import AgentAdapter
from .errors import SprintRunnerError


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
    for pattern in (f"Bash(git {subcommand})", f"Bash(git {subcommand} *)")
) + (
    "Bash(git branch --copy *)",
    "Bash(git branch --delete *)",
    "Bash(git branch --move *)",
    "Bash(git branch -C *)",
    "Bash(git branch -D *)",
    "Bash(git branch -M *)",
    "Bash(git branch -c *)",
    "Bash(git branch -d *)",
    "Bash(git branch -m *)",
    "Bash(git remote add *)",
    "Bash(git remote remove *)",
    "Bash(git remote rename *)",
    "Bash(git remote set-url *)",
)


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def build_command(self, prompt, options, worktree=None):
        extra_denials = options.get("disallowed_tools", [])
        if isinstance(extra_denials, str):
            extra_denials = [extra_denials]
        disallowed_tools = tuple(
            dict.fromkeys((*CLAUDE_GIT_MUTATION_DENIALS, *extra_denials))
        )
        return [
            "claude",
            "-p",
            prompt,
            "--model",
            options.get("model", "sonnet"),
            "--max-turns",
            str(options.get("max_turns", 30)),
            "--permission-mode",
            options.get("permission_mode", "dontAsk"),
            "--output-format",
            options.get("output_format", "json"),
            "--disallowed-tools",
            ",".join(disallowed_tools),
        ]

    def validate_result(self, result, context):
        self.parse_json(result.stdout or "", result.stderr or "")

    @staticmethod
    def parse_json(stdout_text, stderr_text=""):
        if "permission denied" in stderr_text.lower():
            raise SprintRunnerError(
                "FAILED_PERMISSION_DENIED",
                f"Claude permission denied in stderr:\n{stderr_text}",
            )
        cleaned = stdout_text.strip()
        if not cleaned:
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
            raise SprintRunnerError(
                "FAILED_CLAUDE_INVALID_JSON",
                f"Failed to parse JSON response from Claude: {cleaned[:200]}",
            )
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
        denials = data.get("permission_denials") or []
        if denials:
            raise SprintRunnerError(
                "FAILED_PERMISSION_DENIED", f"Claude encountered permission denials: {denials}"
            )
