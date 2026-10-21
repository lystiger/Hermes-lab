/** How full a chat's context is, from the last call's real token counts. */

export interface ChatUsage {
  context_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  output_tokens: number;
  context_window: number | null;
  measured_at?: string;
}

export type ContextLevel = 'ok' | 'warn' | 'high';

/** Above this share of the window, the page says the chat is getting full. */
export const WARN_SHARE = 0.6;
/** Above this share, the page asks you to compact now. */
export const HIGH_SHARE = 0.85;

export interface ContextView {
  level: ContextLevel;
  percent: number;
  cachePercent: number;
  label: string;
}

/** The meter for a chat, or null when no call has been measured yet. */
export function contextView(usage: ChatUsage | null | undefined): ContextView | null {
  if (!usage || !usage.context_window || usage.context_window <= 0) return null;
  const share = usage.context_tokens / usage.context_window;
  const level: ContextLevel = share >= HIGH_SHARE ? 'high' : share >= WARN_SHARE ? 'warn' : 'ok';
  const percent = Math.min(100, Math.round(share * 100));
  const cachePercent = usage.context_tokens > 0
    ? Math.round((usage.cache_read_tokens / usage.context_tokens) * 100)
    : 0;
  return {
    level,
    percent,
    cachePercent,
    label: `Context ${percent}% · ${formatTokens(usage.context_tokens)} of ${formatTokens(usage.context_window)} · cache ${cachePercent}%`,
  };
}

export function formatTokens(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${Math.round(count / 1_000)}k`;
  return String(count);
}
