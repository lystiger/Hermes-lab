import React, { useMemo, useRef, useState } from 'react';
import { useConsoleStore } from '../stores/useConsoleStore';
import { TraceEvent } from '../api/types';
import { EVENT_CATEGORIES, EventCategory, SEVERITY_COLOR, eventCategory, eventKindColor, eventSeverity } from '../features/events/eventKinds';
import { EmptyState, UNKNOWN_TIME_LABEL as UNKNOWN_TIME } from '../components/DataStates';
import { Card } from '../components/Card';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { HERMES_ART } from '../theme/agentArt';
import { FilterPills } from '../components/FilterPills';
import { CopyId } from '../components/CopyId';
import { useArrowNavigation, useEscape } from '../components/keyboard';
import { formatMillis } from '../features/time/format';

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

  const failures = counts.byCategory.get('failures') ?? 0;
  const warnings = counts.byCategory.get('warnings') ?? 0;
  const pageCounts: HeaderCount[] = [
    { label: 'EVENTS HELD', value: allEvents.length },
    { label: 'FAILURES', value: failures, tone: failures ? 'var(--lys-status-danger)' : undefined },
    { label: 'WARNINGS', value: warnings, tone: warnings ? 'var(--lys-status-warning)' : undefined },
    { label: 'STREAM', value: connectionStatus === 'CONNECTED' ? 'live' : connectionStatus.toLowerCase(), tone: connectionStatus === 'CONNECTED' ? 'var(--lys-status-success)' : 'var(--lys-status-warning)' }
  ];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader title="Events" subtitle="Runtime log · live bus buffer, newest first · click a row for its payload" counts={pageCounts} />

      <div className="flex-1 p-6 flex flex-col">
        <Card label="Event log" className="h-full">
          <div className="flex flex-col">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-lys-subtle">
              <div className="flex flex-col gap-2 min-w-0">
                <FilterPills label="Filter events by category" options={categoryOptions} value={category} onChange={(id) => setCategory(id as 'ALL' | EventCategory)} />
                <FilterPills label="Filter events by source" options={sourceOptions} value={source} onChange={setSource} />
              </div>
              <span className="text-[12px] text-lys-faint">{visible.length} of {allEvents.length} shown</span>
            </div>

            <div className="flex items-center gap-4 px-5 py-2 border-b border-lys-subtle text-[10px] tracking-wider uppercase text-lys-faint bg-lys-surface-0">
              <span className="w-28 shrink-0">Time (local)</span>
              <span className="w-6 shrink-0">Sev</span>
              <span className="w-28 shrink-0">Source</span>
              <span className="w-40 shrink-0">Kind</span>
              <span className="flex-1 min-w-[160px]">Detail</span>
              <span className="w-28 shrink-0 text-right">Job</span>
            </div>

            <div ref={listRef} role="log" aria-live="polite" aria-relevant="additions text" aria-label="Events" className="flex flex-col">
              {visible.length === 0 && (
                <EmptyState art={HERMES_ART}>{allEvents.length === 0 ? 'No events received yet. The log fills as Hermes emits them.' : 'No events match these filters.'}</EmptyState>
              )}
              {visible.map((e) => {
                const severity = eventSeverity(e.kind);
                const isOpen = expanded === e.id;
                return (
                  <div key={e.id} className="border-b border-lys-subtle last:border-b-0">
                    <button
                      type="button"
                      data-nav-item
                      aria-expanded={isOpen}
                      onClick={() => setExpanded(isOpen ? null : e.id)}
                      className="w-full flex items-center gap-4 px-5 py-2 text-[12px] text-left hover:bg-lys-surface-2 cursor-pointer"
                      style={{ backgroundColor: severity === 'error' ? 'color-mix(in srgb, var(--lys-status-danger) 7%, transparent)' : severity === 'warn' ? 'color-mix(in srgb, var(--lys-status-warning) 5%, transparent)' : undefined }}
                    >
                      <span className="w-28 shrink-0 font-mono-code text-lys-faint">{eventTime(e)}</span>
                      <span className="w-6 shrink-0" aria-label={`severity ${severity}`} title={severity}>
                        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: SEVERITY_COLOR[severity] }} />
                      </span>
                      <span className="w-28 shrink-0 font-semibold truncate" style={{ color: e.source.accentColor || 'var(--lys-text-muted)' }}>
                        {e.source.displayName}
                      </span>
                      <span className="w-40 shrink-0 font-medium truncate" style={{ color: eventKindColor(e.kind) }}>{e.kind}</span>
                      <span className="flex-1 min-w-[160px] text-lys-secondary truncate">{e.detail}</span>
                      <span className="w-28 shrink-0 text-right font-mono-code text-lys-gold truncate">{e.jobId || UNKNOWN_TIME}</span>
                    </button>

                    {isOpen && (
                      <div className="px-5 pb-4 pt-1 bg-lys-surface-0 flex flex-col gap-2">
                        <div className="flex flex-wrap items-center gap-4 text-[12px] text-lys-muted">
                          <span>id <CopyId value={e.id} /></span>
                          {e.jobId && <span>job <button type="button" onClick={() => setActiveModalJobId(e.jobId!)} className="text-lys-gold underline cursor-pointer font-mono-code">{e.jobId}</button></span>}
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
          </div>
        </Card>
      </div>
    </div>
  );
};

export default EventsRoute;
