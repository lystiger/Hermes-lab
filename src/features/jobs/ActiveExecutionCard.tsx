import React from 'react';
import { JobPipelineGraph } from './JobPipelineGraph';
import { useJob, useJobs } from '../../api/hooks';
import { ACTIVE_JOB_STATUSES } from '../../api/adapters/httpAdapter';
import { ErrorState, Freshness, LoadingState, ResourceError, StaleNotice, UnknownValue } from '../../components/DataStates';
import { Card } from '../../components/Card';
import { CopyId } from '../../components/CopyId';
import { HERMES_ART } from '../../theme/agentArt';
import { useNow } from '../execution/useNow';
import { formatElapsed } from './jobTiming';
import { JobTokens } from './JobRealData';

interface ActiveExecutionCardProps {
  onOpenJob?: (jobId: string) => void;
}

/** The job that is active right now, from the real job list. With none active, the card says so and stays short. */
export const ActiveExecutionCard: React.FC<ActiveExecutionCardProps> = ({ onOpenJob }) => {
  const { jobs, loading, error, stale, refetch, updatedAt } = useJobs();
  const activeJob = jobs.find((j) => ACTIVE_JOB_STATUSES.includes(j.status));
  // The phase graph is its own resource: its failures are shown here, not hidden behind the card.
  const phases = useJob(activeJob?.id ?? null);
  const detail = phases.job;
  const nowMs = useNow(1000);

  if (loading && jobs.length === 0) {
    return <Card><LoadingState label="Loading active execution…" /></Card>;
  }

  if (error && jobs.length === 0) {
    return <Card><ErrorState label="Active execution" error={error} onRetry={refetch} /></Card>;
  }

  if (!activeJob) {
    return (
      <Card label="Active execution">
        <div className="p-5 flex flex-col gap-3">
          {stale && <StaleNotice label="Active execution" error={error} onRetry={refetch} />}
        <div className="flex items-center justify-between gap-6">
          <div className="min-w-0">
            <div className="text-[11px] tracking-wider uppercase text-lys-faint">Active execution</div>
            <div className="mt-1 font-display text-[22px] font-semibold text-lys-muted">No active execution</div>
            <p className="mt-1 text-[12px] text-lys-faint">
              None of the latest {jobs.length} jobs is in RUNNING, PLANNING, PREPARING, VERIFYING or REPAIRING state.
            </p>
          </div>
          <img src={HERMES_ART} alt="" aria-hidden="true" className="h-16 w-auto opacity-60 shrink-0" />
        </div>
        </div>
      </Card>
    );
  }

  return (
    <Card accent="var(--lys-accent-gold)" label="Active execution">
      <div className="p-5 flex flex-col gap-4">
        {stale && <StaleNotice label="Active execution" error={error} onRetry={refetch} />}
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[11px] tracking-wider uppercase text-lys-faint">Active execution</span>
          <span className="ml-auto"><Freshness at={updatedAt} /></span>
          <span className="text-[10px] tracking-wider uppercase text-lys-success border border-lys-success/35 px-1.5 py-0.5">{activeJob.status}</span>
        </div>
        <div className="flex flex-col gap-1">
          <CopyId value={activeJob.id} className="text-lys-faint text-[11px]" />
          <button
            type="button"
            onClick={() => onOpenJob?.(activeJob.id)}
            className="text-left font-display text-[24px] font-semibold text-lys-primary hover:underline cursor-pointer"
          >
            {activeJob.title}
          </button>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-lys-muted">
          <span>{activeJob.repository}</span>
          {activeJob.branch && <span className="text-lys-gold">{activeJob.branch}</span>}
          <span>
            elapsed <span className="text-lys-primary lys-metric">{formatElapsed(activeJob.startedAt, activeJob.completedAt, nowMs)}</span>
          </span>
          <span>tokens <JobTokens jobId={activeJob.id} /></span>
        </div>
        <div>
          {phases.error && !detail ? (
            <ErrorState label="Job phases" error={phases.error} onRetry={phases.refetch} />
          ) : (
            <>
              {phases.error && detail && (
                <ResourceError label="Job phases" error={phases.error} hasData updatedAt={phases.updatedAt} onRetry={phases.refetch} />
              )}
              <JobPipelineGraph steps={detail?.executionGraph ?? []} />
            </>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4 pt-3 border-t border-lys-subtle text-[12px] text-lys-muted">
          <span>
            estimated completion{' '}
            <UnknownValue reason="Hermes exposes no estimator for phase or job completion" className="text-lys-muted" />
          </span>
          {onOpenJob && (
            <button type="button" onClick={() => onOpenJob(activeJob.id)} className="text-lys-gold hover:underline cursor-pointer">
              open job →
            </button>
          )}
        </div>
      </div>
    </Card>
  );
};

