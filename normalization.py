def normalize_agent_id(agent_id: str) -> str:
    """
    Centralized canonical normalization for agent identifiers across LysStack & Hermes.
    Aligns runner naming (e.g. 'antigravity') with console naming ('gemini').
    """
    if not agent_id:
        return "unknown"
    normalized = str(agent_id).strip().lower()
    if normalized in {"antigravity", "gemini", "agy"}:
        return "gemini"
    return normalized
