import React, { useMemo, useState } from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useAgents, useJob, useJobs, useJobTelemetry } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import { ACTIVE_JOB_STATUSES } from '../api/adapters/httpAdapter';
import { ErrorState, LoadingState, EmptyState, Freshness } from '../components/DataStates';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { useNow } from '../features/execution/useNow';
import { FloorCard } from '../features/floor/FloorCard';
import { floorColumns } from '../features/floor/floorLayout';
import { buildTaskInsights, floorDependencies, formatCost } from '../features/floor/floorInsights';
import { JobRunTimeline } from '../features/jobs/JobRunTimeline';
import { timelineRows, type TimelineRow } from '../features/jobs/runTimeline';
import type { TraceEvent } from '../api/types';

/**
 * The run page: one section per active job, its phases in dependency columns (or on a timeline). A repair
 * sits after the check whose findings it fixes, and its re-check after it. Read-only: it never changes a run.
 */
export const FloorRoute: React.FC = () => {
  const { jobs, loading, error, updatedAt, refetch } = useJobs();
  // A job paused until an agent usage limit resets is still mid-run, so it stays on the floor.
  const activeJobs = useMemo(
    () => jobs.filter((j) => ACTIVE_JOB_STATUSES.includes(j.status) || j.status === 'WAITING_FOR_CAPACITY'),
    [jobs]
  );

  const counts: HeaderCount[] = [{ label: 'ACTIVE JOBS', value: activeJobs.length, tone: 'var(--lys-status-success)' }];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader
        updatedAt={updatedAt}
        title="Floor"
        subtitle="Active jobs · by phase"
        counts={counts}
      />

      <div className="flex-1 flex flex-col gap-6 p-6">
        {loading && jobs.length === 0 && <LoadingState label="Loading jobs…" />}
        {error && jobs.length === 0 && <ErrorState label="Floor" error={error} onRetry={refetch} />}
        {!loading && !error && activeJobs.length === 0 && <EmptyState>No active jobs on the floor.</EmptyState>}
        {activeJobs.map((job) => <JobFloor key={job.id} jobId={job.id} title={job.title} />)}
      </div>
    </div>
  );
};

type FloorView = 'cards' | 'timeline';

const JobFloor: React.FC<{ jobId: string; title: string }> = ({ jobId, title }) => {
  const { job: detail, loading, error, updatedAt, refetch } = useJob(jobId);
  const { telemetry } = useJobTelemetry(jobId);
  const { agents } = useAgents();
  const allEvents = useConsoleStore((s) => s.allEvents);
  const nowMs = useNow(1000);
  const [view, setView] = useState<FloorView>('cards');

  const rows = useMemo(() => (detail ? timelineRows(detail) : []), [detail]);
  const insights = useMemo(() => buildTaskInsights(detail?.tasks, telemetry?.tasks ?? []), [detail, telemetry]);
  const columns = useMemo(() => floorColumns(rows, floorDependencies(detail?.phases, insights)), [rows, detail, insights]);
  const jobEvents = useMemo(() => allEvents.filter((e) => e.jobId === jobId), [allEvents, jobId]);

  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <JobFloorHeader
        title={title}
        status={detail?.status}
        repairCount={detail?.repairCount}
        spend={telemetry ? formatCost(telemetry.costUsd, telemetry.totalTokens) : null}
        updatedAt={updatedAt}
        view={view}
        onViewChange={setView}
      />

      {loading && !detail && <LoadingState label="Loading phases…" />}
      {error && !detail && <ErrorState label={`Phases for ${title}`} error={error} onRetry={refetch} />}
      {detail && rows.length === 0 && <EmptyState>No phases reported for this job yet.</EmptyState>}

      {view === 'timeline' && detail && rows.length > 0 && <JobRunTimeline job={detail} />}

      {view === 'cards' && columns.length > 0 && (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {columns.map((column) => (
            <div key={column.level} className="flex flex-col gap-2 w-64 shrink-0">
              {column.rows.map((row: TimelineRow) => (
                <FloorCard
                  key={`${jobId}:${row.key}`}
                  row={row}
                  actor={row.agentId ? resolveActorPresentation(row.agentId, agents) : undefined}
                  insight={insights.get(row.key)}
                  latestEvent={latestEventFor(row, jobEvents)}
                  nowMs={nowMs}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

interface JobFloorHeaderProps {
  title: string;
  status?: string;
  repairCount?: number;
  /** Formatted job spend, or null when no agent has reported usage yet. */
  spend: string | null;
  updatedAt: number | null;
  view: FloorView;
  onViewChange: (view: FloorView) => void;
}

const VIEWS: { id: FloorView; label: string }[] = [
  { id: 'cards', label: 'Cards' },
  { id: 'timeline', label: 'Timeline' }
];

/** Job identity and what it has cost so far, with the switch between the card and timeline views. */
const JobFloorHeader: React.FC<JobFloorHeaderProps> = ({ title, status, repairCount, spend, updatedAt, view, onViewChange }) => (
  <header className="flex flex-wrap items-center justify-between gap-3">
    <div className="flex items-baseline gap-3 min-w-0">
      <h2 title={title} className="text-[14px] font-medium text-lys-primary truncate min-w-0">{title}</h2>
      {status && <span className="text-[10px] tracking-wider uppercase font-mono-code text-lys-success shrink-0">{status}</span>}
    </div>
    <div className="flex flex-wrap items-center gap-4 text-[12px] text-lys-muted">
      {repairCount ? (
        <span style={{ color: 'var(--lys-status-warning)' }}>
          {repairCount} repair cycle{repairCount === 1 ? '' : 's'}
        </span>
      ) : null}
      <span className="font-mono-code" title="Agent-reported usage across every task so far">{spend ?? 'no usage yet'}</span>
      <Freshness at={updatedAt} />
      <div role="group" aria-label="Floor view" className="flex border border-lys-subtle">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            aria-pressed={view === v.id}
            onClick={() => onViewChange(v.id)}
            className={`px-3 py-1 text-[12px] cursor-pointer transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] ${
              view === v.id ? 'bg-lys-surface-interactive text-lys-primary' : 'text-lys-muted hover:bg-lys-surface-2'
            }`}
          >
            {v.label}
          </button>
        ))}
      </div>
    </div>
  </header>
);

/** The newest event for one phase, matched by its spec order or name. Falls back to nothing rather than the job's latest event. */
function latestEventFor(row: TimelineRow, jobEvents: TraceEvent[]): string | undefined {
  const match = jobEvents.find((e) => e.metadata?.order === row.order || e.metadata?.phase === row.name);
  return match?.detail || undefined;
}
