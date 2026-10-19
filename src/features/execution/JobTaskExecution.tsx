import React from 'react';
import { Link } from 'react-router-dom';
import { TraceEvent } from '../../api/types';
import { Badge } from '../../components/Badge';
import { useConsoleStore } from '../../stores/useConsoleStore';
import { useExecutionStore } from '../../stores/useExecutionStore';
import { resourceKey } from '../../stores/executionReducer';
import { stateStyle } from './executionFormat';

interface JobTaskExecutionProps {
  events: TraceEvent[];
}

/**
 * Per-task backend and resource badges for a job, derived from `execution.*` events grouped by taskId.
 * Each badge links to the Execution page.
 */
export const JobTaskExecution: React.FC<JobTaskExecutionProps> = ({ events }) => {
  const setActiveModalJobId = useConsoleStore((s) => s.setActiveModalJobId);
  const resources = useExecutionStore((s) => s.view.resources);

  // Latest execution event per taskId (newest rawTs wins).
  const latestByTask = new Map<string, TraceEvent>();
  for (const e of events) {
    if (!e.kind.startsWith('execution.') || !e.taskId) continue;
    const current = latestByTask.get(e.taskId);
    if (!current || e.rawTs >= current.rawTs) latestByTask.set(e.taskId, e);
  }
  const rows = [...latestByTask.entries()].sort((a, b) => b[1].rawTs - a[1].rawTs);

  return (
    <div>
      <div className="font-sans text-[11px] tracking-wider text-lys-faint mb-2.5">TASK EXECUTION · BACKENDS</div>
      {rows.length === 0 ? (
        <div className="py-2 font-sans text-[11px] text-lys-faint">No backend execution recorded for this job yet.</div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {rows.map(([taskId, evt]) => {
            const meta = (evt.metadata ?? {}) as Record<string, any>;
            const backend: string = meta.backend ?? evt.source.id;
            const resource = meta.resource as { kind: string; id: string; label: string } | undefined;
            const candidate = resource ? resources[resourceKey(backend, resource.kind, resource.id)] : undefined;
            // A warm-reused seat now belongs to a later task: only borrow its live state while it is
            // still this task's execution, otherwise the earlier task would show the later one's state.
            const live =
              candidate && (candidate.executionId === meta.executionId || (!meta.executionId && candidate.taskId === taskId))
                ? candidate
                : undefined;
            const state = live?.state ?? evt.kind.replace('execution.', '');
            const style = stateStyle(state);
            const reused = meta.reused === true || (live?.details?.reused === true);

            return (
              <Link
                key={taskId}
                to="/execution"
                onClick={() => setActiveModalJobId(null)}
                data-testid="job-task-execution"
                className="flex flex-wrap items-center gap-2 px-2.5 py-2 bg-lys-surface-0 border border-lys-subtle hover:border-lys-strong font-sans text-[11px] text-lys-muted transition-colors"
              >
                <span className="text-lys-faint">{taskId}</span>
                <Badge label={backend} color="var(--lys-accent-sky)" />
                <span className="text-lys-primary">{resource ? resource.label : '—'}</span>
                {reused && <Badge label="reused" color="var(--lys-accent-sky)" />}
                <Badge label={state.replace(/_/g, ' ')} color={style.color} />
                <span className="ml-auto text-lys-gold">open execution →</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};
