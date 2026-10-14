import { describeError } from '../../api/mapping';
import { JobDetail, TraceEvent } from '../../api/types';

export interface JobTraceRow {
  event: TraceEvent;
  /** `stored` when it came from the durable history, `live` when only the live buffer had it. */
  origin: 'stored' | 'live';
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
    rows.push({ event, origin: 'stored' });
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
  const verification = job.verification as { status?: unknown } | null | undefined;
  if (verification && typeof verification.status === 'string') {
    lines.push(`verification ${verification.status}`);
  }

  return {
    headline: `Job ${job.status.toLowerCase()}${job.phases?.length ? ` after ${job.phases.length} phase(s)` : ''}`,
    lines: lines.length > 0 ? lines : ['Hermes reported no error detail for this job.']
  };
}
