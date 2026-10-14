import React, { useMemo } from 'react';
import { ExecutionBackendStrip } from '../features/execution/ExecutionBackendStrip';
import { ExecutionResourceCard } from '../features/execution/ExecutionResourceCard';
import { ExecutionTimeline } from '../features/execution/ExecutionTimeline';
import { executionTimeline, groupByBackend } from '../features/execution/executionFormat';
import { useNow } from '../features/execution/useNow';
import { useExecution } from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { isRealApiMode } from '../api/client';

export const ExecutionRoute: React.FC = () => {
  const { view, snapshotStatus, snapshotError, snapshotLoadedAt, refresh } = useExecution();
  const allEvents = useConsoleStore((s) => s.allEvents);
  const nowMs = useNow(1000);

  const backendNames = view.backends.map((b) => b.name);
  const resources = useMemo(() => Object.values(view.resources), [view.resources]);
  const groups = useMemo(() => groupByBackend(resources, backendNames), [resources, backendNames]);
  const timeline = useMemo(() => executionTimeline(allEvents), [allEvents]);
  const loaded = snapshotStatus === 'ready';

  return (
    <div className="flex flex-col pb-10 select-none bg-[#0A0B0D]">
      {!isRealApiMode && (
        <div className="px-5 py-2 border-b border-[#3A2F12] bg-[rgba(227,160,8,0.06)] font-mono-code text-[11px] text-[#E3A008]">
          MOCK FIXTURES · not live Hermes data. Start the Hermes runtime API to see real execution state.
        </div>
      )}

      {/* Backend status strip */}
      <section className="p-5 border-b border-[#1F242B] bg-[#0C0E11]">
        <div className="flex items-center justify-between gap-3 mb-3 font-mono-code text-[11px]">
          <span className="tracking-wider text-[#5C646E]">BACKENDS · SNAPSHOT</span>
          <span className="flex items-center gap-3 text-[#5C646E]">
            {snapshotStatus === 'error' && (
              <span className="text-[#F2555A]" title={snapshotError ?? undefined}>
                snapshot failed · showing last known state
              </span>
            )}
            {snapshotLoadedAt && <span>loaded {snapshotLoadedAt.slice(11, 19)}</span>}
            <button
              onClick={() => void refresh()}
              className="text-[#8C949F] hover:text-[#E6E9ED] cursor-pointer border border-[#1F242B] hover:border-[#3A4048] px-2 py-0.5"
            >
              ↻ refresh
            </button>
          </span>
        </div>
        <ExecutionBackendStrip backends={view.backends} openrig={view.openrig} loaded={loaded} />
      </section>

      {/* Live resources grouped by backend */}
      <section className="p-5 border-b border-[#1F242B]">
        <div className="font-mono-code text-[11px] tracking-wider text-[#5C646E] mb-3.5">
          LIVE RESOURCES · {resources.length} · BY BACKEND
        </div>
        {groups.length === 0 ? (
          <div className="font-mono-code text-[11px] text-[#5C646E]">
            {loaded ? 'No live execution resources.' : 'Waiting for the execution snapshot…'}
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {groups.map((g) => (
              <div key={g.backend}>
                <div className="flex items-center gap-2.5 mb-2 font-mono-code text-[11px]">
                  <span className="text-[#E6E9ED] font-semibold tracking-wider uppercase">{g.backend}</span>
                  <span className="text-[#5C646E]">{g.resources.length} resource{g.resources.length === 1 ? '' : 's'}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {g.resources.map((r) => (
                    <ExecutionResourceCard key={`${r.backend}|${r.kind}|${r.id}`} resource={r} nowMs={nowMs} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Recent execution timeline */}
      <section className="p-5">
        <div className="flex items-center justify-between mb-3.5 font-mono-code text-[11px]">
          <span className="tracking-wider text-[#5C646E]">RECENT EXECUTION TIMELINE</span>
          <span className="text-[#5C646E]">{timeline.length} events</span>
        </div>
        <ExecutionTimeline events={timeline} />
      </section>
    </div>
  );
};

export default ExecutionRoute;
