from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import sys
from pathlib import Path

RUNNER_DIR = Path(__file__).resolve().parent / "runner"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from normalization import normalize_agent_id

try:
    from runner.agents.registry import default_registry
except ImportError:
    try:
        from agents.registry import default_registry
    except ImportError:
        default_registry = None


# Known presentation & role metadata for standard adapters (enrichment only)
KNOWN_AGENT_METADATA: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "displayName": "Gemini",
        "provider": "Google AI Studio",
        "model": "antigravity-2.5-pro",
        "role": "Implementation · scaffolding · migrations",
        "capabilities": ["build", "scaffolding", "migrations", "refactoring"],
        "accentColor": "#5B8CFF",
        "sigil": "BUILD",
        "code": "G-01",
    },
    "claude": {
        "displayName": "Claude",
        "provider": "Anthropic API",
        "model": "claude-sonnet-4-5",
        "role": "Architecture · review · hardening · docs",
        "capabilities": ["architecture", "security-review", "hardening", "documentation"],
        "accentColor": "#D9A05B",
        "sigil": "HARDEN",
        "code": "C-02",
    },
    "codex": {
        "displayName": "Codex",
        "provider": "OpenAI",
        "model": "gpt-5-codex",
        "role": "Verification · tests · static analysis · regressions",
        "capabilities": ["verification", "unit-tests", "static-analysis", "regression-testing"],
        "accentColor": "#4EC9A0",
        "sigil": "VERIFY",
        "code": "X-03",
    }
}


@dataclass
class AgentPresentationDTO:
    displayName: str
    accentColor: Optional[str] = None
    avatarUrl: Optional[str] = None
    characterCardUrl: Optional[str] = None
    sigil: Optional[str] = None
    code: Optional[str] = None


@dataclass
class AgentSummaryDTO:
    id: str
    displayName: str
    provider: str
    model: Optional[str]
    role: str
    capabilities: List[str]
    status: str  # "IDLE" | "RUNNING" | "WAITING" | "OFFLINE" | "BUSY" | "ERROR"
    phase: Optional[str] = None
    currentTask: Optional[str] = None
    activeTool: Optional[str] = None
    presentation: Optional[AgentPresentationDTO] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.presentation:
            data["presentation"] = asdict(self.presentation)
        return data


class AgentService:
    """
    Service that exposes dynamic agent registrations from the Hermes / LysStack registry.
    """

    def __init__(self, registry=None):
        self._registry = registry or default_registry
        self._runtime_status: Dict[str, str] = {}
        self._runtime_tasks: Dict[str, str] = {}

    def set_agent_status(self, agent_id: str, status: str, current_task: Optional[str] = None) -> None:
        normalized_id = normalize_agent_id(agent_id)
        self._runtime_status[normalized_id] = status.upper()
        if current_task is not None:
            self._runtime_tasks[normalized_id] = current_task
        elif status.upper() in {"IDLE", "ERROR", "OFFLINE"}:
            self._runtime_tasks.pop(normalized_id, None)

    def get_agent_status(self, agent_id: str) -> str:
        normalized_id = normalize_agent_id(agent_id)
        return self._runtime_status.get(normalized_id, "IDLE")

    def get_all_agents(self) -> List[Dict[str, Any]]:
        agents_list: List[Dict[str, Any]] = []

        # 1. Fetch all registered adapter names from the registry (Task 6 & Task 7: strictly registry-driven)
        registered_names = list(self._registry.supported_agents) if self._registry else ["antigravity", "claude", "codex"]

        for raw_name in registered_names:
            normalized_id = normalize_agent_id(raw_name)
            meta = KNOWN_AGENT_METADATA.get(normalized_id, {})

            display_name = meta.get("displayName", normalized_id.capitalize())
            provider = meta.get("provider", "Dynamic Provider")
            model = meta.get("model", "unknown")
            role = meta.get("role", "Specialized Operative")
            capabilities = meta.get("capabilities", ["general-execution"])
            accent_color = meta.get("accentColor", "#8C949F")

            status = self._runtime_status.get(normalized_id, "IDLE")
            current_task = self._runtime_tasks.get(normalized_id)

            dto = AgentSummaryDTO(
                id=normalized_id,
                displayName=display_name,
                provider=provider,
                model=model,
                role=role,
                capabilities=capabilities,
                status=status,
                phase=meta.get("sigil"),
                currentTask=current_task,
                presentation=AgentPresentationDTO(
                    displayName=display_name,
                    accentColor=accent_color,
                    sigil=meta.get("sigil", normalized_id.upper()[:4]),
                    code=meta.get("code", normalized_id.upper()[:4]),
                ),
            )
            agents_list.append(dto.to_dict())

        return agents_list


agent_service = AgentService()

# Bind agent service to the state reducer
from agent_state_reducer import agent_state_reducer
agent_state_reducer.bind_service(agent_service)
