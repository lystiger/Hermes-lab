import React, { useEffect, useMemo, useRef, useState } from 'react';
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
import { traceSourceName } from '../api/actors';

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

  // Live events arrive at the top. When the operator has scrolled away, the list stays where it is: it is frozen to
  // the events shown at that moment and new arrivals are counted in a pill instead of moving the page (M7).
  const anchorRef = useRef<HTMLDivElement>(null);
  const [atTop, setAtTop] = useState(true);
  const [frozen, setFrozen] = useState<Set<string> | null>(null);
  useEffect(() => {
    const scroller = anchorRef.current?.closest('.lys-scroll') as HTMLElement | null;
    if (!scroller) return;
    const onScroll = () => setAtTop(scroller.scrollTop <= 24);
    onScroll();
    scroller.addEventListener('scroll', onScroll, { passive: true });
    return () => scroller.removeEventListener('scroll', onScroll);
  }, []);
  useEffect(() => {
    if (atTop) {
      setFrozen(null);
    } else {
      setFrozen((prev) => prev ?? new Set(allEvents.map((e) => e.id)));
    }
    // Freeze at the moment the user leaves the top; later arrivals are counted, not shown.
  }, [atTop]);
  const jumpToTop = () => {
    (anchorRef.current?.closest('.lys-scroll') as HTMLElement | null)?.scrollTo({ top: 0 });
  };

  const counts = useMemo(() => {
    const byCategory = new Map<string, number>();
    const bySource = new Map<string, number>();
    for (const e of allEvents) {
      const c = eventCategory(e.kind);
      byCategory.set(c, (byCategory.get(c) ?? 0) + 1);
      bySource.set(traceSourceName(e.source), (bySource.get(traceSourceName(e.source)) ?? 0) + 1);
    }
    return { byCategory, bySource };
  }, [allEvents]);

  const visible = allEvents.filter(
    (e) =>
      (category === 'ALL' || eventCategory(e.kind) === category) &&
      (source === 'ALL' || traceSourceName(e.source) === source)
  );

  const shown = frozen ? visible.filter((e) => frozen.has(e.id)) : visible;
  const newCount = frozen ? visible.filter((e) => !frozen.has(e.id)).length : 0;

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
      <PageHeader
        updatedAt={allEvents[0] ? allEvents[0].rawTs * 1000 : null}
        title="Events"
        subtitle="Live bus buffer"
        counts={pageCounts}
      />

      <div ref={anchorRef} className="flex-1 p-6 flex flex-col">
        <Card label="Event log" className="h-full">
          <div className="flex flex-col">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-lys-subtle">
              <div className="flex flex-wrap items-center gap-3 min-w-0">
                <FilterPills label="Filter events by category" options={categoryOptions} value={category} onChange={(id) => setCategory(id as 'ALL' | EventCategory)} />
                <div className="h-4 w-px bg-lys-subtle hidden lg:block" />
                <FilterPills label="Filter events by source" options={sourceOptions} value={source} onChange={setSource} />
              </div>
              <span className="text-[12px] text-lys-faint whitespace-nowrap">{shown.length} of {allEvents.length} shown</span>
            </div>

            <div className="hidden sm:grid grid-cols-[80px_16px_110px_120px_minmax(0,1fr)_120px] items-center gap-3 px-5 py-2 border-b border-lys-subtle text-[10px] font-medium tracking-wider uppercase text-lys-faint bg-lys-surface-0 select-none">
              <span>Time</span>
              <span>Sev</span>
              <span>Source</span>
              <span>Kind</span>
              <span>Detail</span>
              <span className="text-right">Job / Run</span>
            </div>

            <div ref={listRef} role="log" aria-live="polite" aria-relevant="additions text" aria-label="Events" className="flex flex-col">
              {shown.length === 0 && (
                <EmptyState art={HERMES_ART}>{allEvents.length === 0 ? 'No events' : 'No matching events'}</EmptyState>
              )}
              {shown.map((e) => {
                const severity = eventSeverity(e.kind);
                const isOpen = expanded === e.id;
                return (
                  <div key={e.id} className="border-b border-lys-subtle last:border-b-0">
                    <button
                      type="button"
                      data-nav-item
                      aria-expanded={isOpen}
                      onClick={() => setExpanded(isOpen ? null : e.id)}
                      className="w-full grid grid-cols-[80px_16px_110px_120px_minmax(0,1fr)_120px] items-center gap-3 px-5 py-2 text-[12px] text-left hover:bg-lys-surface-2 cursor-pointer transition-colors"
                      style={{ backgroundColor: severity === 'error' ? 'color-mix(in srgb, var(--lys-status-danger) 7%, transparent)' : severity === 'warn' ? 'color-mix(in srgb, var(--lys-status-warning) 5%, transparent)' : undefined }}
                    >
                      <span className="font-mono-code text-lys-faint whitespace-nowrap text-[11px]">{eventTime(e)}</span>
                      <span className="flex items-center justify-center" aria-label={`severity ${severity}`} title={severity}>
                        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: SEVERITY_COLOR[severity] }} />
                      </span>
                      <span className="font-semibold truncate text-[12px]" title={traceSourceName(e.source)} style={{ color: e.source.accentColor || 'var(--lys-text-muted)' }}>
                        {traceSourceName(e.source)}
                      </span>
                      <span className="font-mono-code text-[11px] truncate" title={e.kind} style={{ color: eventKindColor(e.kind) }}>
                        {e.kind}
                      </span>
                      <span className="text-lys-secondary truncate min-w-0" title={e.detail}>{e.detail}</span>
                      <span className="font-mono-code text-[11px] text-lys-faint truncate text-right" title={e.jobId || e.runId || undefined}>
                        {e.jobId ? e.jobId : e.runId ? e.runId : ''}
                      </span>
                    </button>

                    {isOpen && (
                      <div className="px-5 pb-4 pt-2 bg-lys-surface-0 border-t border-lys-subtle flex flex-col gap-2">
                        <div className="flex flex-wrap items-center gap-4 text-[12px] text-lys-muted">
                          <span>id <CopyId value={e.id} truncate /></span>
                          {e.jobId && <span>job <button type="button" onClick={() => setActiveModalJobId(e.jobId!)} className="text-lys-gold underline cursor-pointer font-mono-code">{e.jobId}</button></span>}
                          {e.runId && <span>run <CopyId value={e.runId} truncate /></span>}
                          {e.taskId && <span>task <CopyId value={e.taskId} truncate /></span>}
                          {e.actorId && <span>actor <CopyId value={e.actorId} truncate /></span>}
                        </div>
                        <pre className="font-mono-code text-[11px] text-lys-secondary bg-lys-base border border-lys-subtle p-3 overflow-x-auto rounded-sm">
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
        {newCount > 0 && (
          <div className="sticky bottom-4 z-10 mt-3 flex justify-center pointer-events-none">
            <button
              type="button"
              onClick={jumpToTop}
              className="pointer-events-auto inline-flex items-center gap-2 px-3 py-1.5 bg-lys-surface-2 border border-lys-gold text-[12px] text-lys-primary cursor-pointer hover:bg-lys-surface-interactive"
            >
              {newCount} new {newCount === 1 ? 'event' : 'events'} · back to newest
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default EventsRoute;
