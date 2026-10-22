import React, { useMemo } from 'react';
import { ExecutionTimeline } from '../features/execution/ExecutionTimeline';
import { executionTimeline } from '../features/execution/executionFormat';
import { useExecution } from '../api/hooks';
import { useConsoleStore } from '../stores/useConsoleStore';
import { isRealApiMode } from '../api/client';
import { Card } from '../components/Card';
import { EmptyState, ErrorState, LoadingState } from '../components/DataStates';
import { PageHeader, HeaderCount } from '../components/PageHeader';

export const ExecutionRoute: React.FC = () => {
  const { view, snapshotStatus, snapshotError, snapshotLoadedAt, refresh } = useExecution();
  const allEvents = useConsoleStore((s) => s.allEvents);

  const timeline = useMemo(() => executionTimeline(allEvents), [allEvents]);
  const loaded = snapshotStatus === 'ready';
  const available = view.backends.filter((b) => b.available).length;

  const counts: HeaderCount[] = loaded
    ? [{ label: 'BACKENDS AVAILABLE', value: `${available}/${view.backends.length}`, tone: available === view.backends.length ? undefined : 'var(--lys-status-warning)' }]
    : [];

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader
        updatedAt={snapshotLoadedAt ? Date.parse(snapshotLoadedAt) : null}
        title="Execution"
        subtitle="Backends"
        counts={counts}
        actions={
          <button onClick={() => void refresh()} className="text-[12px] px-3 py-1.5 border border-lys-default text-lys-muted hover:text-lys-primary cursor-pointer transition-colors">
            Refresh
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

        <section aria-label="Backends" className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {!loaded && snapshotStatus !== 'error' && (
            <Card className="md:col-span-3">
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
                    <span className="text-[10px] font-mono-code uppercase" style={{ color: tone }}>
                      {b.available ? 'available' : 'unavailable'}
                    </span>
                  </div>
                  <p className="text-[12px] text-lys-muted truncate" title={b.detail || 'no detail reported'}>{b.detail || 'no detail reported'}</p>
                </div>
              </Card>
            );
          })}
        </section>

        <Card label="Recent execution timeline">
          <div className="p-5 flex flex-col gap-3">
            <div className="flex items-center justify-between text-[11px] font-medium tracking-wider uppercase text-lys-faint">
              <span>Recent execution timeline</span>
              <span>{timeline.length} events</span>
            </div>
            {timeline.length === 0 ? <EmptyState>No execution events</EmptyState> : <ExecutionTimeline events={timeline} />}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default ExecutionRoute;
