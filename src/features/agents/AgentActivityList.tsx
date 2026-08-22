import React from 'react';
import { AgentDetail } from '../../api/types';

export const AgentActivityList: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  const getOpColor = (op: string) => {
    switch (op) {
      case 'WRITE': return '#E3A008';
      case 'RUN': return '#3FB950';
      case 'NOTE': return '#F2555A';
      case 'STAGE': return '#4EC9A0';
      default: return '#8C949F';
    }
  };

  return (
    <div className="flex-1 min-w-[280px]">
      <div className="text-[11px] tracking-wider text-[#5C646E] mb-2 font-mono-code">
        CURRENT ACTIVITY
      </div>
      <div className="flex flex-col gap-1">
        {agent.activity.map((act, idx) => (
          <div
            key={idx}
            className="flex items-center gap-3.5 px-2.5 py-1.5 bg-[#101216] font-mono-code text-[11px] border-l border-transparent hover:border-[#3A4048]"
          >
            <span
              style={{ color: getOpColor(act.op) }}
              className="w-14 flex-shrink-0 tracking-wider font-semibold"
            >
              {act.op}
            </span>
            <span className="flex-1 min-w-0 text-[#D7DCE2] truncate">
              {act.path}
            </span>
            <span className="w-18 flex-shrink-0 text-right text-[#5C646E]">
              {act.meta}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
