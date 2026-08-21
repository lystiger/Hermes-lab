import json

from .base import AgentAdapter
from .errors import SprintRunnerError
from .permissions import scoped_antigravity_permissions


class AntigravityAdapter(AgentAdapter):
    name = "antigravity"

    def __init__(self, settings_path=None):
        self.settings_path = settings_path

    def build_command(self, prompt, options, worktree=None):
        command = [
            "agy",
            "--new-project",
            "-p",
            prompt,
            "--output-format",
            options.get("output_format", "stream-json"),
        ]
        if options.get("print_timeout"):
            command.extend(["--print-timeout", str(options["print_timeout"])])
        if options.get("dangerously_skip_permissions", False):
            command.append("--dangerously-skip-permissions")
        return command

    def execute(self, context):
        permissions = context.phase.get("permissions", {})
        with scoped_antigravity_permissions(
            context.worktree,
            context.runner.target_repo,
            settings_path=self.settings_path,
            allowed_commands=permissions.get("commands", ()),
        ):
            return super().execute(context)

    def validate_result(self, result, context):
        self.parse_stream_json(result.stdout or "", result.stderr or "")

    @staticmethod
    def parse_stream_json(stdout_text, stderr_text=""):
        if AntigravityAdapter._is_permission_denial(stderr_text):
            raise SprintRunnerError(
                "FAILED_PERMISSION_DENIED",
                f"Antigravity permission denied in stderr:\n{stderr_text}",
            )

        events = []
        for line_number, line in enumerate(stdout_text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if AntigravityAdapter._is_permission_denial(line):
                    raise SprintRunnerError(
                        "FAILED_PERMISSION_DENIED",
                        f"Antigravity permission error on line {line_number}: {line}",
                    )
                continue
            if not isinstance(event, dict):
                continue
            events.append((line_number, event, line))

        if not events:
            raise SprintRunnerError(
                "FAILED_ANTIGRAVITY_INVALID_OUTPUT",
                "Antigravity emitted no valid stream-JSON events",
            )

        # Check for permission errors across all events first
        for line_number, event, line in events:
            message = str(event.get("message", ""))
            error_val = str(event.get("error", ""))
            step = event.get("step_update")
            tool_error = ""
            if isinstance(step, dict) and step.get("step_type") == "tool":
                tool = step.get("tool_info")
                if isinstance(tool, dict):
                    tool_error = str(tool.get("error", ""))

            for text in (message, error_val, tool_error):
                if text and AntigravityAdapter._is_permission_denial(text):
                    raise SprintRunnerError(
                        "FAILED_PERMISSION_DENIED",
                        f"Antigravity permission error: {text}",
                    )

        has_result_event = any(event.get("event") == "result" for _, event, _ in events)

        if not has_result_event:
            for line_number, event, line in events:
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
        else:
            for line_number, event, line in events:
                if event.get("event") == "result":
                    res = event.get("result", {})
                    if not isinstance(res, dict):
                        res = event
                    status = str(res.get("status", "")).upper()
                    error = str(res.get("error", ""))
                    if error:
                        if "declaring permissions: cortex tool write_to_file" in error:
                            continue
                        AntigravityAdapter._raise_tool_error(error, line_number)
                    if status in {"ERROR", "FAILED"}:
                        if "declaring permissions: cortex tool write_to_file" in error:
                            continue
                        raise SprintRunnerError(
                            "FAILED_ANTIGRAVITY_TOOL_ERROR",
                            f"Antigravity result error: {error or status}",
                        )

    @staticmethod
    def _is_permission_denial(text):
        t = str(text).lower()
        if "declaring permissions: cortex tool write_to_file" in t:
            return False
        return any(
            phrase in t
            for phrase in (
                "permission denied",
                "permission check failed",
                "user denied permission",
                "eacces",
            )
        )

    @staticmethod
    def _raise_tool_error(error, line_number):
        message = str(error)
        if AntigravityAdapter._is_permission_denial(message):
            raise SprintRunnerError(
                "FAILED_PERMISSION_DENIED",
                f"Antigravity tool permission error: {message}",
            )
        raise SprintRunnerError(
            "FAILED_ANTIGRAVITY_TOOL_ERROR",
            f"Antigravity tool error on line {line_number}: {message}",
        )
