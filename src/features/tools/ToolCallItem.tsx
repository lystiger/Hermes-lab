import React from 'react';
import { TraceEvent } from '../../api/types';

export const ToolCallItem: React.FC<{ event: TraceEvent }> = ({ event }) => {
  const agColor = event.source.accentColor || '#8C949F';

  return (
    <div className="flex items-center gap-3.5 py-1.5 px-2.5 bg-[#101216] border-b border-[#14171C] font-mono-code text-[11px] hover:bg-[#12151A] transition-colors">
      <span className="w-20 text-[#5C646E]">{event.ts}</span>
      <span style={{ color: agColor }} className="w-16 font-semibold">
        {event.source.displayName}
      </span>
      <span className="w-24 text-[#8C949F]">{event.kind}</span>
      <span className="flex-1 min-w-0 text-[#B7BEC7] truncate font-sans">
        {event.detail}
      </span>
      <span className="w-16 text-right text-[#5C646E]">{event.dur || '—'}</span>
    </div>
  );
};
