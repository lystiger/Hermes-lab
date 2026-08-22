import React from 'react';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { AGENT_COLOR_MAP } from '../../api/mockData';

export const AgentChatterFeed: React.FC<{ limit?: number }> = ({ limit = 10 }) => {
  const { allEvents } = useConsoleStore();

  const chatterEvents = allEvents.filter(e => 
    e.kind === 'agent.note' || e.kind === 'phase.change' || e.kind === 'quota.warn' || e.kind === 'job.start' || e.kind === 'agent.start'
  ).slice(0, limit);

  return (
    <div className="flex flex-col select-none">
      <div className="flex items-center justify-between font-mono-code text-[11px] text-[#5C646E] mb-2.5">
        <span className="tracking-wider">AGENT CHATTER &amp; HANDOFFS</span>
        <span className="flex items-center gap-1.5 text-[#3FB950]">
          <span className="w-1 h-1 rounded-full bg-[#3FB950] animate-pulse" />
          live
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {chatterEvents.map((evt) => {
          const color = AGENT_COLOR_MAP[evt.agent] || '#CBA35C';

          return (
            <div
              key={evt.id}
              className="p-2.5 bg-[#101216] border border-[#1A1E24] hover:border-[#2A3038] transition-colors"
            >
              <div className="flex items-center justify-between font-mono-code text-[11px] mb-1">
                <span style={{ color }} className="font-semibold">
                  [{evt.agent}]
                </span>
                <span className="text-[#5C646E]">{evt.ts}</span>
              </div>
              <p className="text-[12px] text-[#D7DCE2] leading-relaxed font-mono-code">
                {evt.detail}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
