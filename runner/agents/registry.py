from .antigravity import AntigravityAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .errors import SprintRunnerError


class AgentRegistry:
    def __init__(self, adapters=None):
        self._adapters = dict(adapters or {})

    def register(self, adapter_type):
        self._adapters[adapter_type.name] = adapter_type

    def get(self, name):
        adapter_type = self._adapters.get(name)
        if adapter_type is None:
            raise SprintRunnerError("FAILED_UNKNOWN_AGENT", f"Unknown agent type: {name}")
        return adapter_type()

    @property
    def supported_agents(self):
        return tuple(sorted(self._adapters))


default_registry = AgentRegistry(
    {
        AntigravityAdapter.name: AntigravityAdapter,
        ClaudeAdapter.name: ClaudeAdapter,
        CodexAdapter.name: CodexAdapter,
    }
)
