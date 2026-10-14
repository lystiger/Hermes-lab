import React from 'react';
import { AgentDetail } from '../../api/types';
import { UNKNOWN, isKnown } from '../../components/DataStates';

export const AgentContextMeter: React.FC<{ agent: AgentDetail }> = ({ agent }) => {
  const accentColor = agent.presentation?.accentColor || '#8C949F';
  // A segment is drawn only from a reported percentage. Unknown means an empty bar, never a guessed split.
  const segment = (pct: string) => (isKnown(pct) ? pct : '0%');

  return (
    <div className="flex-1 min-w-[260px]">
      <div className="text-[11px] tracking-wider text-[#5C646E] mb-2 font-mono-code">
        CONTEXT WINDOW
      </div>
      
      <div className="flex items-baseline gap-2">
        <span className="font-mono-code text-[20px] text-[#E6E9ED]">
          {agent.contextUsed || UNKNOWN}
        </span>
        <span className="font-mono-code text-[12px] text-[#5C646E]">
          / {agent.contextMax || UNKNOWN}
        </span>
      </div>

      {/* Multi-segmented visual bar */}
      <div className="mt-2 h-[7px] bg-[#14171C] relative flex overflow-hidden">
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

      <p className="mt-2.5 font-mono-code text-[11px] text-[#5C646E]">
        Hermes reports agent identity and status only. Token and context figures appear once they are exposed.
      </p>
      <div className="mt-2.5 flex flex-col gap-1 font-mono-code text-[11px]">
        <div className="flex justify-between text-[#8C949F]">
          <span>input</span>
          <span className="text-[#E6E9ED]">{agent.input || UNKNOWN}</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>output</span>
          <span className="text-[#E6E9ED]">{agent.output || UNKNOWN}</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>cached</span>
          <span className="text-[#E6E9ED]">{agent.cached || UNKNOWN}</span>
        </div>
        <div className="flex justify-between text-[#8C949F] border-t border-[#1F242B] pt-1 mt-0.5">
          <span>remaining</span>
          <span style={{ color: accentColor }}>{agent.remaining || UNKNOWN}</span>
        </div>
      </div>
    </div>
  );
};
