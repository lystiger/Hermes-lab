import React from 'react';
import { AgentDetail } from '../../api/types';
import { UNKNOWN, isKnown } from '../../components/DataStates';

export const AgentContextMeter: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  const accentColor = agent.presentation?.accentColor || 'var(--lys-text-muted)';
  // A segment is drawn only from a reported percentage. Unknown means an empty bar, never a guessed split.
  const segment = (pct: string) => (isKnown(pct) ? pct : '0%');

  return (
    <div className="flex-1 min-w-[260px]">
      <div className="text-[11px] tracking-wider text-lys-faint mb-2 font-sans">
        CONTEXT WINDOW
      </div>
      
      <div className="flex items-baseline gap-2">
        <span className="font-sans text-[20px] text-lys-primary">
          {agent.contextUsed || UNKNOWN}
        </span>
        <span className="font-sans text-[12px] text-lys-faint">
          / {agent.contextMax || UNKNOWN}
        </span>
      </div>

      {/* Multi-segmented visual bar */}
      <div className="mt-2 h-[7px] bg-lys-surface-1 relative flex overflow-hidden">
        <div
          style={{ width: segment(agent.inPct), backgroundColor: accentColor }}
          className="opacity-95"
          title={`Input: ${agent.input} (${agent.inPct})`}
        />
        <div
          style={{ width: segment(agent.outPct), backgroundColor: accentColor }}
          className="opacity-55"
          title={`Output: ${agent.output} (${agent.outPct})`}
        />
        <div
          style={{ width: segment(agent.cachePct), backgroundColor: accentColor }}
          className="opacity-25"
          title={`Cached: ${agent.cached} (${agent.cachePct})`}
        />
      </div>

      <p className="mt-2.5 font-sans text-[11px] text-lys-faint">
        Hermes reports agent identity and status only. Token and context figures appear once they are exposed.
      </p>
      <div className="mt-2.5 flex flex-col gap-1 font-sans text-[11px]">
        <div className="flex justify-between text-lys-muted">
          <span>input</span>
          <span className="text-lys-primary">{agent.input || UNKNOWN}</span>
        </div>
        <div className="flex justify-between text-lys-muted">
          <span>output</span>
          <span className="text-lys-primary">{agent.output || UNKNOWN}</span>
        </div>
        <div className="flex justify-between text-lys-muted">
          <span>cached</span>
          <span className="text-lys-primary">{agent.cached || UNKNOWN}</span>
        </div>
        <div className="flex justify-between text-lys-muted border-t border-lys-subtle pt-1 mt-0.5">
          <span>remaining</span>
          <span style={{ color: accentColor }}>{agent.remaining || UNKNOWN}</span>
        </div>
      </div>
    </div>
  );
};
