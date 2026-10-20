import { UNKNOWN } from '../../api/unknown';

function parseMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Elapsed time of a job from its own timestamps. A running job is measured to `nowMs`;
 * a finished job keeps its fixed duration. Unknown when the start is missing or the times are inconsistent.
 */
export function formatElapsed(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
  nowMs: number
): string {
  const start = parseMs(startedAt);
  if (start === null) return UNKNOWN;
  const end = parseMs(completedAt) ?? nowMs;
  const totalS = Math.floor((end - start) / 1000);
  if (totalS < 0) return UNKNOWN;

  const h = Math.floor(totalS / 3600);
  const m = Math.floor((totalS % 3600) / 60);
  const s = totalS % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}
