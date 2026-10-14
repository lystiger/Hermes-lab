import React, { useRef, useState } from 'react';
import { AgentSummary, Job } from '../../api/types';
import { ACTIVE_JOB_STATUSES } from '../../api/adapters/httpAdapter';
import { useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { CopyId } from '../../components/CopyId';
import { EmptyState, ErrorState, Freshness, LoadingState, UNKNOWN } from '../../components/DataStates';
import { FilterPills } from '../../components/FilterPills';
import { useArrowNavigation } from '../../components/keyboard';
import { formatDateTime } from '../time/format';

/** Board columns follow the real job statuses. Each job appears in exactly one column. */
export const BOARD_GROUPS = [
  { id: 'RUNNING', label: 'Running', statuses: ACTIVE_JOB_STATUSES, tone: '#3FB950' },
  { id: 'BLOCKED', label: 'Blocked', statuses: ['BLOCKED'], tone: '#E3A008' },
  { id: 'QUEUED', label: 'Queued', statuses: ['QUEUED', 'CLAIMED'], tone: '#8C949F' },
  { id: 'FAILED', label: 'Failed', statuses: ['FAILED'], tone: '#F2555A' },
  { id: 'COMPLETED', label: 'Completed', statuses: ['COMPLETED'], tone: '#5C646E' },
  { id: 'CANCELLED', label: 'Cancelled', statuses: ['CANCELLED'], tone: '#5C646E' }
];

const PRIORITY_COLOR: Record<string, string> = { P0: '#F2555A', P1: '#E3A008', P2: '#8C949F', P3: '#5C646E' };

/** The board column a job belongs to. Unrecognised statuses get their own column, never a guessed one. */
export function groupOf(job: Job): { id: string; label: string; tone: string } {
  const known = BOARD_GROUPS.find((g) => g.statuses.includes(job.status));
  return known ?? { id: `OTHER:${job.status}`, label: `Other · ${job.status}`, tone: '#8C949F' };
}

export const MissionBoard: React.FC<{
  jobs: Job[];
  loading: boolean;
  error: unknown;
  updatedAt: number | null;
  onRetry: () => void;
  onOpen: (jobId: string) => void;
}> = ({ jobs, loading, error, updatedAt, onRetry, onOpen }) => {
  const { agents } = useAgents();
  const [filter, setFilter] = useState('ALL');
  const listRef = useRef<HTMLDivElement>(null);
  useArrowNavigation(listRef);

  const counts = new Map<string, number>();
  for (const j of jobs) counts.set(groupOf(j).id, (counts.get(groupOf(j).id) ?? 0) + 1);
  // Unrecognised statuses each get a column, labelled with the raw status.
  const otherColumns = jobs
    .map((j) => groupOf(j))
    .filter((g) => g.id.startsWith('OTHER:'))
    .filter((g, i, all) => all.findIndex((x) => x.id === g.id) === i)
    .map((g) => ({ ...g, statuses: [] as string[] }));
  const columns = [...BOARD_GROUPS, ...otherColumns];
  const pills = [
    { id: 'ALL', label: 'All', count: jobs.length },
    ...columns.map((c) => ({ id: c.id, label: c.label.replace('Other · ', ''), count: counts.get(c.id) ?? 0 }))
  ];

  return (
    <section aria-label="Mission board" className="flex flex-col gap-3 p-5 border-b border-[#1F242B]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilterPills label="Filter jobs by status" options={pills} value={filter} onChange={setFilter} />
        <Freshness at={updatedAt} />
      </div>

      {loading && jobs.length === 0 && <LoadingState label="Loading jobs…" />}
      {Boolean(error) && jobs.length === 0 && <ErrorState label="Job queue" error={error} onRetry={onRetry} />}
      {!loading && !error && jobs.length === 0 && <EmptyState>No jobs returned by Hermes.</EmptyState>}

      <div ref={listRef} className="flex flex-col gap-5">
        {columns
          .filter((c) => (filter === 'ALL' || filter === c.id) && (counts.get(c.id) ?? 0) > 0)
          .map((c) => (
            <div key={c.id} role="list" aria-label={`${c.label} jobs`} className="flex flex-col gap-2">
              <div className="flex items-center gap-2 font-mono-code text-[11px] tracking-wider" style={{ color: c.tone }}>
                <span>{c.label.toUpperCase()}</span>
                <span className="text-[#5C646E]">{counts.get(c.id)}</span>
              </div>
              {jobs
                .filter((j) => groupOf(j).id === c.id)
                .map((j) => (
                  <JobCard key={j.id} job={j} tone={c.tone} agentsList={agents} onOpen={onOpen} />
                ))}
            </div>
          ))}
      </div>
      {jobs.length > 0 && <p className="font-mono-code text-[10px] text-[#5C646E]">↑ ↓ move · Enter opens the job inspector</p>}
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
  const priorityColor = (job.priority && PRIORITY_COLOR[job.priority]) || '#3A4048';
  const assigned = job.assignedAgentIds.map((id) => resolveActorPresentation(id, agentsList).displayName);
  const progress = typeof job.progress === 'number' ? Math.max(0, Math.min(1, job.progress)) : null;

  return (
    <div role="listitem" className="border border-[#1F242B] bg-[#0C0E11]" style={{ borderLeft: `3px solid ${priorityColor}` }}>
      <div className="p-3 flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-mono-code text-[10px] tracking-wider" style={{ color: priorityColor }}>
            {job.priority || UNKNOWN}
          </span>
          <CopyId value={job.id} className="text-[#5C646E] text-[11px]" />
          <span className="font-mono-code text-[10px] tracking-wider ml-auto" style={{ color: tone }}>
            {job.status}
          </span>
        </div>

        <button
          type="button"
          data-nav-item
          onClick={() => onOpen(job.id)}
          className="text-left text-[14px] font-semibold text-[#E6E9ED] hover:underline cursor-pointer"
        >
          {job.title}
        </button>

        <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono-code text-[11px] text-[#8C949F]">
          <span>{job.repository || UNKNOWN}</span>
          <span className="text-[#CBA35C]">{job.branch || UNKNOWN}</span>
          <span>assigned {assigned.length ? assigned.join(' → ') : UNKNOWN}</span>
          <span>phase {job.currentPhase || UNKNOWN}</span>
          <span>started {formatDateTime(job.startedAt)}</span>
        </div>

        {progress !== null ? (
          <div className="flex items-center gap-2 font-mono-code text-[11px] text-[#8C949F]">
            <div className="flex-1 h-1.5 bg-[#1F242B] relative" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} aria-label="Job progress">
              <div className="absolute left-0 top-0 bottom-0" style={{ width: `${progress * 100}%`, backgroundColor: tone }} />
            </div>
            <span>{Math.round(progress * 100)}%</span>
          </div>
        ) : (
          <span className="font-mono-code text-[11px] text-[#5C646E]" title="Hermes reports no progress for this job">progress {UNKNOWN}</span>
        )}

        {failed && (
          <div role="note" className="mt-1 px-2.5 py-1.5 border border-[rgba(242,85,90,0.4)] bg-[rgba(242,85,90,0.06)] font-mono-code text-[11px] text-[#F2555A]">
            MISSION INTERRUPTED · open the job for the failure explanation
          </div>
        )}
        {job.blockedReason && (
          <div className="font-mono-code text-[11px] text-[#E3A008] break-words">blocked: {String(job.blockedReason)}</div>
        )}
      </div>
    </div>
  );
};
