import React from 'react';
import { useConsoleStore } from '../../stores/useConsoleStore';

export const QueueProjectionBar: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { projections } = useConsoleStore();

  if (compact) {
    return (
      <div className="p-3.5 border-b border-[#1F242B]">
        <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3">
          QUEUE PROJECTION
        </div>
        <div className="flex justify-between font-mono-code text-[11px] text-[#8C949F] mb-2.5">
          <span>remaining budget</span>
          <span className="text-[#E6E9ED]">91k</span>
        </div>

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

        <div className="mt-3 pt-2.5 border-t border-[#1F242B] flex justify-between font-mono-code text-[11px]">
          <span className="text-[#5C646E]">projected remainder</span>
          <span className="text-[#E3A008]">~12k</span>
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
          current estimated remaining budget <span className="text-[#E6E9ED]">91k</span>
        </span>
      </div>

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

      <div className="mt-4 max-w-4xl flex justify-between pt-3 border-t border-[#1F242B] font-mono-code text-[11px]">
        <span className="text-[#5C646E]">projected remainder after queue</span>
        <span className="text-[#E3A008]">
          ~12k · ⚠ another large Codex verification may exceed budget
        </span>
      </div>
    </div>
  );
};
