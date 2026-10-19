/**
 * Per-agent accents. This file is the one place where agent identity maps to a colour.
 * Each value is a CSS variable declared in src/styles/globals.css; the lead replaces the variable values
 * with palettes extracted from the character art, and components pick them up without code changes.
 */
export const AGENT_ACCENT_VARS: Record<string, string> = {
  claude: 'var(--lys-agent-claude)',
  codex: 'var(--lys-agent-codex)',
  gemini: 'var(--lys-agent-gemini)',
  agy: 'var(--lys-agent-gemini)',
  hermes: 'var(--lys-agent-hermes)'
};

/** Accent for a known agent or system actor id, or undefined when the id has no assigned accent. */
export function agentAccent(id: string | null | undefined): string | undefined {
  if (!id) return undefined;
  return AGENT_ACCENT_VARS[id.toLowerCase()];
}

/** Neutral accent for anything without an assigned identity. */
export const NEUTRAL_ACCENT = 'var(--lys-text-muted)';

/**
 * Colour for an actor as the console shows it: a known agent's variable wins, so the lead's palette applies
 * even when the backend sends its own hex; otherwise the backend's colour, then the neutral fallback.
 */
export function actorAccent(id: string | null | undefined, backendColor?: string | null): string {
  return agentAccent(id) || backendColor || NEUTRAL_ACCENT;
}
