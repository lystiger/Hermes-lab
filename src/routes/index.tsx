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
import { ErrorState, LoadingState, EmptyState, Freshness, StaleNotice } from '../components/DataStates';

export const OverviewRoute: React.FC = () => {
  const navigate = useNavigate();
  const { allEvents, setActiveModalJobId } = useConsoleStore();
  const { agents, loading: agentsLoading, error: agentsError, refetch: refetchAgents } = useAgents();
  const { jobs, loading: jobsLoading, error: jobsError, updatedAt: jobsUpdatedAt, refetch: refetchJobs } = useJobs();

  const recentTrace = allEvents.slice(0, 8);
  const queueShort = jobs.slice(0, 4);

  const getPrioColor = (p: string) => {
    if (p === 'P0') return '#F2555A';
    if (p === 'P1') return '#E3A008';
    return '#8C949F';
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
            <div className="flex items-stretch flex-wrap border-b border-[#1F242B]">
              {agents.slice(0, 3).map((ag) => (
                <AgentLaneCard key={ag.id} agent={ag} size="compact" />
              ))}
            </div>
          )}

          {/* Live Trace Stream */}
          <div className="p-5">
            <div className="flex items-center justify-between mb-2.5">
              <span className="font-mono-code text-[11px] tracking-wider text-[#5C646E]">
                LIVE TRACE
              </span>
              <button
                onClick={() => navigate('/events')}
                className="font-mono-code text-[11px] text-[#CBA35C] hover:underline cursor-pointer"
              >
                open events →
              </button>
            </div>

            <div className="flex flex-col">
              {recentTrace.length === 0 && <EmptyState>No events received yet.</EmptyState>}
              {recentTrace.map((e) => {
                const actorColor = e.source.accentColor || '#8C949F';
                return (
                  <div
                    key={e.id}
                    className="flex items-center gap-4 py-1 font-mono-code text-[11px] border-b border-[#14171C] hover:bg-[#12151A] px-1 transition-colors"
                  >
                    <span className="w-24 text-[#5C646E]">{e.ts}</span>
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
                    <span className="flex-1 min-w-0 text-[#B7BEC7] truncate font-sans">
                      {e.detail}
                    </span>
                    <span className="w-16 text-right text-[#5C646E]">{e.dur}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Rail */}
        <div className="w-full xl:w-80 flex-shrink-0 border-l border-[#1F242B] bg-[#0C0E11] flex flex-col">
          {/* Queue Shortlist */}
          <div className="p-4 border-b border-[#1F242B]">
            <div className="flex items-center justify-between mb-3">
              <span className="font-mono-code text-[11px] tracking-wider text-[#5C646E]">
                QUEUE · {jobsLoading && jobs.length === 0 ? '…' : jobs.length}
              </span>
              <button
                onClick={() => navigate('/queue')}
                className="font-mono-code text-[11px] text-[#CBA35C] hover:underline cursor-pointer"
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
                const leadColor = leadActor?.accentColor || '#8C949F';

                return (
                  <div
                    key={q.id}
                    onClick={() => setActiveModalJobId(q.id)}
                    style={{ borderLeftColor: getPrioColor(q.priority || 'P1') }}
                    className="p-2.5 bg-[#101216] border-l-2 hover:bg-[#161A20] cursor-pointer transition-colors"
                  >
                    <div className="flex items-center gap-2 font-mono-code text-[11px]">
                      <span style={{ color: getPrioColor(q.priority || 'P1') }} className="font-semibold">{q.priority || 'P1'}</span>
                      <span className="text-[#5C646E]">{q.id}</span>
                      <span className="flex-1 min-w-0 text-[12px] text-[#D7DCE2] font-sans truncate">{q.title}</span>
                      <span className="text-[#8C949F] tracking-wider">{q.status}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1.5 font-mono-code text-[11px] text-[#5C646E]">
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
