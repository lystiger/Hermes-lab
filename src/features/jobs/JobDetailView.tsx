import React from 'react';
import { Check, X, CircleDot, Circle } from 'lucide-react';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useJob, useAgents, useJobEvents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
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
  const { agents } = useAgents();
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
        <span>Job '{jobId}' not found or not loaded.</span>
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
          <CopyId value={job.id} className="text-[18px] text-lys-faint" />
          <h2 className="text-[20px] font-semibold text-lys-primary">
            {job.title}
          </h2>
          <span
            style={{
              color: statusCol,
              borderColor: `color-mix(in srgb, ${statusCol} 33%, transparent)`,
              backgroundColor: `color-mix(in srgb, ${statusCol} 8%, transparent)`
            }}
            className="flex items-center gap-1.5 font-sans text-[11px] tracking-wider border px-2 py-0.5"
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

      {/* Main Body Split */}
      <div className="flex flex-col lg:flex-row items-stretch">
        {/* Left Column: Generic Execution Graph */}
        <div className="w-full lg:w-80 flex-shrink-0 border-r border-b lg:border-b-0 border-lys-subtle p-5 bg-lys-base">
          <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-4">
            EXECUTION GRAPH · {job.phases?.length || job.executionGraph?.length || 0} PHASES
          </div>

          <div style={{ perspective: '800px' }} className="flex flex-col">
            <div style={{ transformStyle: 'preserve-3d' }} className="flex flex-col">
              {(job.phases || []).map((p, idx) => {
                const actor = p.agentId ? resolveActorPresentation(p.agentId, agents) : null;
                const col = actor?.accentColor || 'var(--lys-border-strong)';
                const isDone = p.status === 'SUCCEEDED';
                const isActive = p.status === 'RUNNING';
                const isFailed = p.status === 'FAILED';

                return (
                  <div key={p.id || idx}>
                    <div
                      style={{
                        borderColor: isActive ? 'color-mix(in srgb, var(--lys-agent-claude) 45%, transparent)' : isDone ? 'var(--lys-border-subtle)' : isFailed ? 'color-mix(in srgb, var(--lys-status-danger) 40%, transparent)' : 'var(--lys-border-subtle)',
                        backgroundColor: isActive ? 'color-mix(in srgb, var(--lys-agent-claude) 6%, transparent)' : isDone ? 'var(--lys-surface-0)' : 'transparent',
                        transform: isActive ? 'translateZ(18px) rotateX(2deg)' : 'translateZ(0)',
                        boxShadow: isActive ? '0 14px 26px -14px color-mix(in srgb, var(--lys-agent-claude) 55%, transparent)' : 'none'
                      }}
                      className="flex gap-3 items-start p-3 border"
                    >
                      {/* Mark Icon */}
                      <div
                        style={{
                          borderColor: isDone ? 'color-mix(in srgb, var(--lys-status-success) 60%, transparent)' : isFailed ? 'var(--lys-status-danger)' : isActive ? col : 'var(--lys-border-default)',
                          backgroundColor: isDone ? 'color-mix(in srgb, var(--lys-status-success) 14%, transparent)' : isFailed ? 'color-mix(in srgb, var(--lys-status-danger) 14%, transparent)' : 'transparent',
                          color: isDone ? 'var(--lys-status-success)' : isFailed ? 'var(--lys-status-danger)' : isActive ? col : 'var(--lys-text-faint)'
                        }}
                        className="w-4.5 h-4.5 flex-shrink-0 flex items-center justify-center font-sans text-[11px] clip-hex"
                      >
                        {isDone ? <Check size={11} strokeWidth={2.5} aria-hidden="true" /> : isFailed ? <X size={11} strokeWidth={2.5} aria-hidden="true" /> : isActive ? <CircleDot size={9} strokeWidth={2.5} aria-hidden="true" /> : <Circle size={9} strokeWidth={2.5} aria-hidden="true" />}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div
                          style={{ color: isDone || isActive ? 'var(--lys-text-primary)' : 'var(--lys-text-faint)' }}
                          className="font-sans text-[11px] tracking-wider font-semibold"
                        >
                          {p.name}
                        </div>
                        <div style={{ color: col }} className="text-[12px] mt-0.5">
                          {p.agentName || actor?.displayName || p.agentId || '—'}
                        </div>
                        <div className="font-sans text-[10.5px] text-lys-faint mt-0.5">
                          {p.role} {p.commitSha ? `· ${p.commitSha.slice(0, 7)}` : ''}
                        </div>
                      </div>

                      <div className="font-sans text-[11px] text-lys-faint text-right">
                        {p.durationMs ? `${(p.durationMs / 1000).toFixed(1)}s` : p.status.toLowerCase()}
                      </div>
                    </div>

                    {/* Step Connector */}
                    {idx < (job.phases?.length || 0) - 1 && (
                      <div
                        style={{ backgroundColor: isDone ? 'color-mix(in srgb, var(--lys-status-success) 40%, transparent)' : 'var(--lys-border-subtle)' }}
                        className="h-4 w-[1px] ml-5"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Artifact References */}
          {job.artifacts && job.artifacts.length > 0 && (
            <div className="mt-5 pt-3.5 border-t border-lys-subtle">
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
        </div>

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
                RUNTIME EVENTS &amp; TRACES · {job.id}
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
                  className="flex items-center gap-3.5 py-1 font-sans text-[11px] border-b border-lys-subtle"
                >
                  <span className="w-24 text-lys-faint">{e.ts}</span>
                  <span
                    style={{ color: e.source.accentColor || 'var(--lys-text-muted)' }}
                    className="w-16 font-medium"
                  >
                    {e.source.displayName}
                  </span>
                  <span className="w-28 text-lys-muted">{e.kind}</span>
                  <span className="flex-1 min-w-0 text-lys-secondary break-words font-sans line-clamp-2" title={e.detail}>
                    {e.detail}
                  </span>
                  <span className="w-16 text-right text-lys-muted">{e.dur}</span>
                  <span
                    className="w-20 text-right text-lys-faint"
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
