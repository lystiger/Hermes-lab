import React, { useMemo, useRef, useState } from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { TraceEvent } from '../api/types';
import { EVENT_CATEGORIES, EventCategory, SEVERITY_COLOR, eventCategory, eventKindColor, eventSeverity } from '../features/events/eventKinds';
import { EmptyState } from '../components/DataStates';
import { FilterPills } from '../components/FilterPills';
import { CopyId } from '../components/CopyId';
import { useArrowNavigation, useEscape } from '../components/keyboard';
import { formatMillis, UNKNOWN_TIME } from '../features/time/format';

/** Time of an event in local time, from its epoch seconds when the bus gives them. */
export function eventTime(e: TraceEvent): string {
  return e.rawTs > 0 ? formatMillis(e.rawTs * 1000) : e.ts || UNKNOWN_TIME;
}

export const EventsRoute: React.FC = () => {
  const { allEvents, setActiveModalJobId, connectionStatus } = useConsoleStore();
  const [category, setCategory] = useState<'ALL' | EventCategory>('ALL');
  const [source, setSource] = useState('ALL');
  const [expanded, setExpanded] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  useArrowNavigation(listRef);
  useEscape(() => setExpanded(null), expanded !== null);

  const counts = useMemo(() => {
    const byCategory = new Map<string, number>();
    const bySource = new Map<string, number>();
    for (const e of allEvents) {
      const c = eventCategory(e.kind);
      byCategory.set(c, (byCategory.get(c) ?? 0) + 1);
      bySource.set(e.source.displayName, (bySource.get(e.source.displayName) ?? 0) + 1);
    }
    return { byCategory, bySource };
  }, [allEvents]);

  const visible = allEvents.filter(
    (e) =>
      (category === 'ALL' || eventCategory(e.kind) === category) &&
      (source === 'ALL' || e.source.displayName === source)
  );

  const categoryOptions = [
    { id: 'ALL', label: 'All', count: allEvents.length },
    ...EVENT_CATEGORIES.filter((c) => (counts.byCategory.get(c.id) ?? 0) > 0).map((c) => ({
      id: c.id,
      label: c.label,
      count: counts.byCategory.get(c.id) ?? 0,
      tone: c.tone
    }))
  ];
  const sourceOptions = [
    { id: 'ALL', label: 'All sources', count: allEvents.length },
    ...Array.from(counts.bySource.entries()).map(([name, count]) => ({ id: name, label: name, count }))
  ];

  return (
    <div className="flex flex-col select-none bg-lys-base min-h-0">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-lys-subtle bg-lys-surface-0">
        <div className="flex flex-col gap-2 min-w-0">
          <FilterPills label="Filter events by category" options={categoryOptions} value={category} onChange={(id) => setCategory(id as 'ALL' | EventCategory)} />
          <FilterPills label="Filter events by source" options={sourceOptions} value={source} onChange={setSource} />
        </div>
        <div className="flex items-center gap-3 font-mono-code text-[11px] text-lys-faint">
          <span>{visible.length} of {allEvents.length} shown</span>
          {connectionStatus === 'CONNECTED' ? (
            <span className="text-lys-success">streaming</span>
          ) : (
            <span className="text-lys-warning">not streaming · {connectionStatus.toLowerCase()}</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4 px-5 py-2 border-b border-lys-subtle font-mono-code text-[10px] tracking-wider text-lys-faint bg-lys-surface-0">
        <span className="w-28 flex-shrink-0">TIME (LOCAL)</span>
        <span className="w-6 flex-shrink-0">SEV</span>
        <span className="w-24 flex-shrink-0">SOURCE</span>
        <span className="w-36 flex-shrink-0">KIND</span>
        <span className="flex-1 min-w-[160px]">DETAIL</span>
        <span className="w-28 flex-shrink-0 text-right">JOB</span>
      </div>

      <div ref={listRef} role="log" aria-live="polite" aria-relevant="additions text" aria-label="Events" className="flex flex-col">
        {visible.length === 0 && (
          <EmptyState>{allEvents.length === 0 ? 'No events received yet.' : 'No events match these filters.'}</EmptyState>
        )}
        {visible.map((e) => {
          const severity = eventSeverity(e.kind);
          const isOpen = expanded === e.id;
          return (
            <div key={e.id} className="border-b border-lys-subtle">
              <button
                type="button"
                data-nav-item
                aria-expanded={isOpen}
                onClick={() => setExpanded(isOpen ? null : e.id)}
                className="w-full flex items-center gap-4 px-5 py-1.5 font-mono-code text-[11.5px] text-left hover:bg-lys-surface-1 cursor-pointer"
                style={{ backgroundColor: severity === 'error' ? 'color-mix(in srgb, var(--lys-status-danger) 7%, transparent)' : severity === 'warn' ? 'color-mix(in srgb, var(--lys-status-warning) 5%, transparent)' : 'transparent' }}
              >
                <span className="w-28 flex-shrink-0 text-lys-faint">{eventTime(e)}</span>
                <span className="w-6 flex-shrink-0" aria-label={`severity ${severity}`} title={severity}>
                  <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: SEVERITY_COLOR[severity] }} />
                </span>
                <span className="w-24 flex-shrink-0 font-semibold truncate" style={{ color: e.source.accentColor || 'var(--lys-text-muted)' }}>
                  {e.source.displayName}
                </span>
                <span className="w-36 flex-shrink-0 font-medium truncate" style={{ color: eventKindColor(e.kind) }}>
                  {e.kind}
                </span>
                <span className="flex-1 min-w-[160px] text-lys-secondary truncate font-sans">{e.detail}</span>
                <span className="w-28 flex-shrink-0 text-right text-lys-gold truncate">{e.jobId || UNKNOWN_TIME}</span>
              </button>

              {isOpen && (
                <div className="px-5 pb-3 pt-1 bg-lys-surface-0 flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-4 font-mono-code text-[11px] text-lys-muted">
                    <span>id <CopyId value={e.id} /></span>
                    {e.jobId && <span>job <button type="button" onClick={() => setActiveModalJobId(e.jobId!)} className="text-lys-gold underline cursor-pointer">{e.jobId}</button></span>}
                    {e.runId && <span>run <CopyId value={e.runId} /></span>}
                    {e.taskId && <span>task <CopyId value={e.taskId} /></span>}
                    {e.actorId && <span>actor <CopyId value={e.actorId} /></span>}
                  </div>
                  <pre className="font-mono-code text-[11px] text-lys-secondary bg-lys-base border border-lys-subtle p-3 overflow-x-auto">
                    {JSON.stringify(e, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="px-5 py-2 flex flex-wrap items-center justify-between gap-2 font-mono-code text-[10px] text-lys-faint">
        <span>↑ ↓ move · Enter expands · Esc collapses</span>
        <span>live bus buffer, newest first · {allEvents.length} held</span>
      </div>
    </div>
  );
};

export default EventsRoute;
