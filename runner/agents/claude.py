import json

from .base import AgentAdapter
from .errors import SprintRunnerError


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def build_command(self, prompt, options, worktree=None):
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
