import React from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useJobs, usePipeline, useRecoverableJobs, useTelemetry } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import { useAgents } from '../api/hooks';
import { ErrorState, Freshness, LoadingState, StaleNotice } from '../components/DataStates';
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
  const { pipeline, error: pipelineError, refetch: refetchPipeline } = usePipeline();
  const { telemetry } = useTelemetry();
  const { agents } = useAgents();

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
        subtitle="Mission board"
        counts={counts}
        notReported={NOT_REPORTED}
      />

      <div className="flex-1 flex flex-col gap-6 p-6">
        {pipeline.length > 0 && (
          <Card accent="var(--lys-accent-gold)" label="Execution order">
            <div className="p-5 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium tracking-wider uppercase text-lys-faint">Execution order · active job</span>
              </div>
              {Boolean(pipelineError) && <StaleNotice label="Execution order" error={pipelineError} onRetry={refetchPipeline} />}
              <ol className="flex flex-col gap-1.5">
                {pipeline.map((p, idx) => {
                  const actor = p.agentId ? resolveActorPresentation(p.agentId, agents) : null;
                  return (
                    <li key={p.id || idx}>
                      <button
                        type="button"
                        onClick={() => p.jobId && setActiveModalJobId(p.jobId)}
                        className="w-full flex flex-wrap items-center gap-3 px-3 py-2 bg-lys-surface-2 hover:bg-lys-surface-interactive text-left text-[13px] cursor-pointer"
                      >
                        <span className="w-6 text-lys-faint text-[11px]">{String(idx + 1).padStart(2, '0')}</span>
                        <span className="w-28 text-lys-primary font-semibold">{p.phase}</span>
                        <span className="text-lys-muted">{p.agentName || actor?.displayName || '—'}</span>
                        <span className="ml-auto text-[10px] tracking-wider uppercase text-lys-secondary">{p.state}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </div>
          </Card>
        )}

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
