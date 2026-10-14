import { describeError } from '../../api/mapping';
import { JobDetail, TraceEvent } from '../../api/types';

export interface JobTraceRow {
  event: TraceEvent;
  /**
   * `stored`: canonical durable envelope. `bus`: in-memory event bus fallback, not durable.
   * `live`: only the live SSE buffer had it.
   */
  origin: 'stored' | 'bus' | 'live';
}

/**
 * Durable history first, then live events that are not already in it, newest first.
 * Events are matched by id, so one event is never shown twice.
 */
export function mergeJobEvents(stored: TraceEvent[], live: TraceEvent[]): JobTraceRow[] {
  const seen = new Set<string>();
  const rows: JobTraceRow[] = [];
  for (const event of stored) {
    if (seen.has(event.id)) continue;
    seen.add(event.id);
    rows.push({ event, origin: event.origin === 'bus' ? 'bus' : 'stored' });
  }
  for (const event of live) {
    if (seen.has(event.id)) continue;
    seen.add(event.id);
    rows.push({ event, origin: 'live' });
  }
  return rows.sort((a, b) => b.event.rawTs - a.event.rawTs);
}

export interface FailureExplanation {
  headline: string;
  lines: string[];
}

/**
 * Why a job stopped, using only what Hermes reported on the job, its phases and its errors.
 * Returns null for a job that is not in a failed, blocked or cancelled state.
 */
export function explainFailure(job: JobDetail): FailureExplanation | null {
  if (!['FAILED', 'BLOCKED', 'CANCELLED'].includes(job.status)) return null;

  const lines: string[] = [];
  if (job.blockedReason) lines.push(`blocked: ${describeError(job.blockedReason)}`);
  for (const phase of job.phases ?? []) {
    if (phase.status === 'FAILED' || phase.status === 'BLOCKED') {
      lines.push(`phase ${phase.name} ${phase.status.toLowerCase()}${phase.detail ? `: ${phase.detail}` : ''}`);
    }
  }
  for (const err of job.errors ?? []) {
    const text = describeError(err);
    if (text) lines.push(text);
  }
  const verification = job.verification as { status?: unknown; results?: unknown } | null | undefined;
  if (verification && typeof verification.status === 'string') {
    lines.push(`verification ${verification.status}`);
    for (const line of verificationResultLines(verification.results)) lines.push(`verification result · ${line}`);
  }

  return {
    headline: `Job ${job.status.toLowerCase()}${job.phases?.length ? ` after ${job.phases.length} phase(s)` : ''}`,
    lines: lines.length > 0 ? lines : ['Hermes reported no error detail for this job.']
  };
}

/**
 * One line of readable text for a result or attempt record of unknown shape: its primitive fields as
 * `key: value`, nested values as short JSON. Nothing is summarised or counted that the record does not say.
 */
export function describeRecord(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value !== 'object') return String(value);
  const parts: string[] = [];
  for (const [key, v] of Object.entries(value as Record<string, unknown>)) {
    if (v === null || v === undefined) continue;
    const text = typeof v === 'object' ? JSON.stringify(v) : String(v);
    parts.push(`${key}: ${text.length > 160 ? `${text.slice(0, 157)}…` : text}`);
  }
  return parts.join(' · ');
}

/** Verification results as a list of readable lines. Accepts an array, a single record, or a plain string. */
export function verificationResultLines(results: unknown): string[] {
  if (results === null || results === undefined) return [];
  if (Array.isArray(results)) return results.map((r) => describeRecord(r)).filter(Boolean);
  if (typeof results === 'object') return [describeRecord(results)].filter(Boolean);
  return [String(results)];
}
