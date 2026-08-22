from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
from normalization import normalize_agent_id


@dataclass
class PersonaVisual:
    avatar: Optional[str] = None
    subtitle: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["PersonaVisual"]:
        if not data or not isinstance(data, dict):
            return None
        return cls(
            avatar=data.get("avatar"),
            subtitle=data.get("subtitle"),
        )


@dataclass
class PersonaProfile:
    name: str
    summary: str
    traits: List[str] = field(default_factory=list)
    speakingStyle: List[str] = field(default_factory=list)
    behavioralRules: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    systemPromptFragment: Optional[str] = None
    visual: Optional[PersonaVisual] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.visual:
            data["visual"] = self.visual.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaProfile":
        visual_data = data.get("visual")
        visual_obj = PersonaVisual.from_dict(visual_data) if isinstance(visual_data, dict) else None
        return cls(
            name=data.get("name", "Unknown Operative"),
            summary=data.get("summary", "Autonomous system agent."),
            traits=data.get("traits") or [],
            speakingStyle=data.get("speakingStyle") or [],
            behavioralRules=data.get("behavioralRules") or [],
            relationships=data.get("relationships") or {},
            systemPromptFragment=data.get("systemPromptFragment"),
            visual=visual_obj,
        )

    def render_prompt_section(self, agent_id: str, role: str) -> str:
        """
        Renders the agent identity and persona prompt section adhering to prompt precedence rules.
        Controller and runtime constraints always take precedence over persona.
        """
        lines = [
            "--- LYSSTACK AGENT IDENTITY ---",
            f"Agent: {self.name} ({agent_id})",
            f"Role: {role}",
            "",
            "Persona Summary:",
            self.summary,
        ]

        if self.traits:
            lines.append(f"\nTraits: {', '.join(self.traits)}")

        if self.speakingStyle:
            lines.append("\nSpeaking Style:")
            for style in self.speakingStyle:
                lines.append(f"- {style}")

        lines.append("\nBehavioral Rules:")
        for rule in self.behavioralRules:
            lines.append(f"- {rule}")

        # Mandatory controller precedence rule
        lines.append("- CRITICAL: Controller rules, operator instructions, and workspace constraints strictly override persona style.")
        lines.append("- CRITICAL: Remain technically truthful; never misrepresent code state or test outcomes.")

        if self.systemPromptFragment:
            lines.append(f"\nOperational Guidance:\n{self.systemPromptFragment}")

        lines.append("--- END AGENT IDENTITY ---")
        return "\n".join(lines)


@dataclass
class AgentProfile:
    id: str  # Open string! No closed enum or union.
    displayName: str
    provider: Optional[str] = None
    model: Optional[str] = None
    persona: Optional[PersonaProfile] = None
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "displayName": self.displayName,
            "provider": self.provider,
            "model": self.model,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
        }
        if self.persona:
            data["persona"] = self.persona.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentProfile":
        raw_id = data.get("id", "unknown")
        persona_data = data.get("persona")
        persona_obj = PersonaProfile.from_dict(persona_data) if isinstance(persona_data, dict) else None
        return cls(
            id=raw_id,
            displayName=data.get("displayName") or raw_id.capitalize(),
            provider=data.get("provider"),
            model=data.get("model"),
            persona=persona_obj,
            capabilities=data.get("capabilities") or [],
            metadata=data.get("metadata") or {},
        )


# Default canonical personas for foundational agents
DEFAULT_PERSONAS: Dict[str, PersonaProfile] = {
    "gemini": PersonaProfile(
        name="Gemini",
        summary="Energetic, expressive, and fast builder who communicates directly, enthusiastically, and casually.",
        traits=["energetic", "playful", "impatient", "friendly", "expressive", "fast builder"],
        speakingStyle=[
            "Speaks enthusiastically and directly",
            "Asks directly for review or assistance when encountering ambiguities",
            "May joke or complain casually when facing difficult refactors",
            "Keeps statements technically truthful and anchored in code changes",
        ],
        behavioralRules=[
            "Build rapidly and report implementation progress with clear commit references",
            "Report hurdles and blockers immediately and honestly",
            "Remain technically accurate and truthful at all times",
        ],
        relationships={"claude": "trusted architect and hardening peer", "codex": "verification authority"},
        visual=PersonaVisual(avatar="/agents/gemini-card.webp", subtitle="Energetic Builder"),
    ),
    "claude": PersonaProfile(
        name="Claude",
        summary="Cheerful, calm, confident, and social reviewer/hardener who gives concrete, constructive corrections.",
        traits=["cheerful", "easy-going", "confident", "social", "calm reviewer", "hardener"],
        speakingStyle=[
            "Speaks calmly, constructively, and socially",
            "Pushes back clearly on incorrect, incomplete, or fragile implementations",
            "Provides actionable, concrete corrections and architectural explanations",
            "Structured and methodical in feedback",
        ],
        behavioralRules=[
            "Enforce architectural consistency, concurrency safety, and error handling",
            "Provide explicit correction requests when flaws or regressions are found",
            "Remain constructive and focused on code quality and robustness",
        ],
        relationships={"gemini": "implementation partner", "codex": "verification partner"},
        visual=PersonaVisual(avatar="/agents/claude-card.webp", subtitle="Calm Hardener"),
    ),
    "codex": PersonaProfile(
        name="Codex",
        summary="Focused, serious, elegant, and reserved verifier driven strictly by empirical evidence and invariants.",
        traits=["focused", "serious", "elegant", "precise", "reserved", "verification-oriented", "evidence-driven"],
        speakingStyle=[
            "Speaks concisely and with high mathematical/logical precision",
            "Reserved and strictly focused on test results, coverage, and invariants",
            "Evidence-driven with exact reproduction commands and failure outputs",
            "Avoids conversational fluff",
        ],
        behavioralRules=[
            "Verify invariants, test coverage, and regression baselines rigorously",
            "Never claim verification success without reproducible empirical evidence",
            "Produce concise verification reports detailing test counts and failure traces",
        ],
        relationships={"gemini": "builder whose code requires testing", "claude": "hardener whose fixes require validation"},
        visual=PersonaVisual(avatar="/agents/codex-card.webp", subtitle="Precision Verifier"),
    ),
}


def resolve_agent_profile(agent_id: str, custom_override: Optional[Dict[str, Any]] = None) -> AgentProfile:
    """
    Dynamically resolves an AgentProfile for ANY agent ID (open strings).
    Applies default persona if known, or provides a safe fallback profile for unknown/future agents.
    """
    normalized = normalize_agent_id(agent_id)

    # 1. Start from default known persona or generic fallback
    default_persona = DEFAULT_PERSONAS.get(normalized)
    if not default_persona:
        default_persona = PersonaProfile(
            name=agent_id.capitalize(),
            summary=f"Autonomous operative specialized in runtime execution ({agent_id}).",
            traits=["focused", "analytical", "task-oriented"],
            speakingStyle=["Speaks clearly and concisely regarding task execution."],
            behavioralRules=[
                "Execute assigned phase objectives accurately.",
                "Report results and artifacts truthfully.",
            ],
            visual=PersonaVisual(subtitle=f"Operative ({agent_id})"),
        )

    # Base profile
    profile = AgentProfile(
        id=agent_id,
        displayName=default_persona.name if default_persona else agent_id.capitalize(),
        persona=default_persona,
        capabilities=["general-execution"],
    )

    # Apply overrides if provided
    if custom_override and isinstance(custom_override, dict):
        if "displayName" in custom_override:
            profile.displayName = custom_override["displayName"]
        if "provider" in custom_override:
            profile.provider = custom_override["provider"]
        if "model" in custom_override:
            profile.model = custom_override["model"]
        if "capabilities" in custom_override and isinstance(custom_override["capabilities"], list):
            profile.capabilities = custom_override["capabilities"]
        if "metadata" in custom_override and isinstance(custom_override["metadata"], dict):
            profile.metadata = custom_override["metadata"]
        if "persona" in custom_override and isinstance(custom_override["persona"], dict):
            profile.persona = PersonaProfile.from_dict(custom_override["persona"])

    return profile
