import React from 'react';
import { TraceEvent } from '../../api/types';

export const ToolCallItem: React.FC<{ event: TraceEvent }> = ({ event }) => {
  const agColor = event.source.accentColor || 'var(--lys-text-muted)';

  return (
    <div className="flex items-center gap-3.5 py-1.5 px-2.5 bg-lys-surface-1 border-b border-lys-subtle font-sans text-[11px] hover:bg-lys-surface-1 transition-colors">
      <span className="w-20 text-lys-faint">{event.ts}</span>
      <span style={{ color: agColor }} className="w-16 font-semibold">
        {event.source.displayName}
      </span>
      <span className="w-24 text-lys-muted">{event.kind}</span>
      <span className="flex-1 min-w-0 text-lys-secondary truncate font-sans">
        {event.detail}
      </span>
      <span className="w-16 text-right text-lys-faint">{event.dur || '—'}</span>
    </div>
  );
};
