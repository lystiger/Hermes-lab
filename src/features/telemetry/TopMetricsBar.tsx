import React from 'react';
import { useConsoleStore } from '../../stores/useConsoleStore';

export const TopMetricsBar: React.FC = () => {
  const { tokensToday } = useConsoleStore();

  return (
    <div className="flex items-stretch border-b border-[#1F242B] bg-[#0C0E11] select-none overflow-x-auto">
      {/* Running */}
      <div className="flex-1 min-w-[120px] px-5 py-3 border-r border-[#1F242B]">
        <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">
          RUNNING
        </div>
        <div className="font-mono-code text-[19px] text-[#E6E9ED]">2</div>
      </div>

      {/* Queued */}
      <div className="flex-1 min-w-[120px] px-5 py-3 border-r border-[#1F242B]">
        <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">
          QUEUED
        </div>
        <div className="font-mono-code text-[19px] text-[#E6E9ED]">4</div>
      </div>

      {/* Blocked */}
      <div className="flex-1 min-w-[120px] px-5 py-3 border-r border-[#1F242B]">
        <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">
          BLOCKED
        </div>
        <div className="font-mono-code text-[19px] text-[#E3A008]">1</div>
      </div>

      {/* Failed 24H */}
      <div className="flex-1 min-w-[120px] px-5 py-3 border-r border-[#1F242B]">
        <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">
          FAILED 24H
        </div>
        <div className="font-mono-code text-[19px] text-[#8C949F]">0</div>
      </div>

      {/* Tokens Today */}
      <div className="flex-[1.2] min-w-[150px] px-5 py-3 border-r border-[#1F242B]">
        <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">
          TOKENS TODAY
        </div>
        <div className="font-mono-code text-[19px] text-[#E6E9ED]">{tokensToday}</div>
      </div>

      {/* Est. Spend */}
      <div className="flex-[1.2] min-w-[140px] px-5 py-3 border-r border-[#1F242B]">
        <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">
          EST. SPEND
        </div>
        <div className="font-mono-code text-[19px] text-[#E6E9ED]">$4.12</div>
      </div>

      {/* Sprint Budget Progress */}
      <div className="flex-[1.4] min-w-[180px] px-5 py-3 flex flex-col justify-center">
        <div className="text-[11px] tracking-wider text-[#5C646E] mb-1 font-mono-code">
          SPRINT BUDGET
        </div>
        <div className="flex items-center gap-2.5">
          <div className="flex-1 h-1.5 bg-[#1F242B] relative">
            <div className="absolute left-0 top-0 bottom-0 w-[58%] bg-[#E3A008]" />
            <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
          </div>
          <span className="font-mono-code text-[11px] text-[#E3A008]">58%</span>
        </div>
      </div>
    </div>
  );
};
