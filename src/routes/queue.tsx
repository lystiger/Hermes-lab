import React from 'react';
import { MissionBoard } from '../features/jobs/MissionBoard';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useJobs, usePipeline, useAgents } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import { EmptyState, ErrorState, Freshness, LoadingState, StaleNotice } from '../components/DataStates';
import { useRecoverableJobs } from '../api/hooks';

export const QueueRoute: React.FC = () => {
  const { setActiveModalJobId } = useConsoleStore();
  const { jobs, loading: jobsLoading, error: jobsError, updatedAt: jobsUpdatedAt, refetch: refetchJobs } = useJobs();
  const { pipeline, loading: pipelineLoading, error: pipelineError, updatedAt: pipelineUpdatedAt, refetch: refetchPipeline } = usePipeline();
  const { agents } = useAgents();

  const getStateColor = (state: string) => {
    switch (state) {
      case 'COMPLETED': return 'var(--lys-text-faint)';
      case 'RUNNING': return 'var(--lys-status-success)';
      case 'QUEUED': return 'var(--lys-text-muted)';
      case 'CLAIMED': return 'var(--lys-accent-gold)';
      case 'BLOCKED': return 'var(--lys-status-warning)';
      case 'FAILED': return 'var(--lys-status-danger)';
      default: return 'var(--lys-text-faint)';
    }
  };

  return (
    <div className="flex flex-col pb-10 select-none bg-lys-base">
      {/* Execution Order Pipeline Section */}
      <div className="p-5 border-b border-lys-subtle bg-lys-surface-0">
        <div className="flex items-center gap-3.5 mb-3 font-mono-code text-[11px]">
          <span className="tracking-wider text-lys-faint">EXECUTION ORDER</span>
          <span className="text-lys-muted">phases of the active job, in the order Hermes reports them</span>
          <Freshness at={pipelineUpdatedAt} />
        </div>

        {pipelineLoading && pipeline.length === 0 && <LoadingState label="Loading execution order…" />}
        {pipelineError && pipeline.length === 0 && (
          <ErrorState label="Execution order" error={pipelineError} onRetry={refetchPipeline} />
        )}
        {!pipelineLoading && !pipelineError && pipeline.length === 0 && (
          <EmptyState>No active job. Nothing is executing in the latest jobs from Hermes.</EmptyState>
        )}

        <div className="flex flex-col max-w-5xl">
          {pipeline.map((p, idx) => {
            const isRunning = p.state === 'RUNNING';
            const isBlocked = p.state === 'BLOCKED';
            const actor = p.agentId ? resolveActorPresentation(p.agentId, agents) : null;
            const agentCol = actor?.accentColor || 'var(--lys-text-muted)';
            const stateCol = getStateColor(p.state);
            const agentName = p.agentName || actor?.displayName || '—';

            return (
              <div key={p.id || idx}>
                <div
                  onClick={() => p.jobId && setActiveModalJobId(p.jobId)}
                  style={{
                    borderColor: isRunning ? 'color-mix(in srgb, var(--lys-agent-claude) 45%, transparent)' : isBlocked ? 'color-mix(in srgb, var(--lys-status-warning) 30%, transparent)' : 'var(--lys-border-subtle)',
                    backgroundColor: isRunning ? 'color-mix(in srgb, var(--lys-agent-claude) 6%, transparent)' : isBlocked ? 'color-mix(in srgb, var(--lys-status-warning) 4%, transparent)' : 'var(--lys-surface-0)'
                  }}
                  className="flex items-center gap-3.5 px-3 py-2 border cursor-pointer hover:border-lys-strong transition-colors"
                >
                  <span className="w-12 flex-shrink-0 font-mono-code text-[12px] text-lys-muted">
                    {p.id}
                  </span>
                  <span
                    style={{ color: isRunning ? 'var(--lys-text-primary)' : p.state === 'COMPLETED' ? 'var(--lys-text-muted)' : 'var(--lys-text-faint)' }}
                    className="w-16 flex-shrink-0 font-mono-code text-[11px] tracking-wider font-semibold"
                  >
                    {p.phase}
                  </span>
                  <span
                    style={{ color: agentCol }}
                    className="w-24 flex-shrink-0 flex items-center gap-1.5 text-[12px]"
                  >
                    <span
                      style={{ borderColor: agentCol }}
                      className="w-3.5 h-3.5 border flex items-center justify-center font-mono-code text-[10px] clip-hex"
                    >
                      {agentName[0]}
                    </span>
                    {agentName}
                  </span>
                  <span className="flex-1 min-w-0 text-[12px] text-lys-secondary truncate font-sans">
                    {p.task}
                  </span>
                  <span className="w-24 flex-shrink-0 text-right font-mono-code text-[11px] text-lys-faint">
                    {p.meta}
                  </span>
                  <span
                    style={{ color: stateCol }}
                    className="w-24 flex-shrink-0 flex items-center justify-end gap-1.5 font-mono-code text-[11px] tracking-wider font-semibold"
                  >
                    <span
                      style={{ backgroundColor: stateCol }}
                      className={`w-1.5 h-1.5 rounded-[1px]`}
                    />
                    {p.state}
                  </span>
                </div>

                {/* Connector Line */}
                {idx < pipeline.length - 1 && (
                  <div
                    style={{
                      backgroundColor: p.state === 'COMPLETED' ? 'color-mix(in srgb, var(--lys-status-success) 40%, transparent)' : 'var(--lys-border-subtle)'
                    }}
                    className="h-3 w-[1px] ml-5"
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Mission board: jobs grouped by their real status */}
      <MissionBoard
        jobs={jobs}
        loading={jobsLoading}
        error={jobsError}
        updatedAt={jobsUpdatedAt}
        onRetry={refetchJobs}
        onOpen={(id) => setActiveModalJobId(id)}
      />
      {jobsError && jobs.length > 0 && (
        <div className="px-5 pt-3.5">
          <StaleNotice label="Job queue" error={jobsError} onRetry={refetchJobs} />
        </div>
      )}

      {/* Recoverable jobs: read-only discovery from GET /jobs/recoverable. Resume and cancel are not offered here. */}
      <RecoverableJobs onSelect={(id) => setActiveModalJobId(id)} />

      <div className="px-5 pt-3.5 font-mono-code text-[11px] text-lys-faint">
        time estimates: not available (Hermes exposes no estimator) · concurrency policy: not reported by Hermes
      </div>
    </div>
  );
};

const RecoverableJobs: React.FC<{ onSelect: (jobId: string) => void }> = ({ onSelect }) => {
  const { jobs, loading, error, updatedAt, refetch } = useRecoverableJobs();
  return (
    <div className="p-5 border-t border-lys-subtle">
      <div className="flex items-center justify-between mb-2.5 font-mono-code text-[11px]">
        <span className="tracking-wider text-lys-faint">RECOVERABLE · {jobs.length} · read-only</span>
        <Freshness at={updatedAt} />
      </div>
      {loading && jobs.length === 0 && <LoadingState label="Loading recoverable jobs…" />}
      {error && <ErrorState label="Recoverable jobs" error={error} onRetry={refetch} />}
      {!loading && !error && jobs.length === 0 && (
        <EmptyState>No unfinished jobs are recoverable from the event ledger.</EmptyState>
      )}
      <div className="flex flex-col gap-1.5">
        {jobs.map((j) => (
          <button
            key={j.id}
            type="button"
            onClick={() => onSelect(j.id)}
            className="flex flex-wrap justify-between gap-2 p-2.5 bg-lys-surface-1 border border-lys-subtle text-left font-mono-code text-[11px] hover:border-lys-strong cursor-pointer"
          >
            <span className="text-lys-primary">{j.id}</span>
            <span className="text-lys-secondary font-sans">{j.title}</span>
            <span className="text-lys-muted">{j.status}</span>
          </button>
        ))}
      </div>
      <p className="mt-2 font-mono-code text-[11px] text-lys-faint">
        Resume and cancel are not available from this console.
      </p>
    </div>
  );
};

export default QueueRoute;
