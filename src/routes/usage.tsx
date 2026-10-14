import React from 'react';
import { TokenBudgetMeter } from '../features/telemetry/TokenBudgetMeter';
import { ProviderTelemetryList } from '../features/telemetry/ProviderTelemetryList';
import { QueueProjectionBar } from '../features/jobs/QueueProjectionBar';
import { useAgents } from '../api/hooks';
import { ErrorState, LoadingState, EmptyState, UNKNOWN } from '../components/DataStates';

export const UsageRoute: React.FC = () => {
  const { agents, loading, error, refetch } = useAgents();

  return (
    <div className="flex flex-col pb-10 select-none bg-[#0A0B0D]">
      <div className="px-5 py-2.5 bg-[#0C0E11] border-b border-[#1F242B] font-mono-code text-[11px] text-[#8C949F]">
        Usage is not measured in this build. Hermes does not report token, budget or provider figures yet,
        so those values show as {UNKNOWN} rather than zero.
      </div>

      {/* 3-Column Top Grid: Context Windows, Run Budget, Provider Quotas */}
      <div className="grid grid-cols-1 lg:grid-cols-3 border-b border-[#1F242B]">
        {/* 1 · CONTEXT WINDOWS */}
        <div className="p-5 border-b lg:border-b-0 border-r border-[#1F242B] bg-[#0A0B0D]">
          <div className="text-[11px] tracking-wider text-[#5C646E] font-mono-code">
            1 · CONTEXT WINDOWS
          </div>
          <div className="mt-1 text-[11px] text-[#5C646E] mb-4">
            per-agent, resets each run
          </div>

          {loading && agents.length === 0 && <LoadingState label="Loading agents…" />}
          {error && agents.length === 0 && <ErrorState label="Agent registry" error={error} onRetry={refetch} />}
          {!loading && !error && agents.length === 0 && <EmptyState>No agents registered.</EmptyState>}

          <div className="flex flex-col gap-4">
            {agents.map((a) => {
              const accentColor = a.presentation?.accentColor || '#8C949F';
              const hasPct = a.contextPct !== undefined;
              return (
                <div key={a.id}>
                  <div className="flex justify-between items-baseline font-mono-code text-[11px]">
                    <span style={{ color: accentColor }}>{a.displayName} · {a.model}</span>
                    <span className="text-[#8C949F]">{a.contextUsed ?? UNKNOWN} / {a.contextMax ?? UNKNOWN}</span>
                  </div>
                  <div className="mt-1.5 h-2 bg-[#14171C] relative">
                    {hasPct && (
                      <div
                        style={{ width: a.contextPct, backgroundColor: accentColor }}
                        className="absolute left-0 top-0 bottom-0"
                      />
                    )}
                    <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
                  </div>
                  <div className="mt-1 flex justify-between font-mono-code text-[11px] text-[#5C646E]">
                    <span>{hasPct ? `${a.contextPct} used` : `context ${UNKNOWN} (not reported)`}</span>
                    <span>{a.sessionTokens ?? UNKNOWN} session</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 2 · RUN BUDGET */}
        <TokenBudgetMeter />

        {/* 3 · PROVIDER QUOTA */}
        <ProviderTelemetryList compact={false} />
      </div>

      {/* 4 · QUEUE PROJECTION */}
      <QueueProjectionBar compact={false} />
    </div>
  );
};

export default UsageRoute;
