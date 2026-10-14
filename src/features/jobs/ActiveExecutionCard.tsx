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
      <div className="p-5 border-b border-[#1F242B] bg-[#0A0B0D] select-none">
        <div className="font-mono-code text-[11px] text-[#5C646E] tracking-wider mb-2">ACTIVE EXECUTION</div>
        <div className="text-[18px] font-semibold text-[#8C949F]">No active execution</div>
        <p className="mt-1 font-mono-code text-[11px] text-[#5C646E]">
          None of the latest {jobs.length} jobs is in RUNNING, PLANNING, PREPARING, VERIFYING or REPAIRING state.
        </p>
      </div>
    );
  }

  const branch = activeJob.branch;

  return (
    <div className="relative p-5 pb-6 border-b border-[#1F242B] overflow-hidden select-none bg-[#0A0B0D]">
      {ambient3d && <AmbientGyro enabled={ambient3d} size={150} />}

      {/* Header Status */}
      <div className="flex items-center gap-2.5 mb-2">
        <span className="font-mono-code text-[11px] text-[#5C646E] tracking-wider">
          ACTIVE EXECUTION
        </span>
        <span className="flex items-center gap-1.5 font-mono-code text-[11px] text-[#3FB950] border border-[rgba(63,185,80,0.35)] px-1.5 py-0.5 bg-[rgba(63,185,80,0.05)]">
          {activeJob.status}
        </span>
      </div>

      {/* Main Title / Clickable Target */}
      <button
        type="button"
        onClick={() => onOpenJob?.(activeJob.id)}
        className="flex items-baseline flex-wrap gap-x-3 gap-y-0.5 text-left cursor-pointer hover:opacity-80 transition-opacity"
      >
        <span className="font-mono-code text-[26px] text-[#5C646E]">{activeJob.id}</span>
        <span className="text-[22px] font-semibold tracking-tight text-[#E6E9ED]">{activeJob.title}</span>
      </button>

      {/* Metadata Bar */}
      <div className="flex items-center flex-wrap gap-x-3.5 gap-y-1 mt-2 font-mono-code text-[11px] text-[#8C949F]">
        <span>{activeJob.repository}</span>
        {branch && (
          <>
            <span className="text-[#2A3038]">·</span>
            <span className="text-[#CBA35C]">{branch}</span>
          </>
        )}
        <span className="text-[#2A3038]">·</span>
        <span>elapsed <span className="text-[#E6E9ED]">{formatElapsed(activeJob.startedAt, activeJob.completedAt, nowMs)}</span></span>
        <span className="text-[#2A3038]">·</span>
        <span>tokens <JobTokens jobId={activeJob.id} /></span>
      </div>

      {/* Pipeline Graph of this job */}
      <div className="mt-6">
        <JobPipelineGraph steps={detail?.executionGraph ?? []} />
      </div>

      {/* Completion footer: no estimator exists in the Hermes API */}
      <div className="mt-5 flex flex-wrap gap-6 pt-3.5 border-t border-[#1F242B] font-mono-code text-[11px]">
        <span className="text-[#5C646E]">ESTIMATED COMPLETION</span>
        <span className="text-[#8C949F]">
          <UnknownValue reason="Hermes exposes no estimator for phase or job completion" className="text-[#8C949F]" />
        </span>
        {onOpenJob && (
          <button
            type="button"
            onClick={() => onOpenJob(activeJob.id)}
            className="text-[#CBA35C] hover:underline cursor-pointer"
          >
            open job →
          </button>
        )}
      </div>
    </div>
  );
};
