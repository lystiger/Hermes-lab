import React from 'react';
import { useTelemetry } from '../../api/hooks';
import { EmptyState, ErrorState, LoadingState, UnknownValue } from '../../components/DataStates';

const NO_PROJECTION = 'Hermes has no projection source for queued work';

/** Queue projection. Rows come only from a real projection source; none exists yet, so none are drawn. */
export const QueueProjectionBar: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { projections, loading, error, refetch } = useTelemetry();

  if (loading && projections.length === 0 && !error) {
    return <LoadingState label="Loading projection…" />;
  }

  if (error && projections.length === 0) {
    return <ErrorState label="Queue projection" error={error} onRetry={refetch} />;
  }

  if (compact) {
    return (
      <div className="p-3.5 border-b border-[#1F242B]">
        <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3">
          QUEUE PROJECTION
        </div>
        <div className="flex justify-between font-mono-code text-[11px] text-[#8C949F] mb-2.5">
          <span>remaining budget</span>
          <UnknownValue reason={NO_PROJECTION} className="text-[#E6E9ED]" />
        </div>

        {projections.length === 0 ? (
          <div className="font-mono-code text-[11px] text-[#5C646E]">No projected rows.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {projections.map((p) => (
              <div key={p.id} className="flex items-center gap-2 font-mono-code text-[11px]">
                <span className="w-8 text-[#5C646E]">{p.id}</span>
                <div className="flex-1 h-2 bg-[#14171C] relative">
                  <div
                    style={{ width: p.w, backgroundColor: p.color }}
                    className="absolute left-0 top-0 bottom-0 opacity-80"
                  />
                </div>
                <span className="w-11 text-right text-[#8C949F]">{p.est}</span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-3 pt-2.5 border-t border-[#1F242B] flex justify-between font-mono-code text-[11px]">
          <span className="text-[#5C646E]">projected remainder</span>
          <UnknownValue reason={NO_PROJECTION} className="text-[#E3A008]" />
        </div>
      </div>
    );
  }

  // Full view for /usage route
  return (
    <div className="p-5">
      <div className="flex items-baseline gap-3.5 mb-3.5 font-mono-code text-[11px]">
        <span className="tracking-wider text-[#5C646E]">QUEUE PROJECTION</span>
        <span className="text-[#8C949F]">
          remaining budget <UnknownValue reason={NO_PROJECTION} className="text-[#E6E9ED]" />
        </span>
      </div>

      {projections.length === 0 ? (
        <EmptyState>{NO_PROJECTION}. No projected rows are shown.</EmptyState>
      ) : (
        <div className="flex flex-col gap-2.5 max-w-4xl">
          {projections.map((p) => {
            const confColor = p.conf === 'low' ? '#E3A008' : p.conf === 'high' ? '#3FB950' : '#8C949F';

            return (
              <div key={p.id} className="flex items-center gap-3.5 font-mono-code text-[11px]">
                <span className="w-10 text-[#8C949F]">{p.id}</span>
                <span className="w-56 text-[12px] text-[#D7DCE2] truncate font-sans">
                  {p.task}
                </span>
                <div className="flex-1 h-3.5 bg-[#101216] relative overflow-hidden">
                  <div
                    style={{ width: p.w, backgroundColor: p.color }}
                    className="absolute left-0 top-0 bottom-0 opacity-80"
                  />
                  <div
                    style={{ width: p.wLow }}
                    className="absolute left-0 top-0 bottom-0 border-r border-dashed border-[rgba(230,233,237,0.35)]"
                  />
                </div>
                <span className="w-24 text-right text-[#8C949F]">{p.est}</span>
                <span style={{ color: confColor }} className="w-20 text-right uppercase">
                  {p.conf}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
