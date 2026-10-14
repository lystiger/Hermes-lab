import React from 'react';
import { useTelemetry } from '../../api/hooks';
import { UnknownValue, Freshness, StaleNotice } from '../../components/DataStates';

const NO_TOKEN_TOTALS = 'Hermes does not report sprint token totals in this build';
const NO_SPEND = 'Hermes does not report cost or spend';
const NO_BUDGET = 'Hermes does not expose a sprint budget, so no percentage can be computed';

interface MetricProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

const Metric: React.FC<MetricProps> = ({ label, children, className = '' }) => (
  <div className={`px-5 py-3 border-r border-[#1F242B] ${className}`}>
    <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">{label}</div>
    {children}
  </div>
);

export const TopMetricsBar: React.FC = () => {
  const { telemetry, loading, error, updatedAt, refetch } = useTelemetry();

  if (error && !telemetry) {
    return (
      <div className="px-5 py-3 border-b border-[#1F242B] bg-[#0C0E11] font-mono-code text-[12px] text-[#F2555A] flex items-center gap-3">
        <span>Metrics unavailable: {error.message}</span>
        <button type="button" onClick={refetch} className="underline cursor-pointer">retry</button>
      </div>
    );
  }

  // A count is shown only after a real job list has loaded; before that it is unknown, never zero.
  const count = (value: number | undefined) =>
    telemetry ? <>{value ?? 0}</> : <UnknownValue reason={loading ? 'Loading from Hermes' : 'Not loaded'} />;

  const failed = telemetry?.failed24hCount;

  return (
    <div className="flex flex-col border-b border-[#1F242B] bg-[#0C0E11] select-none">
      <div className="flex items-stretch overflow-x-auto">
        <Metric label="RUNNING" className="flex-1 min-w-[120px]">
          <div className="font-mono-code text-[19px] text-[#E6E9ED]">{count(telemetry?.runningJobsCount)}</div>
        </Metric>

        <Metric label="QUEUED" className="flex-1 min-w-[120px]">
          <div className="font-mono-code text-[19px] text-[#E6E9ED]">{count(telemetry?.queuedJobsCount)}</div>
        </Metric>

        <Metric label="BLOCKED" className="flex-1 min-w-[120px]">
          <div className="font-mono-code text-[19px] text-[#E3A008]">{count(telemetry?.blockedJobsCount)}</div>
        </Metric>

        <Metric label="FAILED 24H" className="flex-1 min-w-[120px]">
          <div className="font-mono-code text-[19px] text-[#8C949F]">
            {failed === null || failed === undefined ? (
              <UnknownValue reason="A failed job has no completion time, so the 24h window cannot be applied" />
            ) : (
              failed
            )}
          </div>
        </Metric>

        <Metric label="TOKENS TODAY" className="flex-[1.2] min-w-[150px]">
          <div className="font-mono-code text-[19px] text-[#E6E9ED]">
            <UnknownValue reason={NO_TOKEN_TOTALS} />
          </div>
        </Metric>

        <Metric label="EST. SPEND" className="flex-[1.2] min-w-[140px]">
          <div className="font-mono-code text-[19px] text-[#E6E9ED]">
            <UnknownValue reason={NO_SPEND} />
          </div>
        </Metric>

        <div className="flex-[1.4] min-w-[180px] px-5 py-3 flex flex-col justify-center">
          <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">SPRINT BUDGET</div>
          <div className="flex items-center gap-2.5 font-mono-code text-[11px] text-[#5C646E]">
            <UnknownValue reason={NO_BUDGET} className="text-[#8C949F]" />
            <span>no budget exposed</span>
          </div>
        </div>
      </div>

      {error && <div className="px-5 pt-2"><StaleNotice label="Metrics" error={error} onRetry={refetch} /></div>}
      <div className="px-5 pb-2 flex flex-wrap items-center gap-x-4 font-mono-code text-[11px] text-[#5C646E]">
        <span>
          counts from the latest {telemetry ? telemetry.sampleSize : '—'} jobs (GET /jobs)
        </span>
        <Freshness at={updatedAt} />
      </div>
    </div>
  );
};
