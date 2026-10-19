import React from 'react';
import { useCapacityTelemetry } from '../api/hooks';
import { ErrorState, LoadingState } from '../components/DataStates';
import { Card } from '../components/Card';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { NotReportedItem } from '../components/NotReported';
import { Meter, ProviderMeters } from '../features/telemetry/UsageMeters';

const NOT_REPORTED: NotReportedItem[] = [
  { label: 'run budget', reason: 'Hermes exposes no per-run token budget or cap' },
  { label: 'sprint budget', reason: 'Hermes exposes no sprint budget, so no percentage can be computed' },
  { label: 'queue projection', reason: 'Hermes has no projection source for queued work' },
  { label: 'per-agent context', reason: 'Hermes reports no context usage for each agent' }
];

/** Usage (research §5.5): meters from capacity telemetry, each labelled with the window it covers. */
export const UsageRoute: React.FC = () => {
  const { capacity, loading, error, refetch, updatedAt } = useCapacityTelemetry();

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
        subtitle="since runtime start (process lifetime, not daily)"
        counts={counts}
        notReported={[
          ...NOT_REPORTED,
          ...(capacity && providers.length === 0
            ? [{ label: 'provider usage', reason: 'No provider has recorded a request in this runtime process yet' }]
            : [])
        ]}
      />

      <div className="flex-1 flex flex-col gap-6 p-6">
        {loading && !capacity && <Card><LoadingState label="Loading capacity telemetry…" /></Card>}
        {error && !capacity && <Card><ErrorState label="Capacity telemetry" error={error} onRetry={refetch} /></Card>}

        {capacity && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            <Card accent="var(--lys-accent-gold)" label="Tokens">
              <div className="p-5">
                <Meter
                  label="TOKENS"
                  value={capacity.summary?.totalTokens}
                  unit="tok"
                  unknownReason="Capacity report has no summary"
                  tone="var(--lys-accent-gold)"
                  note={capacity.summary ? `${capacity.summary.inputTokens ?? '—'} in · ${capacity.summary.outputTokens ?? '—'} out` : undefined}
                />
              </div>
            </Card>
            <Card accent="var(--lys-status-success)" label="Success rate">
              <div className="p-5">
                <Meter
                  label="SUCCESS RATE"
                  value={aggregateRate}
                  limit={100}
                  unit="%"
                  unknownReason="No requests have been made, so no success rate exists"
                  tone="var(--lys-status-success)"
                  note={`${requests} requests · ${capacity.summary?.totalFailures ?? requests - successes} failed`}
                />
              </div>
            </Card>
            <Card accent="var(--lys-status-warning)" label="Throttling">
              <div className="p-5">
                <Meter
                  label="THROTTLING EVENTS"
                  value={capacity.summary?.totalThrottlingEvents}
                  unknownReason="Capacity report has no summary"
                  tone="var(--lys-status-warning)"
                  note={`${capacity.jobsTracked ?? '—'} jobs tracked`}
                />
              </div>
            </Card>

            {providers.map((p) => (
              <Card key={p.providerId} label={`Meters for ${p.providerId}`}>
                <ProviderMeters provider={p} />
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default UsageRoute;
