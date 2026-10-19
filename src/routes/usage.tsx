import React from 'react';
import { useCapacityTelemetry } from '../api/hooks';
import { EmptyState, ErrorState, LoadingState, StaleNotice } from '../components/DataStates';
import { Card } from '../components/Card';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { NotReportedItem } from '../components/NotReported';
import { ProviderMeters } from '../features/telemetry/UsageMeters';

const NOT_REPORTED: NotReportedItem[] = [
  { label: 'run budget', reason: 'Hermes exposes no per-run token budget or cap' },
  { label: 'sprint budget', reason: 'Hermes exposes no sprint budget, so no percentage can be computed' },
  { label: 'queue projection', reason: 'Hermes has no projection source for queued work' },
  { label: 'per-agent context', reason: 'Hermes reports no context usage for each agent' },
  { label: 'measurement window', reason: 'Metrics cover since runtime start (process lifetime, not daily)' }
];

/** Usage (research §5.5): meters from capacity telemetry, each labelled with the window it covers. */
export const UsageRoute: React.FC = () => {
  const { capacity, loading, error, stale, refetch, updatedAt } = useCapacityTelemetry();

  const providers = capacity?.providers ?? [];
  const requests = providers.reduce((sum, p) => sum + p.totalRequests, 0);
  const successes = providers.reduce((sum, p) => sum + p.successCount, 0);
  const aggregateRate = requests > 0 ? Math.round((successes / requests) * 100) : null;
  const tokens = capacity?.summary?.totalTokens;

  const counts: HeaderCount[] = capacity
    ? [
        { label: 'TOKENS', value: typeof tokens === 'number' ? tokens.toLocaleString() : '—', unit: 'tok' },
        { label: 'REQUESTS', value: requests },
        { label: 'SUCCESS RATE', value: aggregateRate === null ? '—' : aggregateRate, unit: aggregateRate === null ? undefined : '%' },
        { label: 'THROTTLING', value: capacity.summary?.totalThrottlingEvents ?? '—' }
      ]
    : [];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader
        updatedAt={updatedAt}
        title="Usage"
        subtitle="Capacity and limits"
        counts={counts}
        notReported={[
          ...NOT_REPORTED,
          ...(capacity && providers.length === 0
            ? [{ label: 'provider usage', reason: 'No provider has recorded a request in this runtime process yet' }]
            : [])
        ]}
      />

      <div className="flex-1 flex flex-col gap-6 p-6">
        {stale && <StaleNotice label="Capacity telemetry" error={error} onRetry={refetch} />}
        {loading && !capacity && <Card><LoadingState label="Loading capacity telemetry…" /></Card>}
        {error && !capacity && <Card><ErrorState label="Capacity telemetry" error={error} onRetry={refetch} /></Card>}

        {capacity && (
          <div className="flex flex-col gap-4">
            <div className="text-[11px] text-lys-faint">since runtime start (process lifetime, not daily)</div>
            {providers.length === 0 ? (
              <Card><EmptyState>No provider usage</EmptyState></Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {providers.map((p) => (
                  <Card key={p.providerId} label={`Meters for ${p.providerId}`}>
                    <ProviderMeters provider={p} />
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default UsageRoute;
