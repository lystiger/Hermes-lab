import React, { useMemo } from 'react';
import { ExecutionResourceCard } from '../features/execution/ExecutionResourceCard';
import { ExecutionTimeline } from '../features/execution/ExecutionTimeline';
import { executionTimeline, groupByBackend, stateStyle } from '../features/execution/executionFormat';
import { useNow } from '../features/execution/useNow';
import { useExecution } from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { formatTimeOfDay } from '../features/time/format';
import { isRealApiMode } from '../api/client';
import { Card } from '../components/Card';
import { CopyId } from '../components/CopyId';
import { EmptyState, ErrorState, LoadingState } from '../components/DataStates';
import { PageHeader, HeaderCount } from '../components/PageHeader';
import { NotReported, NotReportedItem } from '../components/NotReported';
import { HERMES_ART } from '../theme/agentArt';

const NOT_REPORTED: NotReportedItem[] = [
  { label: 'seat memory', reason: 'The execution snapshot carries no memory or compute figures' },
  { label: 'seat output', reason: 'Hermes does not stream stdout from seats into this console' },
  { label: 'seat heartbeat', reason: 'No heartbeat latency is measured by the snapshot' }
];

export const ExecutionRoute: React.FC = () => {
  const { view, snapshotStatus, snapshotError, snapshotLoadedAt, refresh } = useExecution();
  const allEvents = useConsoleStore((s) => s.allEvents);
  const nowMs = useNow(1000);

  const backendNames = view.backends.map((b) => b.name);
  const resources = useMemo(() => Object.values(view.resources), [view.resources]);
  const groups = useMemo(() => groupByBackend(resources, backendNames), [resources, backendNames]);
  const timeline = useMemo(() => executionTimeline(allEvents), [allEvents]);
  const loaded = snapshotStatus === 'ready';
  const active = resources.filter((r) => r.state === 'acquiring' || r.state === 'running').length;
  const available = view.backends.filter((b) => b.available).length;

  const counts: HeaderCount[] = loaded
    ? [
        { label: 'DEPLOYED SEATS', value: resources.length },
        { label: 'ACTIVE', value: active, tone: active ? 'var(--lys-status-success)' : undefined },
        { label: 'BACKENDS AVAILABLE', value: `${available}/${view.backends.length}`, tone: available === view.backends.length ? undefined : 'var(--lys-status-warning)' }
      ]
    : [];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader
        title="Execution"
        subtitle={
          <span>
            Backends and deployed seats from the execution snapshot
            {snapshotLoadedAt && <> · loaded <span className="font-mono-code">{formatTimeOfDay(snapshotLoadedAt)}</span></>}
          </span>
        }
        counts={counts}
        actions={
          <button onClick={() => void refresh()} className="text-[12px] px-3 py-1.5 border border-lys-default text-lys-muted hover:text-lys-primary cursor-pointer">
            refresh
          </button>
        }
      />

      {!isRealApiMode && (
        <div className="px-6 py-2 bg-lys-warning/12 border-b border-lys-warning/25 text-[12px] text-lys-warning">
          MOCK FIXTURES · not live Hermes data. Start the Hermes runtime API to see real execution state.
        </div>
      )}

      <div className="flex-1 flex flex-col gap-6 p-6">
        {snapshotStatus === 'error' && (
          <Card>
            <ErrorState label="Execution snapshot" error={snapshotError ? new Error(snapshotError) : null} onRetry={() => void refresh()} />
          </Card>
        )}

        <section aria-label="Backends" className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {!loaded && snapshotStatus !== 'error' && (
            <Card className="md:col-span-2 xl:col-span-4">
              <LoadingState label="Waiting for the execution snapshot…" />
            </Card>
          )}
          {view.backends.map((b) => {
            const tone = b.available ? 'var(--lys-status-success)' : 'var(--lys-status-danger)';
            return (
              <Card key={b.name} accent={tone} label={`Backend ${b.name}`}>
                <div className="p-5 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="font-display text-[20px] font-semibold text-lys-primary">{b.name}</span>
                    <span className="text-[10px] tracking-wider uppercase" style={{ color: tone }}>
                      {b.available ? 'available' : 'unavailable'}
                    </span>
                  </div>
                  <p className="text-[12px] text-lys-muted break-words">{b.detail || 'no detail reported'}</p>
                </div>
              </Card>
            );
          })}
        </section>

        <section aria-label="Deployed seats" className="flex flex-col gap-4">
          <div className="text-[11px] tracking-wider uppercase text-lys-faint">Deployed seats · by backend</div>
          {groups.length === 0 ? (
            <Card>
              <EmptyState art={HERMES_ART}>
                {loaded ? 'No deployed seats. Hermes reports no live execution resources right now.' : 'Waiting for the execution snapshot…'}
              </EmptyState>
            </Card>
          ) : (
            groups.map((g) => (
              <div key={g.backend} className="flex flex-col gap-3">
                <div className="flex items-center gap-3 text-[13px]">
                  <span className="font-semibold text-lys-primary">{g.backend}</span>
                  <span className="text-lys-faint">{g.resources.length} seat{g.resources.length === 1 ? '' : 's'}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                  {g.resources.map((r, idx) => (
                    <Card key={`${r.backend}|${r.kind}|${r.id}`} accent={stateStyle(r.state).color} label={`Seat ${r.id}`}>
                      <ExecutionResourceCard resource={r} nowMs={nowMs} seat={idx + 1} />
                    </Card>
                  ))}
                </div>
              </div>
            ))
          )}
        </section>

        <Card label="Recent execution timeline">
          <div className="p-5 flex flex-col gap-3">
            <div className="flex items-center justify-between text-[11px] tracking-wider uppercase text-lys-faint">
              <span>Recent execution timeline</span>
              <span>{timeline.length} events</span>
            </div>
            {timeline.length === 0 ? <EmptyState>No execution events recorded yet.</EmptyState> : <ExecutionTimeline events={timeline} />}
          </div>
        </Card>

        <NotReported items={NOT_REPORTED} />
        <span className="sr-only"><CopyId value="" /></span>
      </div>
    </div>
  );
};

export default ExecutionRoute;
