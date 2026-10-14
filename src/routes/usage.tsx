import React from 'react';
import { TokenBudgetMeter } from '../features/telemetry/TokenBudgetMeter';
import { QueueProjectionBar } from '../features/jobs/QueueProjectionBar';
import { useAgents, useCapacityTelemetry } from '../api/hooks';
import { ErrorState, Freshness, LoadingState, EmptyState, UnknownValue } from '../components/DataStates';
import { Meter, PROCESS_WINDOW, ProviderMeters } from '../features/telemetry/UsageMeters';
import { UNKNOWN_TIME } from '../features/time/format';

/** Usage (research §5.5): meters from capacity telemetry, each with the window it covers. */
export const UsageRoute: React.FC = () => {
  const { agents } = useAgents();
  const { capacity, loading, error, updatedAt, refetch } = useCapacityTelemetry();

  const providers = capacity?.providers ?? [];
  const requests = providers.reduce((sum, p) => sum + p.totalRequests, 0);
  const successes = providers.reduce((sum, p) => sum + p.successCount, 0);
  const aggregateRate = requests > 0 ? Math.round((successes / requests) * 100) : null;

  return (
    <div className="flex flex-col pb-10 select-none bg-lys-base">
      <div className="px-5 py-2.5 border-b border-lys-subtle bg-lys-surface-0 flex flex-wrap items-center justify-between gap-2 font-mono-code text-[11px] text-lys-muted">
        <span>
          Every total here covers <span className="text-lys-primary">{PROCESS_WINDOW}</span>. Unknown values are not zero.
        </span>
        <Freshness at={updatedAt} />
      </div>

      {loading && !capacity && <LoadingState label="Loading capacity telemetry…" />}
      {error && !capacity && <ErrorState label="Capacity telemetry" error={error} onRetry={refetch} />}
      {error && capacity && (
        <div role="alert" className="m-4 font-mono-code text-[11px] text-lys-warning">
          refresh failed, showing last loaded data: {error.message}
        </div>
      )}

      {capacity && (
        <>
          <section aria-label="Totals" className="grid grid-cols-1 md:grid-cols-3 gap-4 p-5 border-b border-lys-subtle">
            <div className="p-4 bg-lys-surface-1 border border-lys-subtle">
              <Meter
                label="TOKENS"
                value={capacity.summary?.totalTokens}
                unit="tok"
                window={PROCESS_WINDOW}
                unknownReason="Capacity report has no summary"
                tone="var(--lys-accent-gold)"
                note={capacity.summary ? `${capacity.summary.inputTokens ?? '—'} in · ${capacity.summary.outputTokens ?? '—'} out` : undefined}
              />
            </div>
            <div className="p-4 bg-lys-surface-1 border border-lys-subtle">
              <Meter
                label="SUCCESS RATE"
                value={aggregateRate}
                limit={100}
                unit="%"
                window={PROCESS_WINDOW}
                unknownReason="No requests have been made, so no success rate exists"
                tone="var(--lys-status-success)"
                note={`${requests} requests · ${capacity.summary?.totalFailures ?? requests - successes} failed`}
              />
            </div>
            <div className="p-4 bg-lys-surface-1 border border-lys-subtle">
              <Meter
                label="THROTTLING EVENTS"
                value={capacity.summary?.totalThrottlingEvents}
                window={PROCESS_WINDOW}
                unknownReason="Capacity report has no summary"
                tone="var(--lys-status-warning)"
                note={`${capacity.jobsTracked ?? UNKNOWN_TIME} jobs tracked`}
              />
            </div>
          </section>

          <section aria-label="Provider meters" className="p-5 flex flex-col gap-4 border-b border-lys-subtle">
            <div className="font-mono-code text-[11px] tracking-wider text-lys-faint">PROVIDERS · {providers.length}</div>
            {providers.length === 0 ? (
              <EmptyState>No provider has recorded a request in this runtime process yet.</EmptyState>
            ) : (
              providers.map((p) => <ProviderMeters key={p.providerId} provider={p} />)
            )}
          </section>
        </>
      )}

      <section aria-label="Run budget and context" className="grid grid-cols-1 lg:grid-cols-2 border-b border-lys-subtle">
        <TokenBudgetMeter />
        <div className="p-5 select-none">
          <div className="text-[11px] tracking-wider text-lys-faint font-mono-code">AGENT CONTEXT WINDOWS</div>
          <div className="mt-1 text-[11px] text-lys-faint mb-3">Hermes does not report context per agent.</div>
          <div className="flex flex-col gap-2 font-mono-code text-[11px]">
            {agents.map((a) => (
              <div key={a.id} className="flex justify-between text-lys-muted">
                <span style={{ color: a.presentation?.accentColor }}>{a.displayName}</span>
                <UnknownValue reason="Hermes reports no context usage for this agent" />
              </div>
            ))}
          </div>
        </div>
      </section>

      <QueueProjectionBar compact={false} />
    </div>
  );
};

export default UsageRoute;
