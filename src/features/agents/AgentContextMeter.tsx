import React from 'react';
import { AgentData } from '../../api/types';

export const AgentContextMeter: React.FC<{ agent: AgentData }> = ({ agent }) => {
  return (
    <div className="flex-1 min-w-[260px]">
      <div className="text-[11px] tracking-wider text-[#5C646E] mb-2 font-mono-code">
        CONTEXT WINDOW
      </div>
      
      <div className="flex items-baseline gap-2">
        <span className="font-mono-code text-[20px] text-[#E6E9ED]">
          {agent.ctxUsed}
        </span>
        <span className="font-mono-code text-[12px] text-[#5C646E]">
          / {agent.ctxMax}
        </span>
      </div>

      {/* Multi-segmented visual bar */}
      <div className="mt-2 h-[7px] bg-[#14171C] relative flex overflow-hidden">
        <div
          style={{ width: agent.inPct, backgroundColor: agent.color }}
          className="opacity-95"
          title={`Input: ${agent.input} (${agent.inPct})`}
        />
        <div
          style={{ width: agent.outPct, backgroundColor: agent.color }}
          className="opacity-55"
          title={`Output: ${agent.output} (${agent.outPct})`}
        />
        <div
          style={{ width: agent.cachePct, backgroundColor: agent.color }}
          className="opacity-25"
          title={`Cached: ${agent.cached} (${agent.cachePct})`}
        />
      </div>

      <div className="mt-2.5 flex flex-col gap-1 font-mono-code text-[11px]">
        <div className="flex justify-between text-[#8C949F]">
          <span>input</span>
          <span className="text-[#E6E9ED]">{agent.input}</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>output</span>
          <span className="text-[#E6E9ED]">{agent.output}</span>
        </div>
        <div className="flex justify-between text-[#8C949F]">
          <span>cached</span>
          <span className="text-[#E6E9ED]">{agent.cached}</span>
        </div>
        <div className="flex justify-between text-[#8C949F] border-t border-[#1F242B] pt-1 mt-0.5">
          <span>remaining</span>
          <span style={{ color: agent.color }}>{agent.remaining}</span>
        </div>
      </div>
    </div>
  );
};
