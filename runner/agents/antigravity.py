import json

from .base import AgentAdapter
from .errors import SprintRunnerError
from .permissions import scoped_antigravity_permissions


class AntigravityAdapter(AgentAdapter):
    name = "antigravity"

    def build_command(self, prompt, options, worktree=None):
        command = [
            "agy",
            "-p",
            prompt,
            "--output-format",
            options.get("output_format", "stream-json"),
        ]
        if options.get("dangerously_skip_permissions", False):
            command.append("--dangerously-skip-permissions")
        return command

    def execute(self, context):
        with scoped_antigravity_permissions(
            context.worktree, context.runner.canonical_repo
        ):
            return super().execute(context)

    def validate_result(self, result, context):
        self.parse_stream_json(result.stdout or "", result.stderr or "")

    @staticmethod
    def parse_stream_json(stdout_text, stderr_text=""):
        if "permission denied" in stderr_text.lower():
            raise SprintRunnerError(
                "FAILED_PERMISSION_DENIED",
                f"Antigravity permission denied in stderr:\n{stderr_text}",
            )

        parsed_events = 0
        for line_number, line in enumerate(stdout_text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if "permission denied" in line.lower() or "eacces" in line.lower():
                    raise SprintRunnerError(
                        "FAILED_PERMISSION_DENIED",
                        f"Antigravity permission error on line {line_number}: {line}",
                    )
                continue
            if not isinstance(event, dict):
                continue
            parsed_events += 1

            step = event.get("step_update")
            if isinstance(step, dict) and step.get("step_type") == "tool":
                tool = step.get("tool_info")
                if isinstance(tool, dict) and tool.get("error") not in (None, False, ""):
                    AntigravityAdapter._raise_tool_error(tool["error"], line_number)

            if event.get("error") not in (None, False, ""):
                AntigravityAdapter._raise_tool_error(event["error"], line_number)
            if str(event.get("status", "")).upper() in {"ERROR", "FAILED"}:
                message = event.get("message") or event.get("details") or line
                raise SprintRunnerError(
                    "FAILED_ANTIGRAVITY_TOOL_ERROR",
                    f"Antigravity tool event failed: {message}",
                )
            if event.get("is_error") is True:
                raise SprintRunnerError(
                    "FAILED_ANTIGRAVITY_TOOL_ERROR",
                    f"Antigravity tool error event: {event.get('message') or line}",
                )
            message = str(event.get("message", ""))
            if "permission denied" in message.lower() or "eacces" in message.lower():
                raise SprintRunnerError(
                    "FAILED_PERMISSION_DENIED",
                    f"Antigravity permission error in message: {message}",
                )

        if parsed_events == 0:
            raise SprintRunnerError(
                "FAILED_ANTIGRAVITY_INVALID_OUTPUT",
                "Antigravity emitted no valid stream-JSON events",
            )

    @staticmethod
    def _raise_tool_error(error, line_number):
        message = str(error)
        if any(term in message.lower() for term in ("permission", "denied", "eacces")):
            raise SprintRunnerError(
                "FAILED_PERMISSION_DENIED",
                f"Antigravity tool permission error: {message}",
            )
        raise SprintRunnerError(
            "FAILED_ANTIGRAVITY_TOOL_ERROR",
            f"Antigravity tool error on line {line_number}: {message}",
        )
