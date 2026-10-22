import React from 'react';
import { JobRunTimeline } from './JobRunTimeline';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useJob, useJobEvents } from '../../api/hooks';
import { OperationalThreadView } from '../messaging/OperationalThreadView';
import { JobTaskExecution } from '../execution/JobTaskExecution';
import { useNow } from '../execution/useNow';
import { formatElapsed } from './jobTiming';
import { mergeJobEvents } from './jobEvents';
import { JobDiagnostics, JobFailure, JobObservations, JobRuns, JobTasks, JobTokens } from './JobRealData';
import { ErrorState, LoadingState, EmptyState, Freshness, ResourceError } from '../../components/DataStates';
import { formatDateTime } from '../time/format';
import { CopyId } from '../../components/CopyId';

interface JobDetailViewProps {
  jobId?: string;
}

export const JobDetailView: React.FC<JobDetailViewProps> = ({ jobId = '' }) => {
  const { allEvents } = useConsoleStore();
  const { job, loading, error, stale, updatedAt, refetch } = useJob(jobId);
  const durable = useJobEvents(job ? job.id : null);
  const nowMs = useNow(1000);

  if (loading && !job) {
    return <LoadingState label={`Loading job ${jobId}…`} />;
  }

  if (error && !job) {
    return <ErrorState label={`Job ${jobId}`} error={error} onRetry={refetch} />;
  }

  if (!job) {
    return (
      <div className="w-full p-12 bg-lys-base font-sans text-[12px] text-lys-muted flex items-center justify-center">
        <span>No job loaded</span>
      </div>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'RUNNING':
        return 'var(--lys-status-success)';
      case 'COMPLETED':
        return 'var(--lys-text-faint)';
      case 'FAILED':
        return 'var(--lys-status-danger)';
      case 'CANCELLED':
        return 'var(--lys-text-faint)';
      case 'PREPARING':
      case 'QUEUED':
        return 'var(--lys-accent-gold)';
      default:
        return 'var(--lys-text-muted)';
    }
  };

  const statusCol = getStatusColor(job.status);
  const liveEvents = allEvents.filter((e) => Boolean(e.jobId && (e.jobId === job.id || e.jobId === job.sprintId)));
  const traceRows = mergeJobEvents(durable.events, liveEvents);

  return (
    <div className="w-full bg-lys-base select-none">
      {stale && (
        <div className="px-5 pt-4">
          <ResourceError label={`Job ${job.id}`} error={error} hasData updatedAt={updatedAt} onRetry={refetch} />
        </div>
      )}
      {/* Header Banner */}
      <div className="p-5 border-b border-lys-subtle bg-lys-surface-0">
        <div className="flex items-center gap-3">
          <CopyId truncate value={job.id} className="max-w-[40%] text-[18px] text-lys-faint" />
          <h2 title={job.title} className="min-w-0 truncate text-[20px] font-semibold text-lys-primary">
            {job.title}
          </h2>
          <span
            style={{
              color: statusCol,
              borderColor: `color-mix(in srgb, ${statusCol} 33%, transparent)`,
              backgroundColor: `color-mix(in srgb, ${statusCol} 8%, transparent)`
            }}
            className="shrink-0 flex items-center gap-1.5 font-sans text-[11px] tracking-wider border px-2 py-0.5"
          >
            {job.status === 'RUNNING' && (
              <span style={{ backgroundColor: statusCol }} className="w-1 h-1 rounded-[1px]" />
            )}
            {job.status}
          </span>
        </div>

        <div className="mt-2.5 flex items-center flex-wrap gap-x-4 gap-y-1 font-sans text-[11px] text-lys-muted">
          <span>{job.repository}</span>
          {job.branch && <span className="text-lys-gold">{job.branch}</span>}
          <span className="text-lys-default">·</span>
          <span>started {formatDateTime(job.startedAt)}</span>
          <span>completed {formatDateTime(job.completedAt)}</span>
          <span>elapsed <span className="text-lys-primary">{formatElapsed(job.startedAt, job.completedAt, nowMs)}</span></span>
          <span>tokens <JobTokens jobId={job.id} /></span>
        </div>
      </div>

      <div className="px-5 pt-4">
        <JobFailure job={job} />
      </div>

      <section aria-label="Run timeline" className="px-5 py-4 border-b border-lys-subtle">
        <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-3">
          RUN TIMELINE · {job.phases?.length || job.executionGraph?.length || 0} PHASES
        </div>
        <JobRunTimeline job={job} />
      </section>

      {/* Main Body Split */}
      <div className="flex flex-col lg:flex-row items-stretch">
        {/* Left Column: Artifact References (the phases are on the run timeline above) */}
        {job.artifacts && job.artifacts.length > 0 && (
          <div className="w-full lg:w-80 flex-shrink-0 border-r border-b lg:border-b-0 border-lys-subtle p-5 bg-lys-base">
            <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-2.5">
              ARTIFACT REFERENCES
            </div>
            <div className="flex flex-col gap-1.5 font-sans text-[11px]">
              {job.artifacts.map((art, idx) => (
                <div key={art.id || idx} className="flex justify-between text-lys-muted">
                  <span className="text-lys-gold">{art.label}</span>
                  <span className="text-lys-faint truncate max-w-[120px]" title={art.ref}>{art.ref}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Right Column: Operational Thread & Execution Events */}
        <div className="flex-1 min-w-0 flex flex-col p-4 gap-5">
          {/* Phase 5 Operational Messaging & Handoffs View */}
          <OperationalThreadView
            jobId={job.id}
            assignedAgentIds={job.assignedAgentIds}
          />

          <JobDiagnostics job={job} />
          <JobTasks jobId={job.id} />
          <JobRuns jobId={job.id} />
          <JobObservations jobId={job.id} />

          {/* Backend execution per task (D-009) */}
          <JobTaskExecution events={traceRows.map((r) => r.event)} />

          {/* Job trace: durable history merged with the live buffer */}
          <div className="pb-8">
            <div className="flex items-center justify-between mb-2.5">
              <span className="font-sans text-[11px] tracking-wider text-lys-faint">
                RUNTIME EVENTS &amp; TRACES
              </span>
              <Freshness at={durable.updatedAt} />
            </div>
            {durable.error && (
              <ErrorState label="Durable job history" error={durable.error} onRetry={durable.refetch} />
            )}
            {!durable.error && traceRows.length === 0 && !durable.loading && (
              <EmptyState>No events recorded</EmptyState>
            )}
            <div className="flex flex-col">
              {traceRows.slice(0, 50).map(({ event: e, origin }) => (
                <div
                  key={e.id}
                  className="grid grid-cols-[70px_90px_100px_minmax(0,1fr)] xl:grid-cols-[80px_110px_120px_minmax(0,1fr)_45px_65px] items-center gap-3 py-1 font-sans text-[11px] border-b border-lys-subtle"
                >
                  <span title={e.ts} className="min-w-0 truncate text-lys-faint">{e.ts}</span>
                  <span
                    style={{ color: e.source.accentColor || 'var(--lys-text-muted)' }}
                    title={e.source.displayName} className="min-w-0 truncate font-medium"
                  >
                    {e.source.displayName}
                  </span>
                  <span
                    title={`${e.kind} · ${e.dur} · ${origin === 'stored' ? 'durable' : origin === 'bus' ? 'in-memory' : 'live'}`}
                    className="min-w-0 truncate text-lys-muted"
                  >
                    {e.kind}
                  </span>
                  <span className="flex-1 min-w-0 text-lys-secondary break-words font-sans line-clamp-2" title={e.detail}>
                    {e.detail}
                  </span>
                  <span title={e.dur} className="min-w-0 truncate hidden xl:block text-right text-lys-muted">{e.dur}</span>
                  <span
                    className="min-w-0 truncate hidden xl:block text-right text-lys-faint"
                    title={
                      origin === 'stored'
                        ? 'Durable: canonical stored envelope'
                        : origin === 'bus'
                          ? 'In-memory event bus: not durable, lost on restart'
                          : 'Live buffer only: received over the stream this session'
                    }
                  >
                    {origin === 'stored' ? 'durable' : origin === 'bus' ? 'in-memory' : 'live'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
