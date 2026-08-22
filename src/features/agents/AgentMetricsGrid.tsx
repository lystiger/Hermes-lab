import React from 'react';
import { AgentData } from '../../api/types';

export const AgentMetricsGrid: React.FC<{ agent: AgentData }> = ({ agent }) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 border-b border-[#1F242B]">
      {agent.metrics.map((m, idx) => (
        <div
          key={idx}
          className="p-4 border-r border-[#1F242B] last:border-r-0 bg-[#0C0E11]"
        >
          <div className="text-[11px] tracking-wider text-[#5C646E]">
            {m.label}
          </div>
          <div
            style={{ color: m.color || '#E6E9ED' }}
            className="mt-1 font-mono-code text-[17px] font-medium"
          >
            {m.value}
          </div>
          {m.sub && (
            <div className="mt-0.5 font-mono-code text-[11px] text-[#5C646E]">
              {m.sub}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};
