import React from 'react';
import { AgentDetail } from '../../api/types';

export const AgentRunsTable: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  const accentColor = agent.presentation?.accentColor || 'var(--lys-text-muted)';

  const getResultColor = (res: string) => {
    switch (res) {
      case 'PASSED': return 'var(--lys-status-success)';
      case 'RUNNING': return 'var(--lys-status-success)';
      case 'FAILED': return 'var(--lys-status-danger)';
      case 'RETRIED': return 'var(--lys-status-warning)';
      case 'RATE LIMITED': return 'var(--lys-status-danger)';
      default: return 'var(--lys-text-muted)';
    }
  };

  return (
    <div className="p-5 pb-8">
      <div className="font-mono-code text-[11px] tracking-wider text-lys-faint mb-2.5">
        RECENT RUNS
      </div>

      <div className="flex flex-col">
        {agent.runs.map((r, idx) => (
          <div
            key={idx}
            className="flex items-center gap-4 py-2 border-b border-lys-subtle font-mono-code text-[11px] hover:bg-lys-surface-1 px-1 transition-colors"
          >
            <span className="w-12 text-lys-muted">{r.id}</span>
            <span
              style={{ color: accentColor }}
              className="w-16 tracking-wider font-semibold"
            >
              {r.phase}
            </span>
            <span className="flex-1 min-w-0 text-[12px] text-lys-primary font-sans truncate">
              {r.task}
            </span>
            <span className="w-18 text-right text-lys-muted">{r.tokens}</span>
            <span className="w-16 text-right text-lys-muted">{r.dur}</span>
            <span
              style={{ color: getResultColor(r.result) }}
              className="w-24 text-right tracking-wider font-medium"
            >
              {r.result}
            </span>
          </div>
        ))}
        {agent.runs.length === 0 && (
          <div className="py-4 text-center font-mono-code text-[11px] text-lys-faint">
            Run history is not loaded. No runs endpoint is wired for agents yet, so this is unknown rather than empty.
          </div>
        )}
      </div>
    </div>
  );
};
