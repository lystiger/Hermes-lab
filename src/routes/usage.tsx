import React from 'react';
import { TokenBudgetMeter } from '../features/telemetry/TokenBudgetMeter';
import { ProviderQuotaList } from '../features/telemetry/ProviderQuotaList';
import { QueueProjectionBar } from '../features/jobs/QueueProjectionBar';
import { useConsoleStore } from '../stores/useConsoleStore';

export const UsageRoute: React.FC = () => {
  const { agents } = useConsoleStore();

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
            {agents.map((a) => (
              <div key={a.id}>
                <div className="flex justify-between items-baseline font-mono-code text-[11px]">
                  <span style={{ color: a.color }}>{a.name} · {a.model}</span>
                  <span className="text-[#8C949F]">{a.ctxUsed} / {a.ctxMax}</span>
                </div>
                <div className="mt-1.5 h-2 bg-[#14171C] relative">
                  <div
                    style={{ width: a.ctxPct, backgroundColor: a.color }}
                    className="absolute left-0 top-0 bottom-0"
                  />
                  <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
                </div>
                <div className="mt-1 flex justify-between font-mono-code text-[11px] text-[#5C646E]">
                  <span>{a.ctxPct} used</span>
                  <span>{a.remaining} free</span>
                </div>
              </div>
            ))}
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
