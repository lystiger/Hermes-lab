import React from 'react';
import { TokenBudgetMeter } from '../features/telemetry/TokenBudgetMeter';
import { ProviderQuotaList } from '../features/telemetry/ProviderQuotaList';
import { QueueProjectionBar } from '../features/jobs/QueueProjectionBar';
import { useAgents } from '../api/hooks';

export const UsageRoute: React.FC = () => {
  const { agents } = useAgents();

  return (
    <div className="flex flex-col pb-10 select-none bg-[#0A0B0D]">
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

          <div className="flex flex-col gap-4">
            {agents.map((a) => {
              const accentColor = a.presentation?.accentColor || '#8C949F';
              const contextPct = a.contextPct || '25%';
              return (
                <div key={a.id}>
                  <div className="flex justify-between items-baseline font-mono-code text-[11px]">
                    <span style={{ color: accentColor }}>{a.displayName} · {a.model}</span>
                    <span className="text-[#8C949F]">{a.contextUsed || '0k'} / {a.contextMax || '200k'}</span>
                  </div>
                  <div className="mt-1.5 h-2 bg-[#14171C] relative">
                    <div
                      style={{ width: contextPct, backgroundColor: accentColor }}
                      className="absolute left-0 top-0 bottom-0"
                    />
                    <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
                  </div>
                  <div className="mt-1 flex justify-between font-mono-code text-[11px] text-[#5C646E]">
                    <span>{contextPct} used</span>
                    <span>{a.sessionTokens || 'active'}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 2 · RUN BUDGET */}
        <TokenBudgetMeter />

        {/* 3 · PROVIDER QUOTA */}
        <ProviderQuotaList compact={false} />
      </div>

      {/* 4 · QUEUE PROJECTION */}
      <QueueProjectionBar compact={false} />
    </div>
  );
};

export default UsageRoute;
