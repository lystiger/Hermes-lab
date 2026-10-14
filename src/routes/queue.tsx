import React from 'react';
import { QueueTable } from '../features/jobs/QueueTable';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useJobs, usePipeline, useAgents } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import { EmptyState, ErrorState, Freshness, LoadingState, StaleNotice } from '../components/DataStates';
import { useRecoverableJobs } from '../api/hooks';

export const QueueRoute: React.FC = () => {
  const { setActiveModalJobId, liveMotion } = useConsoleStore();
  const { jobs, loading: jobsLoading, error: jobsError, updatedAt: jobsUpdatedAt, refetch: refetchJobs } = useJobs();
  const { pipeline, loading: pipelineLoading, error: pipelineError, updatedAt: pipelineUpdatedAt, refetch: refetchPipeline } = usePipeline();
  const { agents } = useAgents();

  const getStateColor = (state: string) => {
    switch (state) {
      case 'COMPLETED': return '#5C646E';
      case 'RUNNING': return '#3FB950';
      case 'QUEUED': return '#8C949F';
      case 'CLAIMED': return '#CBA35C';
      case 'BLOCKED': return '#E3A008';
      case 'FAILED': return '#F2555A';
      default: return '#5C646E';
    }
  };

  return (
    <div className="flex flex-col pb-10 select-none bg-[#0A0B0D]">
      {/* Execution Order Pipeline Section */}
      <div className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <div className="flex items-center gap-3.5 mb-3 font-mono-code text-[11px]">
          <span className="tracking-wider text-[#5C646E]">EXECUTION ORDER</span>
          <span className="text-[#8C949F]">phases of the active job, in the order Hermes reports them</span>
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
            const agentCol = actor?.accentColor || '#8C949F';
            const stateCol = getStateColor(p.state);
            const agentName = p.agentName || actor?.displayName || '—';

            return (
              <div key={p.id || idx}>
                <div
                  onClick={() => p.jobId && setActiveModalJobId(p.jobId)}
                  style={{
                    borderColor: isRunning ? 'rgba(217,160,91,0.45)' : isBlocked ? 'rgba(227,160,8,0.3)' : '#1F242B',
                    backgroundColor: isRunning ? 'rgba(217,160,91,0.06)' : isBlocked ? 'rgba(227,160,8,0.04)' : '#0C0E11'
                  }}
                  className="flex items-center gap-3.5 px-3 py-2 border cursor-pointer hover:border-[#3A4048] transition-colors"
                >
                  <span className="w-12 flex-shrink-0 font-mono-code text-[12px] text-[#8C949F]">
                    {p.id}
                  </span>
                  <span
                    style={{ color: isRunning ? '#E6E9ED' : p.state === 'COMPLETED' ? '#8C949F' : '#5C646E' }}
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
                  <span className="flex-1 min-w-0 text-[12px] text-[#B7BEC7] truncate font-sans">
                    {p.task}
                  </span>
                  <span className="w-24 flex-shrink-0 text-right font-mono-code text-[11px] text-[#5C646E]">
                    {p.meta}
                  </span>
                  <span
                    style={{ color: stateCol }}
                    className="w-24 flex-shrink-0 flex items-center justify-end gap-1.5 font-mono-code text-[11px] tracking-wider font-semibold"
                  >
                    <span
                      style={{ backgroundColor: stateCol }}
                      className={`w-1.5 h-1.5 rounded-[1px] ${isRunning && liveMotion ? 'animate-pulse' : ''}`}
                    />
                    {p.state}
                  </span>
                </div>

                {/* Connector Line */}
                {idx < pipeline.length - 1 && (
                  <div
                    style={{
                      backgroundColor: p.state === 'COMPLETED' ? 'rgba(63,185,80,0.4)' : '#1F242B'
                    }}
                    className="h-3 w-[1px] ml-5"
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Queue Table */}
      <div className="px-5 pt-3.5">
        <Freshness at={jobsUpdatedAt} />
      </div>
      {jobsLoading && jobs.length === 0 && <LoadingState label="Loading jobs…" />}
      {jobsError && jobs.length === 0 && <ErrorState label="Job queue" error={jobsError} onRetry={refetchJobs} />}
      {jobsError && jobs.length > 0 && (
        <div className="px-5 pt-3.5">
          <StaleNotice label="Job queue" error={jobsError} onRetry={refetchJobs} />
        </div>
      )}
      {!jobsLoading && !jobsError && jobs.length === 0 && <EmptyState>No jobs returned by Hermes.</EmptyState>}
      <QueueTable
        jobs={jobs}
        onSelectJob={(id) => setActiveModalJobId(id)}
        showFilters={true}
      />

      {/* Recoverable jobs: read-only discovery from GET /jobs/recoverable. Resume and cancel are not offered here. */}
      <RecoverableJobs onSelect={(id) => setActiveModalJobId(id)} />

      <div className="px-5 pt-3.5 font-mono-code text-[11px] text-[#5C646E]">
        time estimates: not available (Hermes exposes no estimator) · concurrency policy: not reported by Hermes
      </div>
    </div>
  );
};

const RecoverableJobs: React.FC<{ onSelect: (jobId: string) => void }> = ({ onSelect }) => {
  const { jobs, loading, error, updatedAt, refetch } = useRecoverableJobs();
  return (
    <div className="p-5 border-t border-[#1F242B]">
      <div className="flex items-center justify-between mb-2.5 font-mono-code text-[11px]">
        <span className="tracking-wider text-[#5C646E]">RECOVERABLE · {jobs.length} · read-only</span>
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
            className="flex flex-wrap justify-between gap-2 p-2.5 bg-[#101216] border border-[#1F242B] text-left font-mono-code text-[11px] hover:border-[#3A4048] cursor-pointer"
          >
            <span className="text-[#E6E9ED]">{j.id}</span>
            <span className="text-[#B7BEC7] font-sans">{j.title}</span>
            <span className="text-[#8C949F]">{j.status}</span>
          </button>
        ))}
      </div>
      <p className="mt-2 font-mono-code text-[11px] text-[#5C646E]">
        Resume and cancel are not available from this console.
      </p>
    </div>
  );
};

export default QueueRoute;
