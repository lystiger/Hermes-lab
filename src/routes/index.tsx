import React from 'react';
import { useNavigate } from 'react-router-dom';
import { TopMetricsBar } from '../features/telemetry/TopMetricsBar';
import { ActiveExecutionCard } from '../features/jobs/ActiveExecutionCard';
import { AgentLaneCard } from '../features/agents/AgentLaneCard';
import { QueueProjectionBar } from '../features/jobs/QueueProjectionBar';
import { ProviderTelemetryList } from '../features/telemetry/ProviderTelemetryList';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useAgents, useJobs } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import { eventKindColor } from '../features/events/eventKinds';
import { ErrorState, LoadingState, EmptyState, Freshness, StaleNotice, UNKNOWN } from '../components/DataStates';

export const OverviewRoute: React.FC = () => {
  const navigate = useNavigate();
  const { allEvents, setActiveModalJobId } = useConsoleStore();
  const { agents, loading: agentsLoading, error: agentsError, refetch: refetchAgents } = useAgents();
  const { jobs, loading: jobsLoading, error: jobsError, updatedAt: jobsUpdatedAt, refetch: refetchJobs } = useJobs();

  const recentTrace = allEvents.slice(0, 8);
  const queueShort = jobs.slice(0, 4);

  const getPrioColor = (p?: string) => {
    if (p === 'P0') return 'var(--lys-status-danger)';
    if (p === 'P1') return 'var(--lys-status-warning)';
    return 'var(--lys-text-muted)';
  };

  return (
    <div className="flex flex-col min-h-0 select-none">
      {/* Top Telemetry Metrics Bar */}
      <TopMetricsBar />

      {/* Main Split Body: Left Main (Execution + Lanes + Live Trace), Right Rail */}
      <div className="flex flex-col xl:flex-row items-stretch flex-wrap min-h-0">
        {/* Left Column */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Active Execution Banner */}
          <ActiveExecutionCard onOpenJob={(jobId) => setActiveModalJobId(jobId)} />

          {/* Agent Lanes Row */}
          {agentsLoading && agents.length === 0 ? (
            <LoadingState label="Loading agents…" />
          ) : agentsError && agents.length === 0 ? (
            <ErrorState label="Agent registry" error={agentsError} onRetry={refetchAgents} />
          ) : (
            <div className="flex items-stretch flex-wrap border-b border-lys-subtle">
              {agents.slice(0, 3).map((ag) => (
                <AgentLaneCard key={ag.id} agent={ag} size="compact" />
              ))}
            </div>
          )}

          {/* Live Trace Stream */}
          <div className="p-5">
            <div className="flex items-center justify-between mb-2.5">
              <span className="font-mono-code text-[11px] tracking-wider text-lys-faint">
                LIVE TRACE
              </span>
              <button
                onClick={() => navigate('/events')}
                className="font-mono-code text-[11px] text-lys-gold hover:underline cursor-pointer"
              >
                open events →
              </button>
            </div>

            <div className="flex flex-col">
              {recentTrace.length === 0 && <EmptyState>No events received yet.</EmptyState>}
              {recentTrace.map((e) => {
                const actorColor = e.source.accentColor || 'var(--lys-text-muted)';
                return (
                  <div
                    key={e.id}
                    className="flex items-center gap-4 py-1 font-mono-code text-[11px] border-b border-lys-subtle hover:bg-lys-surface-1 px-1 transition-colors"
                  >
                    <span className="w-24 text-lys-faint">{e.ts}</span>
                    <span
                      style={{ color: actorColor }}
                      className="w-16 font-semibold"
                    >
                      {e.source.displayName}
                    </span>
                    <span
                      style={{ color: eventKindColor(e.kind) }}
                      className="w-28"
                    >
                      {e.kind}
                    </span>
                    <span className="flex-1 min-w-0 text-lys-secondary truncate font-sans">
                      {e.detail}
                    </span>
                    <span className="w-16 text-right text-lys-faint">{e.dur}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Rail */}
        <div className="w-full xl:w-80 flex-shrink-0 border-l border-lys-subtle bg-lys-surface-0 flex flex-col">
          {/* Queue Shortlist */}
          <div className="p-4 border-b border-lys-subtle">
            <div className="flex items-center justify-between mb-3">
              <span className="font-mono-code text-[11px] tracking-wider text-lys-faint">
                QUEUE · {jobsLoading && jobs.length === 0 ? '…' : jobs.length}
              </span>
              <button
                onClick={() => navigate('/queue')}
                className="font-mono-code text-[11px] text-lys-gold hover:underline cursor-pointer"
              >
                all →
              </button>
            </div>

            {jobsError && jobs.length === 0 && (
              <ErrorState label="Job queue" error={jobsError} onRetry={refetchJobs} />
            )}
            {jobsError && jobs.length > 0 && (
              <StaleNotice label="Job queue" error={jobsError} onRetry={refetchJobs} />
            )}
            {!jobsError && !jobsLoading && jobs.length === 0 && (
              <EmptyState>No jobs returned by Hermes.</EmptyState>
            )}
            <div className="mb-2">
              <Freshness at={jobsUpdatedAt} />
            </div>

            <div className="flex flex-col gap-1">
              {queueShort.map((q) => {
                const leadActor = q.assignedAgentIds[0] ? resolveActorPresentation(q.assignedAgentIds[0], agents) : null;
                const leadColor = leadActor?.accentColor || 'var(--lys-text-muted)';

                return (
                  <div
                    key={q.id}
                    onClick={() => setActiveModalJobId(q.id)}
                    style={{ borderLeftColor: getPrioColor(q.priority) }}
                    className="p-2.5 bg-lys-surface-1 border-l-2 hover:bg-lys-surface-2 cursor-pointer transition-colors"
                  >
                    <div className="flex items-center gap-2 font-mono-code text-[11px]">
                      <span style={{ color: getPrioColor(q.priority) }} className="font-semibold">{q.priority || UNKNOWN}</span>
                      <span className="text-lys-faint">{q.id}</span>
                      <span className="flex-1 min-w-0 text-[12px] text-lys-primary font-sans truncate">{q.title}</span>
                      <span className="text-lys-muted tracking-wider">{q.status}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1.5 font-mono-code text-[11px] text-lys-faint">
                      <span className="truncate">{q.repository}</span>
                      <span style={{ color: leadColor }}>
                        {q.assignedAgentIds.map(id => resolveActorPresentation(id, agents).displayName).join(' → ')}
                      </span>
                      <span className="flex-1 text-right">{q.estimatedTime || '—'}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Queue Projection Bar */}
          <QueueProjectionBar compact={true} />

          {/* Provider Quotas */}
          <ProviderTelemetryList compact={true} />
        </div>
      </div>
    </div>
  );
};

export default OverviewRoute;
