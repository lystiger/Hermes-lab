import React from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useJobs, useRecoverableJobs, useTelemetry } from '../api/hooks';
import { ErrorState, Freshness, LoadingState } from '../components/DataStates';
import { Card } from '../components/Card';
import { CopyId } from '../components/CopyId';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { NotReportedItem } from '../components/NotReported';
import { MissionBoard } from '../features/jobs/MissionBoard';

const NOT_REPORTED: NotReportedItem[] = [
  { label: 'time estimates', reason: 'Hermes exposes no estimator for queued or running work' },
  { label: 'concurrency policy', reason: 'Hermes does not report a concurrency policy or repository capacity' }
];

export const QueueRoute: React.FC = () => {
  const { setActiveModalJobId } = useConsoleStore();
  const { jobs, loading: jobsLoading, error: jobsError, stale, updatedAt: jobsUpdatedAt, refetch: refetchJobs } = useJobs();
  const { telemetry } = useTelemetry();

  const counts: HeaderCount[] = telemetry
    ? [
        { label: 'RUNNING', value: telemetry.runningJobsCount, tone: 'var(--lys-status-success)' },
        { label: 'BLOCKED', value: telemetry.blockedJobsCount, tone: 'var(--lys-status-warning)' },
        { label: 'QUEUED', value: telemetry.queuedJobsCount },
        { label: 'FAILED 24H', value: telemetry.failed24hCount ?? '—', tone: telemetry.failed24hCount ? 'var(--lys-status-danger)' : undefined }
      ]
    : [];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader
        updatedAt={jobsUpdatedAt}
        title="Queue"
        subtitle="Backlog and history"
        counts={counts}
        notReported={NOT_REPORTED}
      />

      <div className="flex-1 flex flex-col gap-6 p-6">

        {jobsLoading && jobs.length === 0 && <LoadingState label="Loading jobs…" />}
        <MissionBoard
          jobs={jobs}
          loading={jobsLoading}
          error={jobsError}
          stale={stale && Boolean(jobsError)}
          updatedAt={jobsUpdatedAt}
          onRetry={refetchJobs}
          onOpen={(id) => setActiveModalJobId(id)}
        />

        <RecoverableJobs onSelect={(id) => setActiveModalJobId(id)} />
      </div>
    </div>
  );
};

const RecoverableJobs: React.FC<{ onSelect: (jobId: string) => void }> = ({ onSelect }) => {
  const { jobs, loading, error, updatedAt, refetch } = useRecoverableJobs();

  if (!loading && !error && jobs.length === 0) {
    return (
      <div className="px-5 py-3 bg-lys-surface-1 border border-lys-subtle rounded-md flex items-center justify-between text-[12px]">
        <span className="text-[11px] font-medium tracking-wider uppercase text-lys-faint">Recoverable · 0</span>
        <span className="text-lys-faint">No recoverable jobs</span>
      </div>
    );
  }

  return (
    <Card label="Recoverable jobs">
      <div className="p-5 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium tracking-wider uppercase text-lys-faint">Recoverable · {jobs.length} · read-only</span>
          <Freshness at={updatedAt} />
        </div>
        {loading && jobs.length === 0 && <LoadingState label="Loading recoverable jobs…" />}
        {error && <ErrorState label="Recoverable jobs" error={error} onRetry={refetch} />}
        <div className="flex flex-col gap-1.5">
          {jobs.map((j) => (
            <div
              key={j.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(j.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelect(j.id);
                }
              }}
              className="flex flex-wrap justify-between gap-2 p-2.5 bg-lys-surface-2 hover:bg-lys-surface-interactive text-left text-[12px] cursor-pointer"
            >
              <CopyId value={j.id} truncate className="text-lys-faint" />
              <span className="text-lys-primary truncate max-w-[300px]" title={j.title}>{j.title}</span>
              <span className="text-lys-muted uppercase font-mono-code text-[11px]">{j.status}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
};

export default QueueRoute;
