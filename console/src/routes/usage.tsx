import React from 'react';
import { useAgentLimits, useCapacityTelemetry } from '../api/hooks';
import { CAPACITY_WINDOW_LABEL } from '../api/mapping';
import { AgentLimit } from '../api/types';
import { EmptyState, ErrorState, LoadingState, StaleNotice } from '../components/DataStates';
import { Badge } from '../components/Badge';
import { Card } from '../components/Card';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { formatResetIn, statusTone, StatusTone } from '../features/usage/format';

const TONE_COLOR: Record<StatusTone, string> = {
  success: 'var(--lys-status-success)',
  warning: 'var(--lys-status-warning)',
  danger: 'var(--lys-status-danger)',
  muted: 'var(--lys-text-muted)'
};

/** The status shown on the badge: readiness and staleness come before the backend's own status. */
function displayStatus(agent: AgentLimit): string {
  if (!agent.ready) return 'not ready';
  if (agent.stale) return 'stale';
  return agent.status;
}

const AgentLimitCard: React.FC<{ agent: AgentLimit }> = ({ agent }) => {
  const status = displayStatus(agent);
  // The bar keeps the backend's colour for a stale reading; only the badge says it is stale.
  const barColor = TONE_COLOR[statusTone(agent.status)];

  return (
    <Card as="section" label={`Limits for ${agent.name}`} bodyClassName="p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="min-w-0 truncate font-sans text-[13px] text-lys-primary">
          {agent.name}
          {agent.plan && <span className="text-lys-muted"> · {agent.plan}</span>}
        </div>
        <Badge label={status} color={TONE_COLOR[statusTone(status)]} />
      </div>

      {agent.ready ? (
        <>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-[34px] leading-none font-semibold lys-metric text-lys-primary">{agent.leftPct === null ? '—' : `${agent.leftPct}%`}</span>
            {agent.leftPct !== null && <span className="text-[12px] text-lys-faint">left</span>}
          </div>
          <div
            role="progressbar"
            aria-label={`${agent.name} remaining`}
            aria-valuemin={0}
            aria-valuemax={100}
            {...(agent.leftPct === null ? {} : { 'aria-valuenow': agent.leftPct })}
            className="h-1.5 w-full bg-lys-subtle"
          >
            {agent.leftPct !== null && <div className="h-full" style={{ width: `${agent.leftPct}%`, background: barColor }} />}
          </div>
          {agent.resetsAt && <div className="text-[11px] text-lys-muted">resets in {formatResetIn(agent.resetsInSeconds)}</div>}
          {agent.windows.length > 0 && (
            <ul className="flex flex-col gap-1 pt-2 border-t border-lys-subtle/50">
              {agent.windows.map((w) => (
                <li key={w.label} className="flex items-baseline justify-between gap-2 text-[11px]">
                  <span className="text-lys-muted">{w.label}</span>
                  <span className="text-lys-primary lys-metric">{w.leftPct === null ? '—' : `${w.leftPct}%`}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="text-[12px] text-lys-secondary break-words">{agent.authHelp}</p>
      )}
    </Card>
  );
};

/** Usage: what is left for each agent, as computed by Hermes, plus the runtime totals in the header. */
export const UsageRoute: React.FC = () => {
  const telemetry = useCapacityTelemetry();
  const { limits, loading, error, stale, refetch, updatedAt } = useAgentLimits();

  const capacity = telemetry.capacity;
  const providers = capacity?.providers ?? [];
  const requests = providers.reduce((sum, p) => sum + p.totalRequests, 0);
  const successes = providers.reduce((sum, p) => sum + p.successCount, 0);
  const successRate = requests > 0 ? Math.round((successes / requests) * 100) : null;
  const tokens = capacity?.summary?.totalTokens;
  const throttling = capacity?.summary?.totalThrottlingEvents;

  // Totals are process-lifetime, so the window is stated on hover rather than as extra words on the page.
  const title = CAPACITY_WINDOW_LABEL;
  const counts: HeaderCount[] = [
    { label: 'TOKENS', value: typeof tokens === 'number' ? tokens.toLocaleString() : '—', title },
    { label: 'REQUESTS', value: capacity ? requests : '—', title },
    { label: 'SUCCESS RATE', value: successRate === null ? '—' : successRate, unit: successRate === null ? undefined : '%', title },
    { label: 'THROTTLING', value: typeof throttling === 'number' ? throttling : '—', title }
  ];

  const agents = limits?.agents ?? [];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader updatedAt={updatedAt} title="Usage" counts={counts} />

      <div className="flex-1 flex flex-col gap-6 p-6">
        {stale && <StaleNotice label="Agent limits" error={error} onRetry={refetch} />}
        {loading && !limits && <Card><LoadingState label="Loading agent limits…" /></Card>}
        {error && !limits && <Card><ErrorState label="Agent limits" error={error} onRetry={refetch} /></Card>}

        {limits &&
          (agents.length === 0 ? (
            <Card><EmptyState>No agent limits</EmptyState></Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {agents.map((agent) => <AgentLimitCard key={agent.id} agent={agent} />)}
            </div>
          ))}
      </div>
    </div>
  );
};

export default UsageRoute;
