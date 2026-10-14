import React from 'react';
import { AgentDetail } from '../../api/types';

export const AgentActivityList: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  const getOpColor = (op: string) => {
    switch (op) {
      case 'WRITE': return 'var(--lys-status-warning)';
      case 'RUN': return 'var(--lys-status-success)';
      case 'NOTE': return 'var(--lys-status-danger)';
      case 'STAGE': return 'var(--lys-agent-codex)';
      default: return 'var(--lys-text-muted)';
    }
  };

  return (
    <div className="flex-1 min-w-[280px]">
      <div className="text-[11px] tracking-wider text-lys-faint mb-2 font-mono-code">
        CURRENT ACTIVITY
      </div>
      {agent.activity.length === 0 && (
        <div className="font-mono-code text-[11px] text-lys-faint">
          Activity is not loaded in this build. Live events for this agent appear in Events.
        </div>
      )}
      <div className="flex flex-col gap-1">
        {agent.activity.map((act, idx) => (
          <div
            key={idx}
            className="flex items-center gap-3.5 px-2.5 py-1.5 bg-lys-surface-1 font-mono-code text-[11px] border-l border-transparent hover:border-lys-strong"
          >
            <span
              style={{ color: getOpColor(act.op) }}
              className="w-14 flex-shrink-0 tracking-wider font-semibold"
            >
              {act.op}
            </span>
            <span className="flex-1 min-w-0 text-lys-primary truncate">
              {act.path}
            </span>
            <span className="w-18 flex-shrink-0 text-right text-lys-faint">
              {act.meta}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
