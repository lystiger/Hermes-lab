import { JobDetail, PipelineStepState } from '../../api/types';
import { mapPhaseState } from '../../api/adapters/httpAdapter';

/** One phase of a job on the run timeline. Times are epoch ms; null when Hermes did not report them. */
export interface TimelineRow {
  key: string;
  order: number;
  name: string;
  /** The phase's role from the sprint spec (builder, hardener, verifier, ...). Agents have no fixed role. */
  role?: string;
  agentId?: string;
  state: PipelineStepState;
  startMs: number | null;
  endMs: number | null;
  commitSha?: string;
  /** Hermes replaced this phase with a repair or replan. */
  superseded?: boolean;
}

/** A phase is shown by its prompt file name without the folder or extension; the full name is in the tooltip. */
export function phaseLabel(name: string): string {
  return name.split('/').pop()?.replace(/\.md$/, '') ?? name;
}

function parseMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Rows in spec order. Hermes job phases are the source (they carry role, order and times);
 * a detail without phases falls back to its execution graph, which has no times.
 */
export function timelineRows(job: Pick<JobDetail, 'phases' | 'executionGraph'>): TimelineRow[] {
  if (job.phases && job.phases.length > 0) {
    return [...job.phases]
      .sort((a, b) => a.order - b.order)
      .map((p) => {
        const startMs = parseMs(p.startedAt);
        const endMs = parseMs(p.completedAt) ?? (startMs !== null && p.durationMs ? startMs + p.durationMs : null);
        return {
          key: p.id || `phase-${p.order}`,
          order: p.order,
          name: p.name,
          role: p.role || undefined,
          agentId: p.agentId,
          state: mapPhaseState(p.status),
          startMs,
          endMs,
          commitSha: p.commitSha,
          superseded: p.status === 'SUPERSEDED'
        };
      });
  }
  return (job.executionGraph ?? []).map((s, idx) => ({
    key: s.id || `step-${idx}`,
    order: idx + 1,
    name: s.phase,
    role: s.note,
    agentId: s.agentId,
    state: s.state,
    startMs: null,
    endMs: null
  }));
}

/** Time window of the timeline: first phase start to last phase end, or `nowMs` while anything runs. */
export function timelineWindow(rows: TimelineRow[], nowMs: number): { startMs: number; endMs: number } | null {
  const starts = rows.map((r) => r.startMs).filter((v): v is number => v !== null);
  if (starts.length === 0) return null;
  const startMs = Math.min(...starts);
  const running = rows.some((r) => r.startMs !== null && r.endMs === null);
  const ends = rows.map((r) => r.endMs).filter((v): v is number => v !== null);
  const endMs = Math.max(startMs + 1000, running ? nowMs : 0, ...ends);
  return { startMs, endMs };
}

export function formatDuration(ms: number): string {
  const totalS = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(totalS / 3600);
  const m = Math.floor((totalS % 3600) / 60);
  const s = totalS % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}
