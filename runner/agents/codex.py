from .base import AgentAdapter
from .errors import SprintRunnerError


class CodexAdapter(AgentAdapter):
    name = "codex"

    def build_command(self, prompt, options, worktree=None):
        command = ["codex", "exec", "--color", "never"]
        if worktree is not None:
            command.extend(["--cd", str(worktree)])
        if options.get("model"):
            command.extend(["--model", str(options["model"])])
        if options.get("sandbox"):
            command.extend(["--sandbox", str(options["sandbox"])])
        if options.get("ephemeral", True):
            command.append("--ephemeral")
        command.append(prompt)
        return command

    def validate_result(self, result, context):
        if not (result.stdout or "").strip():
            raise SprintRunnerError("FAILED_CODEX_EMPTY_OUTPUT", "Codex emitted no output")
