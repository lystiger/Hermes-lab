import React from 'react';
import { useConsoleStore } from '../../stores/useConsoleStore';

export const AgentChatterFeed: React.FC<{ limit?: number }> = ({ limit = 10 }) => {
  const { allEvents } = useConsoleStore();

  const chatterEvents = allEvents.filter(e => 
    e.kind === 'agent.note' || e.kind === 'phase.change' || e.kind === 'quota.warn' || e.kind === 'job.start' || e.kind === 'agent.start'
  ).slice(0, limit);

  return (
    <div className="flex flex-col select-none">
      <div className="flex items-center justify-between font-mono-code text-[11px] text-lys-faint mb-2.5">
        <span className="tracking-wider">AGENT CHATTER &amp; HANDOFFS</span>
        <span className="flex items-center gap-1.5 text-lys-success">
          <span className="w-1 h-1 rounded-full bg-lys-success" />
          live
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {chatterEvents.map((evt) => {
          const color = evt.source.accentColor || 'var(--lys-accent-gold)';

          return (
            <div
              key={evt.id}
              className="p-2.5 bg-lys-surface-1 border border-lys-subtle hover:border-lys-default transition-colors"
            >
              <div className="flex items-center justify-between font-mono-code text-[11px] mb-1">
                <span style={{ color }} className="font-semibold">
                  [{evt.source.displayName}]
                </span>
                <span className="text-lys-faint">{evt.ts}</span>
              </div>
              <p className="text-[12px] text-lys-primary leading-relaxed font-mono-code">
                {evt.detail}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
