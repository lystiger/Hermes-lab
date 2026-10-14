import React, { useState } from 'react';
import { AgentDetail } from '../../api/types';
import { EmptyState, isKnown } from '../../components/DataStates';

export const AgentAllowanceCard: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  const [showTooltip, setShowTooltip] = useState(false);
  const accentColor = agent.presentation?.accentColor || '#8C949F';

  return (
    <div className="flex-1 min-w-[240px]">
      <div className="text-[11px] tracking-wider text-[#5C646E] mb-2 font-mono-code">
        ALLOWANCE
      </div>

      {agent.allowance.length === 0 && (
        <EmptyState>Provider quota is not reported by Hermes for this agent.</EmptyState>
      )}

      <div className="flex flex-col gap-2.5">
        {agent.allowance.map((al, idx) => {
          const isEst = al.tag === 'EST';
          const isExact = al.tag === 'EXACT';
          const tagColor = isExact ? '#3FB950' : isEst ? '#E3A008' : '#5C646E';

          return (
            <div key={idx}>
              <div className="flex items-center justify-between font-mono-code text-[11px]">
                <span className="text-[#8C949F]">{al.label}</span>
                <span className="flex items-center gap-1.5 text-[#E6E9ED]">
                  {al.value}
                  <span
                    style={{ color: tagColor, borderColor: `${tagColor}44` }}
                    className="text-[10px] tracking-wider px-1 border"
                  >
                    {al.tag}
                  </span>
                </span>
              </div>
              <div className="mt-1 h-[6px] bg-[#14171C] relative">
                {isKnown(al.pct) && (
                  <div
                    style={{
                      width: al.pct,
                      backgroundColor: al.tag === 'N/A' ? '#3A4048' : accentColor,
                      opacity: isEst ? 0.5 : 0.9
                    }}
                    className="absolute left-0 top-0 bottom-0"
                  />
                )}
                <div className="absolute inset-0 bg-striped-pattern pointer-events-none" />
              </div>
            </div>
          );
        })}
      </div>

      <div
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className="relative mt-3 pt-2.5 border-t border-[#1F242B] flex flex-col gap-1.5 font-mono-code text-[11px] cursor-help"
      >
        <div className="flex justify-between text-[#8C949F]">
          <span>est. capacity</span>
          <span className="text-[#E6E9ED]">{agent.capacity}</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>est. reset</span>
          <span className="text-[#E3A008]">{agent.reset}</span>
        </div>

        {showTooltip && (
          <div className="absolute right-0 top-full mt-2 z-30 w-64 p-2.5 bg-[#12151A] border border-[#2A3038] shadow-2xl font-mono-code text-[11px] text-[#B7BEC7] leading-relaxed">
            {agent.resetNote}
          </div>
        )}
      </div>
    </div>
  );
};
