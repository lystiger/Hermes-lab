import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ActiveExecutionCard } from '../features/jobs/ActiveExecutionCard';
import { AgentPresence } from '../features/agents/AgentPresence';
import { ProviderTelemetryList } from '../features/telemetry/ProviderTelemetryList';
import { useConsoleStore } from '../stores/useConsoleStore';
import { useAgents, useCapacityTelemetry, useJobs, useTelemetry } from '../api/hooks';
import { resolveActorPresentation } from '../api/actors';
import { eventKindColor } from '../features/events/eventKinds';
import { ErrorState, LoadingState, EmptyState, StaleNotice, UNKNOWN } from '../components/DataStates';
import { Card } from '../components/Card';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { NotReported, NotReportedItem } from '../components/NotReported';
import { HERMES_ART } from '../theme/agentArt';
import { UNKNOWN_TIME } from '../features/time/format';
import { eventTime } from './events';

const NOT_REPORTED: NotReportedItem[] = [
  { label: 'estimated spend', reason: 'Hermes reports no cost data, so no spend can be shown' },
  { label: 'sprint budget', reason: 'Hermes exposes no sprint budget or cap' },
  { label: 'queue projection', reason: 'Hermes has no projection or estimator for queued work' },
  { label: 'remaining budget', reason: 'Hermes exposes no budget to subtract from' }
];

export const OverviewRoute: React.FC = () => {
  const navigate = useNavigate();
  const { allEvents, setActiveModalJobId } = useConsoleStore();
  const { agents, loading: agentsLoading, error: agentsError, refetch: refetchAgents } = useAgents();
  const { jobs, loading: jobsLoading, error: jobsError, stale: jobsStale, refetch: refetchJobs } = useJobs();
  const { telemetry, error: telemetryError, refetch: refetchTelemetry } = useTelemetry();
  const { capacity } = useCapacityTelemetry();

  const recentTrace = allEvents.slice(0, 8);
  const queueShort = jobs.slice(0, 4);
  const providers = capacity?.providers ?? [];
  const processTokens = capacity?.summary?.totalTokens;

  const counts: HeaderCount[] = telemetry
    ? [
        { label: 'RUNNING', value: telemetry.runningJobsCount, tone: 'var(--lys-status-success)' },
        { label: 'QUEUED', value: telemetry.queuedJobsCount },
        { label: 'BLOCKED', value: telemetry.blockedJobsCount, tone: 'var(--lys-status-warning)' },
        {
          label: 'FAILED 24H',
          value: telemetry.failed24hCount ?? UNKNOWN,
          tone: telemetry.failed24hCount ? 'var(--lys-status-danger)' : undefined,
          title: telemetry.failed24hCount === null ? 'A failed job has no completion time, so the 24h window cannot be applied' : undefined
        },
        {
          label: 'TOKENS · SINCE START',
          value: typeof processTokens === 'number' ? processTokens : UNKNOWN,
          unit: typeof processTokens === 'number' ? 'tok' : undefined,
          title: 'Process total since runtime start, not today'
        }
      ]
    : [];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader
        title="Overview"
        subtitle={telemetry ? `Hermes runtime · counts from the latest ${telemetry.sampleSize} jobs (GET /jobs)` : 'Hermes runtime'}
        counts={counts}
      />

      {telemetryError && !telemetry && (
        <div className="px-6 pt-4">
          <ErrorState label="Metrics" error={telemetryError} onRetry={refetchTelemetry} />
        </div>
      )}

      <div className="flex-1 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-5 p-6 items-stretch">
        <div className="flex flex-col gap-5 min-w-0">
          <ActiveExecutionCard onOpenJob={(jobId) => setActiveModalJobId(jobId)} />

          {agentsLoading && agents.length === 0 ? (
            <Card><LoadingState label="Loading agents…" /></Card>
          ) : agentsError && agents.length === 0 ? (
            <Card><ErrorState label="Agent registry" error={agentsError} onRetry={refetchAgents} /></Card>
          ) : (
            <section aria-label="Agents" className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {agents.slice(0, 3).map((ag, i) => (
                <Card key={ag.id} accent={`var(--lys-agent-${ag.id.toLowerCase()}, var(--lys-text-muted))`}>
                  <AgentPresence agent={ag} index={i} onClick={() => navigate(`/agents/${ag.id}`)} />
                </Card>
              ))}
            </section>
          )}

          <Card label="Live trace" className="flex-1">
            <div className="p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] tracking-wider uppercase text-lys-faint">Live trace</span>
                <button onClick={() => navigate('/events')} className="text-[12px] text-lys-gold hover:underline cursor-pointer">
                  open events →
                </button>
              </div>
              {recentTrace.length === 0 ? (
                <EmptyState art={HERMES_ART}>No events received yet. Events appear here as Hermes emits them.</EmptyState>
              ) : (
                <div className="flex flex-col">
                  {recentTrace.map((e) => (
                    <div key={e.id} className="flex items-center gap-4 py-1.5 text-[12px] border-b border-lys-subtle last:border-b-0 hover:bg-lys-surface-2 px-1">
                      <span className="w-28 shrink-0 font-mono-code text-lys-faint">{eventTime(e)}</span>
                      <span className="w-28 shrink-0 font-semibold truncate" style={{ color: e.source.accentColor || 'var(--lys-text-muted)' }}>
                        {e.source.displayName}
                      </span>
                      <span className="w-40 shrink-0 truncate" style={{ color: eventKindColor(e.kind) }}>{e.kind}</span>
                      <span className="flex-1 min-w-0 text-lys-secondary truncate">{e.detail}</span>
                      <span className="w-16 shrink-0 text-right text-lys-faint">{e.dur}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>

        <aside className="flex flex-col gap-5 min-w-0">
          <Card label="Queue">
            <div className="p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] tracking-wider uppercase text-lys-faint">Queue · {jobsLoading && jobs.length === 0 ? '…' : jobs.length}</span>
                <button onClick={() => navigate('/queue')} className="text-[12px] text-lys-gold hover:underline cursor-pointer">
                  all →
                </button>
              </div>
              {jobsStale && <StaleNotice label="Job queue" error={jobsError} onRetry={refetchJobs} />}
              {jobsError && jobs.length === 0 && <ErrorState label="Job queue" error={jobsError} onRetry={refetchJobs} />}
              {!jobsError && !jobsLoading && jobs.length === 0 && (
                <EmptyState art={HERMES_ART}>No jobs returned by Hermes.</EmptyState>
              )}
              {queueShort.map((q) => (
                <button
                  key={q.id}
                  type="button"
                  onClick={() => setActiveModalJobId(q.id)}
                  className="text-left p-2.5 bg-lys-surface-2 hover:bg-lys-surface-interactive cursor-pointer border-l-2 border-lys-default"
                >
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-lys-faint font-mono-code">{q.id}</span>
                    <span className="ml-auto text-lys-muted tracking-wider">{q.status}</span>
                  </div>
                  <div className="mt-1 text-[13px] text-lys-primary truncate">{q.title}</div>
                  <div className="mt-0.5 text-[11px] text-lys-faint truncate">
                    {q.assignedAgentIds.map((id) => resolveActorPresentation(id, agents).displayName).join(' → ') || UNKNOWN_TIME}
                  </div>
                </button>
              ))}
            </div>
          </Card>

          {providers.length > 0 && (
            <Card label="Provider usage">
              <ProviderTelemetryList compact={true} />
            </Card>
          )}

          <NotReported items={providers.length === 0 ? [...NOT_REPORTED, { label: 'provider usage', reason: 'No provider has recorded a request in this runtime process yet' }] : NOT_REPORTED} />
        </aside>
      </div>
    </div>
  );
};

export default OverviewRoute;
