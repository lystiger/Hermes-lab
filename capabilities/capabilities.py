import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger("hermes.capabilities")


@dataclass
class Capability:
    """Open-string capability descriptor."""
    id: str
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capability":
        return cls(
            id=str(data.get("id", "")).strip(),
            description=data.get("description"),
            tags=data.get("tags") or [],
            metadata=data.get("metadata") or {},
        )


@dataclass
class CapabilityRef:
    """Reference to a capability possessed or required by an actor."""
    id: str
    proficiency: Optional[Union[int, float, str]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_value(cls, val: Any) -> "CapabilityRef":
        if isinstance(val, str):
            return cls(id=val.strip())
        if isinstance(val, dict):
            return cls(
                id=str(val.get("id", "")).strip(),
                proficiency=val.get("proficiency"),
                metadata=val.get("metadata"),
            )
        if isinstance(val, CapabilityRef):
            return val
        return cls(id=str(val).strip())


# Initial default capabilities for standard agents
DEFAULT_CAPABILITY_PROFILES: Dict[str, List[str]] = {
    "gemini": [
        "implementation",
        "code.python",
        "code.typescript",
        "backend.fastapi",
        "frontend.react",
        "testing.unit",
    ],
    "claude": [
        "review.code",
        "review.architecture",
        "review.concurrency",
        "code.python",
        "frontend.react",
        "documentation",
        "git.inspect",
        "repo.read",
    ],
    "codex": [
        "verification",
        "review.correctness",
        "testing.unit",
        "testing.integration",
        "git.inspect",
        "repo.read",
    ],
    "antigravity": [
        "implementation",
        "code.python",
        "code.typescript",
        "backend.fastapi",
        "frontend.react",
        "review.architecture",
        "testing.unit",
        "testing.integration",
        "verification",
        "documentation",
        "git.inspect",
        "repo.read",
    ],
}


class CapabilityRegistry:
    """
    Central, provider-agnostic registry for actor capabilities and deterministic capability matching.
    """

    def __init__(self):
        self._actors: Dict[str, Any] = {}
        self._capabilities: Dict[str, Capability] = {}

    def register_capability(self, cap: Union[Capability, str, Dict[str, Any]]) -> Capability:
        if isinstance(cap, str):
            c_obj = Capability(id=cap.strip())
        elif isinstance(cap, dict):
            c_obj = Capability.from_dict(cap)
        else:
            c_obj = cap
        self._capabilities[c_obj.id] = c_obj
        return c_obj

    def register_actor(self, profile: Any) -> None:
        """Registers an actor profile (AgentProfile, SubagentProfile, or dict)."""
        if isinstance(profile, dict):
            actor_id = profile.get("id")
        else:
            actor_id = getattr(profile, "id", None)
        if not actor_id:
            raise ValueError("Actor profile must have an 'id'")
        self._actors[actor_id] = profile

    def unregister_actor(self, actor_id: str) -> Optional[Any]:
        return self._actors.pop(actor_id, None)

    def get_actor(self, actor_id: str) -> Optional[Any]:
        return self._actors.get(actor_id)

    def list_actors(self) -> List[Any]:
        return list(self._actors.values())

    def get_actor_capabilities(self, actor_id: str) -> List[str]:
        profile = self.get_actor(actor_id)
        if not profile:
            if actor_id in DEFAULT_CAPABILITY_PROFILES:
                return list(DEFAULT_CAPABILITY_PROFILES[actor_id])
            return []
        if isinstance(profile, dict):
            raw_caps = profile.get("capabilities", []) or []
        else:
            raw_caps = getattr(profile, "capabilities", []) or []
        res = []
        for c in raw_caps:
            if isinstance(c, str):
                res.append(c.strip())
            elif isinstance(c, dict) and "id" in c:
                res.append(str(c["id"]).strip())
            elif hasattr(c, "id"):
                res.append(str(c.id).strip())
        return res

    def list_available_capabilities(self) -> List[str]:
        """Returns all distinct capabilities possessed by currently registered/dispatchable actors."""
        caps = set(self._capabilities.keys())
        for actor_id in self._actors:
            caps.update(self.get_actor_capabilities(actor_id))
        return sorted(list(caps))

    def actor_satisfies(self, actor_id: str, required_capabilities: Sequence[str]) -> bool:
        """
        Determines whether a specific actor satisfies all required capabilities.
        Deterministic check: actor must possess every required capability.
        """
        if not required_capabilities:
            return True
        actor_caps = set(self.get_actor_capabilities(actor_id))
        for req in required_capabilities:
            req_clean = req.strip()
            if req_clean not in actor_caps:
                return False
        return True

    def find_actors(
        self,
        required_capabilities: Sequence[str],
        preferred_actors: Optional[Sequence[str]] = None,
        excluded_actors: Optional[Sequence[str]] = None,
        available_actors: Optional[Sequence[str]] = None,
    ) -> List[Tuple[Any, float, Dict[str, Any]]]:
        """
        Finds and ranks all eligible actors satisfying required capabilities.
        Ranking:
        1. Eliminate unavailable actors (if available_actors is specified).
        2. Eliminate excluded actors.
        3. Eliminate actors lacking any required capability.
        4. Apply preferred actor boost.
        5. Deterministic tie-breaking by preferred index, then actor ID.
        """
        req_set = [r.strip() for r in required_capabilities if r.strip()]
        excluded_set = {e.strip() for e in (excluded_actors or []) if e.strip()}
        pref_list = [p.strip() for p in (preferred_actors or []) if p.strip()]
        avail_set = {a.strip() for a in available_actors} if available_actors is not None else None

        results = []

        for actor_id, profile in self._actors.items():
            # 1. Availability check
            if avail_set is not None and actor_id not in avail_set:
                continue

            # 2. Excluded check
            if actor_id in excluded_set:
                continue

            # 3. Capability requirement check
            actor_caps = set(self.get_actor_capabilities(actor_id))
            matched = [c for c in req_set if c in actor_caps]
            missing = [c for c in req_set if c not in actor_caps]

            if missing:
                # Ineligible
                continue

            # 4. Score calculation
            score = 1.0
            if actor_id in pref_list:
                pref_index = pref_list.index(actor_id)
                score += 10.0 - (pref_index * 0.1)

            match_info = {
                "matchedCapabilities": matched,
                "missingCapabilities": missing,
                "preferred": actor_id in pref_list,
                "totalCapabilities": len(actor_caps),
            }
            results.append((profile, score, match_info))

        # 5. Deterministic tie-break sorting: highest score first, then alphabetical actor.id
        results.sort(
            key=lambda item: (
                -item[1],
                item[0].get("id", "") if isinstance(item[0], dict) else getattr(item[0], "id", str(item[0])),
            )
        )
        return results

    def select_actor(
        self,
        required_capabilities: Sequence[str],
        preferred_actors: Optional[Sequence[str]] = None,
        excluded_actors: Optional[Sequence[str]] = None,
        available_actors: Optional[Sequence[str]] = None,
        request_id: Optional[str] = None,
        publisher: Any = None,
        job_id: Optional[str] = None,
    ) -> Any:
        """
        Selects the single best actor deterministically.
        Returns a DelegationDecision.
        """
        from capabilities.delegation import DelegationDecision

        req_clean = [r.strip() for r in required_capabilities if r.strip()]

        if publisher:
            publisher.publish(
                source_id="capability_registry",
                source_kind="runtime",
                kind="capability.match_requested",
                detail=f"Matching actor for capabilities: {', '.join(req_clean)}",
                job_id=job_id,
                metadata={
                    "requestId": request_id,
                    "requiredCapabilities": req_clean,
                    "preferredActors": preferred_actors or [],
                    "excludedActors": excluded_actors or [],
                },
            )

        ranked = self.find_actors(
            required_capabilities=req_clean,
            preferred_actors=preferred_actors,
            excluded_actors=excluded_actors,
            available_actors=available_actors,
        )

        if not ranked:
            logger.info("No actor found satisfying required capabilities: %s", req_clean)
            if publisher:
                publisher.publish(
                    source_id="capability_registry",
                    source_kind="runtime",
                    kind="capability.no_match",
                    detail=f"No actor found satisfying required capabilities: {', '.join(req_clean)}",
                    job_id=job_id,
                    metadata={
                        "requestId": request_id,
                        "requiredCapabilities": req_clean,
                    },
                )
            return DelegationDecision(
                requestId=request_id or "",
                selectedActorId=None,
                status="no_match",
                reason=f"No registered/available actor satisfies all required capabilities: {', '.join(req_clean)}",
                requiredCapabilities=req_clean,
                matchedCapabilities=[],
                missingCapabilities=req_clean,
            )

        best_profile, best_score, match_info = ranked[0]
        selected_id = getattr(best_profile, "id", str(best_profile))

        if publisher:
            publisher.publish(
                source_id="capability_registry",
                source_kind="runtime",
                kind="capability.match_selected",
                detail=f"Selected actor {selected_id} (score: {best_score:.2f}) for capabilities: {', '.join(req_clean)}",
                job_id=job_id,
                metadata={
                    "requestId": request_id,
                    "selectedActorId": selected_id,
                    "score": best_score,
                    "matchedCapabilities": match_info.get("matchedCapabilities", []),
                },
            )

        return DelegationDecision(
            requestId=request_id or "",
            selectedActorId=selected_id,
            status="selected",
            reason=f"Selected actor '{selected_id}' satisfying all {len(req_clean)} required capabilities.",
            requiredCapabilities=req_clean,
            matchedCapabilities=match_info.get("matchedCapabilities", []),
            missingCapabilities=[],
            metadata={"score": best_score},
        )


def create_default_capability_registry() -> CapabilityRegistry:
    """Factory creating a pre-populated CapabilityRegistry with default agent profiles."""
    from personas.persona import resolve_agent_profile

    registry = CapabilityRegistry()
    for agent_id, caps in DEFAULT_CAPABILITY_PROFILES.items():
        profile = resolve_agent_profile(agent_id)
        profile.capabilities = list(caps)
        registry.register_actor(profile)
    return registry


default_capability_registry = create_default_capability_registry()
