import React, { useRef } from 'react';
import { AgentSummary, Job } from '../../api/types';
import { ACTIVE_JOB_STATUSES } from '../../api/adapters/httpAdapter';
import { useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { CopyId } from '../../components/CopyId';
import { ErrorState, LoadingState, Freshness, UNKNOWN, StaleNotice } from '../../components/DataStates';
import { useArrowNavigation } from '../../components/keyboard';
import { Card } from '../../components/Card';
import { HERMES_ART } from '../../theme/agentArt';
import { formatDateTime } from '../time/format';

/**
 * Board columns follow the real job statuses. Each job appears in exactly one column. Status is shown by colour
 * and by shape (research §2.1): every column header carries a glyph as well as its tone.
 */
export const BOARD_GROUPS = [
  { id: 'RUNNING', label: 'Running', glyph: '◆', statuses: ACTIVE_JOB_STATUSES, tone: 'var(--lys-status-success)' },
  { id: 'BLOCKED', label: 'Blocked', glyph: '■', statuses: ['BLOCKED'], tone: 'var(--lys-status-warning)' },
  { id: 'QUEUED', label: 'Queued', glyph: '○', statuses: ['QUEUED', 'CLAIMED'], tone: 'var(--lys-text-muted)' },
  { id: 'FAILED', label: 'Failed', glyph: '✕', statuses: ['FAILED'], tone: 'var(--lys-status-danger)' },
  { id: 'COMPLETED', label: 'Completed', glyph: '✓', statuses: ['COMPLETED'], tone: 'var(--lys-text-faint)' },
  { id: 'CANCELLED', label: 'Cancelled', glyph: '⊘', statuses: ['CANCELLED'], tone: 'var(--lys-text-faint)' }
];

const PRIORITY_COLOR: Record<string, string> = {
  P0: 'var(--lys-status-danger)',
  P1: 'var(--lys-status-warning)',
  P2: 'var(--lys-text-muted)',
  P3: 'var(--lys-text-faint)'
};

/** The board column a job belongs to. Unrecognised statuses get their own column, never a guessed one. */
export function groupOf(job: Job): { id: string; label: string; tone: string; glyph: string } {
  const known = BOARD_GROUPS.find((g) => g.statuses.includes(job.status));
  return known ?? { id: `OTHER:${job.status}`, label: `Other · ${job.status}`, tone: 'var(--lys-text-muted)', glyph: '?' };
}

export const MissionBoard: React.FC<{
  jobs: Job[];
  loading: boolean;
  error: unknown;
  stale?: boolean;
  updatedAt: number | null;
  onRetry: () => void;
  onOpen: (jobId: string) => void;
}> = ({ jobs, loading, error, stale = false, updatedAt, onRetry, onOpen }) => {
  const { agents } = useAgents();
  const listRef = useRef<HTMLDivElement>(null);
  useArrowNavigation(listRef);

  const counts = new Map<string, number>();
  for (const j of jobs) counts.set(groupOf(j).id, (counts.get(groupOf(j).id) ?? 0) + 1);
  const otherColumns = jobs
    .map((j) => groupOf(j))
    .filter((g) => g.id.startsWith('OTHER:'))
    .filter((g, i, all) => all.findIndex((x) => x.id === g.id) === i)
    .map((g) => ({ ...g, statuses: [] as string[] }));
  const columns = [...BOARD_GROUPS, ...otherColumns];

  return (
    <section aria-label="Mission board" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[12px] text-lys-muted">
          {jobs.length === 0 && !loading && !error ? 'No jobs in the latest sample from GET /jobs.' : `${jobs.length} jobs in the latest sample`}
        </div>
        <Freshness at={updatedAt} />
      </div>

      {Boolean(stale) && <StaleNotice label="Job queue" error={error} onRetry={onRetry} />}
      {loading && jobs.length === 0 && <Card><LoadingState label="Loading jobs…" /></Card>}
      {Boolean(error) && jobs.length === 0 && <Card><ErrorState label="Job queue" error={error} onRetry={onRetry} /></Card>}

      <div ref={listRef} className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6 gap-4 items-start">
        {columns.map((c) => {
          const n = counts.get(c.id) ?? 0;
          const colJobs = jobs.filter((j) => groupOf(j).id === c.id);
          return (
            <div key={c.id} role="list" aria-label={`${c.label} jobs`} className="flex flex-col gap-3 min-w-0">
              <div className="bg-lys-surface-1 border-t-[3px] px-3 py-2.5 flex items-center justify-between" style={{ borderTopColor: c.tone }}>
                <span className="flex items-center gap-2 text-[12px] tracking-wider uppercase" style={{ color: c.tone }}>
                  <span aria-hidden="true">{c.glyph}</span>
                  {c.label}
                </span>
                <span className="font-display text-[20px] font-semibold text-lys-primary lys-metric">{n}</span>
              </div>
              {colJobs.length === 0 ? (
                <div className="border border-dashed border-lys-subtle min-h-[220px] flex items-center justify-center text-[12px] text-lys-faint">none</div>
              ) : (
                colJobs.map((j) => <JobCard key={j.id} job={j} tone={c.tone} agentsList={agents} onOpen={onOpen} />)
              )}
            </div>
          );
        })}
      </div>

      {jobs.length === 0 && !loading && !error && (
        <div className="flex justify-center py-6">
          <img src={HERMES_ART} alt="" aria-hidden="true" className="h-20 w-auto opacity-70" />
        </div>
      )}
      {jobs.length > 0 && <p className="text-[11px] text-lys-faint">↑ ↓ move between jobs · Enter opens the job inspector</p>}
    </section>
  );
};

const JobCard: React.FC<{
  job: Job;
  tone: string;
  agentsList: AgentSummary[];
  onOpen: (jobId: string) => void;
}> = ({ job, tone, agentsList, onOpen }) => {
  const failed = job.status === 'FAILED';
  const assigned = job.assignedAgentIds.map((id) => resolveActorPresentation(id, agentsList).displayName);
  const progress = typeof job.progress === 'number' ? Math.max(0, Math.min(1, job.progress)) : null;

  return (
    <Card accent={tone} as="div" label={`Job ${job.id}`}>
      <div role="listitem" className="p-3.5 flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {job.priority && PRIORITY_COLOR[job.priority] && (
            <span className="text-[10px] tracking-wider px-1.5 py-0.5 border" style={{ color: PRIORITY_COLOR[job.priority], borderColor: PRIORITY_COLOR[job.priority] }}>
              {job.priority}
            </span>
          )}
          <CopyId value={job.id} className="text-lys-faint text-[11px]" />
        </div>

        <button type="button" data-nav-item onClick={() => onOpen(job.id)} className="text-left text-[15px] font-semibold text-lys-primary hover:underline cursor-pointer">
          {job.title}
        </button>

        <div className="flex flex-col gap-0.5 text-[12px] text-lys-muted">
          <span className="truncate">{job.repository || UNKNOWN}{job.branch ? <span className="text-lys-gold"> · {job.branch}</span> : null}</span>
          <span className="truncate">assigned {assigned.length ? assigned.join(' → ') : UNKNOWN}</span>
          <span>started <span className="font-mono-code text-lys-faint">{formatDateTime(job.startedAt)}</span></span>
        </div>

        {progress !== null ? (
          <div className="flex items-center gap-2 text-[11px] text-lys-muted">
            <div className="flex-1 h-1.5 bg-lys-surface-2 relative" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} aria-label="Job progress">
              <div className="absolute left-0 top-0 bottom-0" style={{ width: `${progress * 100}%`, backgroundColor: tone }} />
            </div>
            <span className="lys-metric">{Math.round(progress * 100)}%</span>
          </div>
        ) : (
          <span className="text-[11px] text-lys-faint" title="Hermes reports no progress for this job">progress {UNKNOWN}</span>
        )}

        {failed && (
          <div role="note" className="px-2.5 py-1.5 border border-[color-mix(in_srgb,var(--lys-status-danger)_40%,transparent)] bg-[color-mix(in_srgb,var(--lys-status-danger)_6%,transparent)] text-[11px] text-lys-danger">
            MISSION INTERRUPTED · open the job for the failure explanation
          </div>
        )}
        {job.blockedReason && <div className="text-[11px] text-lys-warning break-words">blocked: {String(job.blockedReason)}</div>}
      </div>
    </Card>
  );
};
