import React from 'react';
import { AmbientGyro } from '../../components/AmbientGyro';
import { JobPipelineGraph } from './JobPipelineGraph';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useJob, useJobs } from '../../api/hooks';
import { ACTIVE_JOB_STATUSES } from '../../api/adapters/httpAdapter';
import { ErrorState, LoadingState, UnknownValue } from '../../components/DataStates';
import { JobTokens } from './JobRealData';
import { useNow } from '../execution/useNow';
import { formatElapsed } from './jobTiming';

interface ActiveExecutionCardProps {
  onOpenJob?: (jobId: string) => void;
}

/** The job that is active right now, taken from the real job list. Nothing is shown when none is active. */
export const ActiveExecutionCard: React.FC<ActiveExecutionCardProps> = ({ onOpenJob }) => {
  const { ambient3d } = useConsoleStore();
  const { jobs, loading, error, refetch } = useJobs();
  const activeJob = jobs.find((j) => ACTIVE_JOB_STATUSES.includes(j.status));
  const { job: detail } = useJob(activeJob?.id ?? null);
  const nowMs = useNow(1000);

  if (loading && jobs.length === 0) {
    return <LoadingState label="Loading active execution…" />;
  }

  if (error && jobs.length === 0) {
    return <ErrorState label="Active execution" error={error} onRetry={refetch} />;
  }

  if (!activeJob) {
    return (
      <div className="p-5 border-b border-lys-subtle bg-lys-base select-none">
        <div className="font-mono-code text-[11px] text-lys-faint tracking-wider mb-2">ACTIVE EXECUTION</div>
        <div className="text-[18px] font-semibold text-lys-muted">No active execution</div>
        <p className="mt-1 font-mono-code text-[11px] text-lys-faint">
          None of the latest {jobs.length} jobs is in RUNNING, PLANNING, PREPARING, VERIFYING or REPAIRING state.
        </p>
      </div>
    );
  }

  const branch = activeJob.branch;

  return (
    <div className="relative p-5 pb-6 border-b border-lys-subtle overflow-hidden select-none bg-lys-base">
      {ambient3d && <AmbientGyro enabled={ambient3d} size={150} />}

      {/* Header Status */}
      <div className="flex items-center gap-2.5 mb-2">
        <span className="font-mono-code text-[11px] text-lys-faint tracking-wider">
          ACTIVE EXECUTION
        </span>
        <span className="flex items-center gap-1.5 font-mono-code text-[11px] text-lys-success border border-lys-success/35 px-1.5 py-0.5 bg-lys-success/5">
          {activeJob.status}
        </span>
      </div>

      {/* Main Title / Clickable Target */}
      <button
        type="button"
        onClick={() => onOpenJob?.(activeJob.id)}
        className="flex items-baseline flex-wrap gap-x-3 gap-y-0.5 text-left cursor-pointer hover:opacity-80 transition-opacity"
      >
        <span className="font-mono-code text-[26px] text-lys-faint">{activeJob.id}</span>
        <span className="text-[22px] font-semibold tracking-tight text-lys-primary">{activeJob.title}</span>
      </button>

      {/* Metadata Bar */}
      <div className="flex items-center flex-wrap gap-x-3.5 gap-y-1 mt-2 font-mono-code text-[11px] text-lys-muted">
        <span>{activeJob.repository}</span>
        {branch && (
          <>
            <span className="text-lys-default">·</span>
            <span className="text-lys-gold">{branch}</span>
          </>
        )}
        <span className="text-lys-default">·</span>
        <span>elapsed <span className="text-lys-primary">{formatElapsed(activeJob.startedAt, activeJob.completedAt, nowMs)}</span></span>
        <span className="text-lys-default">·</span>
        <span>tokens <JobTokens jobId={activeJob.id} /></span>
      </div>

      {/* Pipeline Graph of this job */}
      <div className="mt-6">
        <JobPipelineGraph steps={detail?.executionGraph ?? []} />
      </div>

      {/* Completion footer: no estimator exists in the Hermes API */}
      <div className="mt-5 flex flex-wrap gap-6 pt-3.5 border-t border-lys-subtle font-mono-code text-[11px]">
        <span className="text-lys-faint">ESTIMATED COMPLETION</span>
        <span className="text-lys-muted">
          <UnknownValue reason="Hermes exposes no estimator for phase or job completion" className="text-lys-muted" />
        </span>
        {onOpenJob && (
          <button
            type="button"
            onClick={() => onOpenJob(activeJob.id)}
            className="text-lys-gold hover:underline cursor-pointer"
          >
            open job →
          </button>
        )}
      </div>
    </div>
  );
};
