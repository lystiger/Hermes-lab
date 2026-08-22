import React from 'react';
import { AgentData } from '../../api/types';
import { AGENT_COLOR_MAP } from '../../api/mockData';

export const AgentRunsTable: React.FC<{ agent: AgentData }> = ({ agent }) => {
  const getResultColor = (res: string) => {
    switch (res) {
      case 'PASSED': return '#3FB950';
      case 'RUNNING': return '#3FB950';
      case 'FAILED': return '#F2555A';
      case 'RETRIED': return '#E3A008';
      case 'RATE LIMITED': return '#F2555A';
      default: return '#8C949F';
    }
  };

  return (
    <div className="p-5 pb-8">
      <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-2.5">
        RECENT RUNS
      </div>

      <div className="flex flex-col">
        {agent.runs.map((r, idx) => (
          <div
            key={idx}
            className="flex items-center gap-4 py-2 border-b border-[#14171C] font-mono-code text-[11px] hover:bg-[#12151A] px-1 transition-colors"
          >
            <span className="w-12 text-[#8C949F]">{r.id}</span>
            <span
              style={{ color: agent.color }}
              className="w-16 tracking-wider font-semibold"
            >
              {r.phase}
            </span>
            <span className="flex-1 min-w-0 text-[12px] text-[#D7DCE2] font-sans truncate">
              {r.task}
            </span>
            <span className="w-18 text-right text-[#8C949F]">{r.tokens}</span>
            <span className="w-16 text-right text-[#8C949F]">{r.dur}</span>
            <span
              style={{ color: getResultColor(r.result) }}
              className="w-24 text-right tracking-wider font-medium"
            >
              {r.result}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
