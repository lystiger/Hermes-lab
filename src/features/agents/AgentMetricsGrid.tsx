import React from 'react';
import { AgentDetail } from '../../api/types';

export const AgentMetricsGrid: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 border-b border-lys-subtle">
      {agent.metrics.map((m, idx) => (
        <div
          key={idx}
          className="p-4 border-r border-lys-subtle last:border-r-0 bg-lys-surface-0"
        >
          <div className="text-[11px] tracking-wider text-lys-faint font-mono-code">
            {m.label}
          </div>
          <div
            style={{ color: m.color || 'var(--lys-text-primary)' }}
            className="mt-1 font-mono-code text-[17px] font-medium"
          >
            {m.value}
          </div>
          {m.sub && (
            <div className="mt-0.5 font-mono-code text-[11px] text-lys-faint">
              {m.sub}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};
