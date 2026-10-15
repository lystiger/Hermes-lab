import React from 'react';
import { TraceEvent } from '../../api/types';
import { eventColor } from './executionFormat';

interface ExecutionTimelineProps {
  events: TraceEvent[];
  limit?: number;
}

/** Recent `execution.*` events, newest first. */
export const ExecutionTimeline: React.FC<ExecutionTimelineProps> = ({ events, limit = 50 }) => {
  const rows = events.slice(0, limit);

  if (rows.length === 0) {
    return (
      <div className="py-4 font-sans text-[11px] text-lys-faint">No execution events recorded yet.</div>
    );
  }

  return (
    <div className="flex flex-col font-sans text-[11px]">
      <div className="hidden md:flex items-center gap-4 px-1 py-1.5 border-b border-lys-subtle tracking-wider text-lys-faint">
        <span className="w-24 flex-shrink-0">TIME</span>
        <span className="w-24 flex-shrink-0">BACKEND</span>
        <span className="w-44 flex-shrink-0">EVENT</span>
        <span className="flex-1 min-w-0">DETAIL</span>
        <span className="w-28 flex-shrink-0">JOB · TASK</span>
      </div>
      {rows.map((e) => (
        <div
          key={e.id}
          data-testid="execution-event"
          className="flex flex-wrap md:flex-nowrap items-center gap-x-4 gap-y-0.5 px-1 py-1.5 border-b border-lys-subtle hover:bg-lys-surface-1"
        >
          <span className="w-24 flex-shrink-0 text-lys-faint">{e.ts}</span>
          <span className="w-24 flex-shrink-0 font-semibold" style={{ color: e.source.accentColor || 'var(--lys-text-muted)' }}>
            {e.source.id}
          </span>
          <span className="w-full md:w-44 flex-shrink-0 font-medium break-all" style={{ color: eventColor(e.kind) }}>
            {e.kind.replace('execution.', '')}
          </span>
          <span className="flex-1 min-w-0 break-words font-sans text-lys-secondary">{e.detail}</span>
          <span className="flex-shrink-0 max-w-full font-mono-code text-[11px] text-lys-muted break-all">
            {e.jobId || '—'}{e.taskId ? ` · ${e.taskId}` : ''}
          </span>
        </div>
      ))}
    </div>
  );
};
