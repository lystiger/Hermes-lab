/**
 * Agent art and the focal point used to crop it. Crops show the face and no sheet text. Swapping in cut-out
 * assets later only changes this file; components read it through <FocalImage>.
 *
 * focus: the point of the image to keep in view, as fractions of its width and height, and how far to zoom in
 * around it. zoom 1 shows the whole image.
 */
export interface Focus {
  x: number;
  y: number;
  zoom: number;
}

export interface AgentArt {
  /** Square portrait used for roster thumbnails. */
  avatar: string;
  /** Character art for dossier panes. The portrait files are clean figures with no text, so the card may show all of them. */
  card: string;
  avatarFocus: Focus;
  cardFocus: Focus;
}

export const AGENT_ART: Record<string, AgentArt> = {
  claude: {
    avatar: '/portrait/claude.png',
    card: '/portrait/claude.png',
    avatarFocus: { x: 0.5, y: 0.4, zoom: 1.05 },
    cardFocus: { x: 0.5, y: 0.35, zoom: 1 }
  },
  codex: {
    avatar: '/portrait/codex.png',
    card: '/portrait/codex.png',
    avatarFocus: { x: 0.5, y: 0.4, zoom: 1.05 },
    cardFocus: { x: 0.5, y: 0.35, zoom: 1 }
  },
  gemini: {
    avatar: '/portrait/gemini.png',
    card: '/portrait/gemini.png',
    avatarFocus: { x: 0.5, y: 0.4, zoom: 1.05 },
    cardFocus: { x: 0.5, y: 0.35, zoom: 1 }
  }
};

/**
 * Character art (the anime-style persona portraits). Off: the files stay in public/portrait and
 * the UI uses its plain initials marks instead. Turning it back on restores the art everywhere.
 * The anime style lives on its own branch, style/anime-persona.
 */
export const PERSONA_ART_ENABLED = false;

/** Decorative design elements (the animated sidebar cube). Off hides them; no asset is removed. */
export const DESIGN_ART_ENABLED = false;

/** Hermes orchestrator emblem, used for empty states. Not an agent card. */
export const HERMES_ART: string | undefined = PERSONA_ART_ENABLED ? '/portrait/hermes.png' : undefined;

export function agentArt(id: string | null | undefined): AgentArt | undefined {
  if (!PERSONA_ART_ENABLED || !id) return undefined;
  return AGENT_ART[id.toLowerCase()];
}
