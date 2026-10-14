import React from 'react';
import { useCapacityTelemetry } from '../../api/hooks';
import { CAPACITY_WINDOW_LABEL } from '../../api/mapping';
import { ProviderTelemetry, UsageSnapshotView } from '../../api/types';
import { EmptyState, ErrorState, Freshness, LoadingState, UNKNOWN, UnknownValue, isKnown } from '../../components/DataStates';

const NO_PROVIDERS = 'No provider usage reported by Hermes. The provider registry has recorded no requests yet.';

/** Label for where a usage figure came from. Estimates are never shown as provider-reported facts. */
export function sourceLabel(source: string | null | undefined): { text: string; color: string } {
  switch (source) {
    case 'provider_reported':
      return { text: 'provider reported', color: '#3FB950' };
    case 'hermes_estimated':
      return { text: 'estimated by Hermes', color: '#E3A008' };
    default:
      return { text: 'source unknown', color: '#8C949F' };
  }
}

const orUnknown = (value: number | null | undefined, reason: string) =>
  isKnown(value) ? <>{value}</> : <UnknownValue reason={reason} />;

const ProviderRow: React.FC<{ provider: ProviderTelemetry; compact: boolean }> = ({ provider, compact }) => {
  const usage: UsageSnapshotView | null = provider.usage;
  const src = sourceLabel(usage?.source);
  const rate = provider.successRate === null ? (
    <UnknownValue reason="No requests have been made, so no success rate exists" />
  ) : (
    `${Math.round(provider.successRate * 100)}%`
  );

  return (
    <div className={`p-3 bg-[#101216] border border-[#1F242B] font-mono-code text-[11px] ${compact ? '' : 'mb-3'}`}>
      <div className="flex items-center justify-between">
        <span className="text-[12px] text-[#E6E9ED] font-semibold">{provider.providerId}</span>
        <span className="text-[#8C949F] tracking-wider">{provider.status}</span>
      </div>
      {provider.statusReason && <div className="mt-1 text-[#5C646E]">{provider.statusReason}</div>}

      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[#8C949F]">
        <span>requests <span className="text-[#E6E9ED]">{provider.totalRequests}</span></span>
        <span>success rate <span className="text-[#E6E9ED]">{rate}</span></span>
        <span>failures <span className="text-[#E6E9ED]">{provider.failureCount}</span></span>
        <span>throttled <span className="text-[#E6E9ED]">{provider.throttlingCount}</span></span>
      </div>

      {!compact && (
        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[#8C949F]">
          <span>tokens used <span className="text-[#E6E9ED]">{orUnknown(usage?.tokensUsed, 'Provider did not report token usage')}</span></span>
          <span>requests left <span className="text-[#E6E9ED]">{orUnknown(usage?.requestsRemaining, 'Provider did not report a remaining request count')}</span></span>
          <span>context <span className="text-[#E6E9ED]">{orUnknown(usage?.contextUsed, 'Provider did not report context use')}</span>
            {' / '}
            {orUnknown(usage?.contextWindow, 'Provider did not report a context window')}
          </span>
          <span>resets <span className="text-[#E6E9ED]">{usage?.resetAt ?? UNKNOWN}</span></span>
        </div>
      )}

      <div className="mt-2 flex flex-wrap justify-between gap-2 text-[#5C646E]">
        <span style={{ color: src.color }}>{src.text}</span>
        <span>{CAPACITY_WINDOW_LABEL}</span>
      </div>
    </div>
  );
};

/** Provider measurements from GET /capacity/telemetry. Every total is labelled as since runtime start. */
export const ProviderTelemetryList: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { capacity, loading, error, updatedAt, refetch } = useCapacityTelemetry();

  if (loading && !capacity) return <LoadingState label="Loading provider telemetry…" />;
  if (error && !capacity) return <ErrorState label="Provider telemetry" error={error} onRetry={refetch} />;
  if (!capacity) return null;

  return (
    <div className={compact ? 'p-3.5 select-none' : 'p-5 select-none'}>
      <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-1">
        {compact ? 'PROVIDER USAGE' : '3 · PROVIDER USAGE'}
      </div>
      <div className="font-mono-code text-[11px] text-[#5C646E] mb-3">{CAPACITY_WINDOW_LABEL}</div>

      {error && (
        <div role="alert" className="mb-2 font-mono-code text-[11px] text-[#E3A008]">
          refresh failed, showing last loaded data: {error.message}
        </div>
      )}

      {capacity.providers.length === 0 ? (
        <EmptyState>{NO_PROVIDERS}</EmptyState>
      ) : (
        capacity.providers.map((p) => <ProviderRow key={p.providerId} provider={p} compact={compact} />)
      )}

      {!compact && (
        <div className="mt-2 font-mono-code text-[11px] text-[#5C646E]">
          {capacity.summary ? (
            <span>
              {capacity.summary.totalProviders ?? UNKNOWN} providers · {capacity.summary.totalRequests ?? UNKNOWN} requests ·{' '}
              {capacity.summary.totalTokens ?? UNKNOWN} tokens · {capacity.jobsTracked ?? UNKNOWN} jobs tracked
            </span>
          ) : (
            <span>summary not reported</span>
          )}{' '}
          <Freshness at={updatedAt} />
        </div>
      )}
    </div>
  );
};
