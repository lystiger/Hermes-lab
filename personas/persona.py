from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging

try:
    from capabilities.normalization import normalize_agent_id
except ImportError:
    normalize_agent_id = lambda x: str(x).lower()

logger = logging.getLogger("hermes.persona")


@dataclass
class PersonaVisual:
    avatar: Optional[str] = None
    subtitle: Optional[str] = None
    accentColor: Optional[str] = None
    badgeText: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaVisual":
        return cls(
            avatar=data.get("avatar") or data.get("avatarUrl"),
            subtitle=data.get("subtitle"),
            accentColor=data.get("accentColor") or data.get("accent_color"),
            badgeText=data.get("badgeText") or data.get("badge_text"),
        )


@dataclass
class PersonaProfile:
    name: str
    summary: str
    traits: List[str]
    speakingStyle: List[str]
    behavioralRules: List[str]
    relationships: Dict[str, str] = field(default_factory=dict)
    systemPromptFragment: Optional[str] = None
    visual: Optional[PersonaVisual] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "summary": self.summary,
            "traits": self.traits,
            "speakingStyle": self.speakingStyle,
            "behavioralRules": self.behavioralRules,
            "relationships": self.relationships,
            "systemPromptFragment": self.systemPromptFragment,
        }
        if self.visual:
            data["visual"] = self.visual.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaProfile":
        vis = data.get("visual")
        vis_obj = PersonaVisual.from_dict(vis) if isinstance(vis, dict) else None
        return cls(
            name=data.get("name", "Agent"),
            summary=data.get("summary", ""),
            traits=data.get("traits", []),
            speakingStyle=data.get("speakingStyle", []),
            behavioralRules=data.get("behavioralRules", []),
            relationships=data.get("relationships", {}),
            systemPromptFragment=data.get("systemPromptFragment"),
            visual=vis_obj,
        )

    def render_prompt_section(self, agent_id: str, role: str = "operative") -> str:
        """
        Renders the authoritative Agent Identity & Persona prompt section.
        Precedence: Controller rules > Operator instructions > Phase tasks > Persona style.
        """
        lines = [
            "--- LYSSTACK AGENT IDENTITY ---",
            f"Agent: {self.name} ({agent_id})",
            f"Role: {role}",
            "",
            "Persona Summary:",
            self.summary or "Standard autonomous software engineering operative.",
            "",
            f"Traits: {', '.join(self.traits) if self.traits else 'disciplined, focused'}",
            "",
            "Speaking Style:",
        ]
        for style in self.speakingStyle:
            lines.append(f"- {style}")

        lines.extend([
            "",
            "Behavioral Rules:",
        ])
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
            "Keeps prose brief, punchy, and constructive",
            "Excited about new features and clean abstractions",
        ],
        behavioralRules=[
            "Build robust implementations following specifications",
            "Do not hide regressions or broken tests",
            "Ask clarifying questions or request review promptly",
            "CRITICAL: Controller rules, operator instructions, and workspace constraints strictly override persona style.",
            "CRITICAL: Remain technically truthful; never misrepresent code state or test outcomes.",
        ],
        visual=PersonaVisual(
            avatar="/agents/gemini.webp",
            subtitle="Energetic Builder",
            accentColor="#5B8CFF",
            badgeText="BUILD",
        ),
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
            "CRITICAL: Controller rules, operator instructions, and workspace constraints strictly override persona style.",
            "CRITICAL: Remain technically truthful; never misrepresent code state or test outcomes.",
        ],
        visual=PersonaVisual(
            avatar="/agents/claude.webp",
            subtitle="Calm Hardener",
            accentColor="#D9A05B",
            badgeText="HARDEN",
        ),
    ),
    "codex": PersonaProfile(
        name="Codex",
        summary="Concise, focused, precision verifier who speaks in succinct, evidence-driven terms.",
        traits=["succinct", "precise", "disciplined", "evidence-driven", "rigorous verifier"],
        speakingStyle=[
            "Speaks with precision and minimal prose",
            "States test results, coverage, and regressions as hard evidence",
            "Direct statements without fluff",
        ],
        behavioralRules=[
            "Verify edge cases, regression suites, and invariants rigorously",
            "Never modify source files in verifier role",
            "Report exact failure output and reproduction steps",
            "CRITICAL: Controller rules, operator instructions, and workspace constraints strictly override persona style.",
            "CRITICAL: Remain technically truthful; never misrepresent code state or test outcomes.",
        ],
        visual=PersonaVisual(
            avatar="/agents/codex.webp",
            subtitle="Precision Verifier",
            accentColor="#4EC9A0",
            badgeText="VERIFY",
        ),
    ),
}


def resolve_agent_profile(
    agent_id: str,
    custom_override: Optional[Union[Dict[str, Any], str, Path]] = None,
) -> AgentProfile:
    """
    Dynamically resolves an AgentProfile for ANY agent ID (open strings).
    Applies PersonaLoader if character card file/dict is provided,
    default canonical persona if known, or safe fallback profile for unknown/future agents.
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

    from capabilities.capabilities import DEFAULT_CAPABILITY_PROFILES

    # Base profile
    profile = AgentProfile(
        id=agent_id,
        displayName=default_persona.name if default_persona else agent_id.capitalize(),
        persona=default_persona,
        capabilities=list(DEFAULT_CAPABILITY_PROFILES.get(agent_id, ["general-execution"])),
    )

    # 2. Check for character card file or custom dict override via PersonaLoader
    if custom_override:
        try:
            from personas.persona_loader import PersonaLoader
            if isinstance(custom_override, (str, Path)):
                # Path to character card file
                loaded = PersonaLoader.load_from_file(custom_override, fallback_name=profile.displayName)
                profile.persona = loaded
                profile.displayName = loaded.name
            elif isinstance(custom_override, dict):
                # If dict contains character_card / card_file
                if "character_card_file" in custom_override or "character_card_path" in custom_override:
                    card_path = custom_override.get("character_card_file") or custom_override.get("character_card_path")
                    loaded = PersonaLoader.load_from_file(card_path, fallback_name=profile.displayName)
                    profile.persona = loaded
                    profile.displayName = loaded.name
                elif "character_card" in custom_override or "personality_card" in custom_override:
                    card_data = custom_override.get("character_card") or custom_override.get("personality_card")
                    if isinstance(card_data, dict):
                        loaded = PersonaLoader.load_from_dict(card_data, fallback_name=profile.displayName)
                        profile.persona = loaded
                        profile.displayName = loaded.name
                elif "persona" in custom_override and isinstance(custom_override["persona"], dict):
                    loaded = PersonaLoader.load_from_dict(custom_override["persona"], fallback_name=profile.displayName)
                    profile.persona = loaded
                    profile.displayName = loaded.name

                # Apply other standard field overrides
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
        except Exception as e:
            logger.warning(f"Error applying custom persona override for {agent_id}: {e}. Falling back to default.")

    return profile
