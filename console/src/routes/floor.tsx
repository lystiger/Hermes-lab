import React, { useMemo } from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useAgents, useJob, useJobs } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import { ACTIVE_JOB_STATUSES } from '../api/adapters/httpAdapter';
import { ErrorState, LoadingState, EmptyState, Freshness } from '../components/DataStates';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { useNow } from '../features/execution/useNow';
import { FloorCard } from '../features/floor/FloorCard';
import { floorColumns } from '../features/floor/floorLayout';
import { timelineRows, type TimelineRow } from '../features/jobs/runTimeline';
import type { TraceEvent } from '../api/types';

/**
 * Read-only floor: one section per active job, with its phases laid out in dependency columns.
 * Hermes reports no phase dependency edges yet, so every phase currently sits in the first column.
 */
export const FloorRoute: React.FC = () => {
  const { jobs, loading, error, updatedAt, refetch } = useJobs();
  const activeJobs = useMemo(() => jobs.filter((j) => ACTIVE_JOB_STATUSES.includes(j.status)), [jobs]);

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

const JobFloor: React.FC<{ jobId: string; title: string }> = ({ jobId, title }) => {
  const { job: detail, loading, error, updatedAt, refetch } = useJob(jobId);
  const { agents } = useAgents();
  const allEvents = useConsoleStore((s) => s.allEvents);
  const nowMs = useNow(1000);

  const rows = useMemo(() => (detail ? timelineRows(detail) : []), [detail]);
  const columns = useMemo(() => floorColumns(rows), [rows]);
  const jobEvents = useMemo(() => allEvents.filter((e) => e.jobId === jobId), [allEvents, jobId]);

  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 title={title} className="text-[14px] font-medium text-lys-primary truncate min-w-0">{title}</h2>
        <Freshness at={updatedAt} />
      </header>

      {loading && !detail && <LoadingState label="Loading phases…" />}
      {error && !detail && <ErrorState label={`Phases for ${title}`} error={error} onRetry={refetch} />}
      {detail && rows.length === 0 && <EmptyState>No phases reported for this job.</EmptyState>}

      {columns.length > 0 && (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {columns.map((column) => (
            <div key={column.level} className="flex flex-col gap-2 w-60 shrink-0">
              {column.rows.map((row: TimelineRow) => {
                const actor = row.agentId ? resolveActorPresentation(row.agentId, agents) : undefined;
                return (
                  <FloorCard
                    key={`${jobId}:${row.key}`}
                    row={row}
                    actor={actor}
                    latestEvent={latestEventFor(row, jobEvents)}
                    nowMs={nowMs}
                  />
                );
              })}
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

/** The newest event for one phase, matched by its spec order or name. Falls back to nothing rather than the job's latest event. */
function latestEventFor(row: TimelineRow, jobEvents: TraceEvent[]): string | undefined {
  const match = jobEvents.find((e) => e.metadata?.order === row.order || e.metadata?.phase === row.name);
  return match?.detail || undefined;
}
