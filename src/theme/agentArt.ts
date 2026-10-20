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
  /** Character sheet (contains text): cropped to the figure for dossier panes, never shown whole. */
  card: string;
  avatarFocus: Focus;
  cardFocus: Focus;
}

export const AGENT_ART: Record<string, AgentArt> = {
  claude: {
    avatar: '/portrait/claude.png',
    card: '/portrait/claude.png',
    avatarFocus: { x: 0.5, y: 0.4, zoom: 1.05 },
    cardFocus: { x: 0.36, y: 0.27, zoom: 2.4 }
  },
  codex: {
    avatar: '/portrait/codex.png',
    card: '/portrait/codex.png',
    avatarFocus: { x: 0.5, y: 0.4, zoom: 1.05 },
    cardFocus: { x: 0.3, y: 0.22, zoom: 3.0 }
  },
  gemini: {
    avatar: '/portrait/gemini.png',
    card: '/portrait/gemini.png',
    avatarFocus: { x: 0.5, y: 0.4, zoom: 1.05 },
    cardFocus: { x: 0.27, y: 0.2, zoom: 3.0 }
  }
};

/** Hermes orchestrator emblem, used for empty states. Not an agent card. */
export const HERMES_ART = '/portrait/hermes.png';

export function agentArt(id: string | null | undefined): AgentArt | undefined {
  if (!id) return undefined;
  return AGENT_ART[id.toLowerCase()];
}
