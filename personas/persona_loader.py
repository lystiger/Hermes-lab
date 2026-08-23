import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from personas.persona import PersonaProfile, PersonaVisual

logger = logging.getLogger("hermes.persona_loader")

# Forbidden privilege keys that must NEVER be loaded or parsed from character cards
FORBIDDEN_PRIVILEGE_KEYS = {
    "permissions",
    "tools",
    "shell",
    "filesystem",
    "sudo",
    "privileges",
    "allowlist",
    "allowed_commands",
    "capabilities_grant",
    "auth",
    "token",
    "api_key",
    "workspace_scope",
}


class PersonaLoader:
    """
    Safe parser and loader for character cards and external persona definitions.
    Treats all incoming data as untrusted prompt-layer content.
    Prevents privilege escalation and malformed crash loops.
    """

    @staticmethod
    def sanitize_untrusted_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Strips out forbidden security and privilege keys from imported character cards."""
        clean: Dict[str, Any] = {}
        for k, v in raw_data.items():
            if k.lower() in FORBIDDEN_PRIVILEGE_KEYS:
                logger.warning("Ignored unauthorized privilege key in character card: %s", k)
                continue
            clean[k] = v
        return clean

    @classmethod
    def load_from_dict(cls, data: Dict[str, Any], fallback_name: str = "Operative") -> PersonaProfile:
        try:
            clean_data = cls.sanitize_untrusted_data(data)

            name = str(clean_data.get("name") or clean_data.get("character_name") or fallback_name)
            summary = str(clean_data.get("summary") or clean_data.get("description") or "Autonomous system agent.")

            # Traits
            raw_traits = clean_data.get("traits") or clean_data.get("personality") or []
            if isinstance(raw_traits, str):
                traits = [t.strip() for t in raw_traits.split(",") if t.strip()]
            elif isinstance(raw_traits, list):
                traits = [str(t) for t in raw_traits]
            else:
                traits = []

            # Speaking Style
            raw_style = clean_data.get("speakingStyle") or clean_data.get("speaking_style") or clean_data.get("mes_example") or []
            if isinstance(raw_style, str):
                speaking_style = [s.strip() for s in raw_style.split("\n") if s.strip()]
            elif isinstance(raw_style, list):
                speaking_style = [str(s) for s in raw_style]
            else:
                speaking_style = []

            # Behavioral Rules
            raw_rules = clean_data.get("behavioralRules") or clean_data.get("behavioral_rules") or clean_data.get("scenario") or []
            if isinstance(raw_rules, str):
                behavioral_rules = [r.strip() for r in raw_rules.split("\n") if r.strip()]
            elif isinstance(raw_rules, list):
                behavioral_rules = [str(r) for r in raw_rules]
            else:
                behavioral_rules = []

            # Relationships
            raw_rel = clean_data.get("relationships") or {}
            relationships = {str(k): str(v) for k, v in raw_rel.items()} if isinstance(raw_rel, dict) else {}

            # Visual
            raw_visual = clean_data.get("visual") or {}
            avatar = str(raw_visual.get("avatar") or clean_data.get("avatar") or "") or None
            subtitle = str(raw_visual.get("subtitle") or clean_data.get("subtitle") or "") or None
            visual = PersonaVisual(avatar=avatar, subtitle=subtitle) if (avatar or subtitle) else None

            system_fragment = str(clean_data.get("systemPromptFragment") or clean_data.get("system_prompt") or "") or None

            return PersonaProfile(
                name=name,
                summary=summary,
                traits=traits,
                speakingStyle=speaking_style,
                behavioralRules=behavioral_rules,
                relationships=relationships,
                systemPromptFragment=system_fragment,
                visual=visual,
            )
        except Exception as e:
            logger.warning("Failed parsing character card dictionary, using fallback persona: %s", e)
            return PersonaProfile(
                name=fallback_name,
                summary="Autonomous system agent (fallback persona).",
                traits=["focused", "resilient"],
                behavioralRules=["Remain technically accurate and adhere to runtime constraints."],
            )

    @classmethod
    def load_from_file(cls, file_path: Union[str, Path], fallback_name: str = "Operative") -> PersonaProfile:
        path = Path(file_path)
        if not path.exists():
            logger.warning("Character card file not found: %s", path)
            return PersonaProfile(
                name=fallback_name,
                summary="Autonomous system agent (fallback).",
            )

        try:
            text = path.read_text(encoding="utf-8")
            # Try JSON first
            if text.strip().startswith("{"):
                data = json.loads(text)
                return cls.load_from_dict(data, fallback_name=fallback_name)
            else:
                # Markdown / text fallback parsing
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                summary = lines[0] if lines else "Autonomous operative."
                return PersonaProfile(
                    name=fallback_name,
                    summary=summary,
                    traits=["adaptive"],
                    speakingStyle=lines[1:5],
                    behavioralRules=["Follow runtime controller instructions."],
                )
        except Exception as e:
            logger.warning("Malformed character card at %s, falling back safely: %s", path, e)
            return PersonaProfile(
                name=fallback_name,
                summary="Autonomous system agent (safe fallback).",
            )
