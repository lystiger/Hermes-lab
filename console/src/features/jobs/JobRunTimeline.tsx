import React from 'react';
import { JobDetail, PipelineStepState } from '../../api/types';
import { useAgents } from '../../api/hooks';
import { resolveActorPresentation } from '../../api/actors';
import { EmptyState } from '../../components/DataStates';
import { useNow } from '../execution/useNow';
import { formatDuration, phaseLabel, timelineRows, timelineWindow } from './runTimeline';

const STATE_LABEL: Record<PipelineStepState, string> = {
  COMPLETED: 'completed',
  RUNNING: 'running',
  QUEUED: 'queued',
  CLAIMED: 'preparing',
  BLOCKED: 'blocked',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
  SKIPPED: 'skipped',
  UNKNOWN: 'unknown status',
  IDLE: 'replaced'
};

interface JobRunTimelineProps {
  job: Pick<JobDetail, 'phases' | 'executionGraph'>;
}

/**
 * Every phase of a job on one time axis, start to finish. A row is a phase and is labelled with its role;
 * the bar shows the agent that ran it. Phases of a parallel group overlap. Nothing is drawn without a reported time.
 */
export const JobRunTimeline: React.FC<JobRunTimelineProps> = ({ job }) => {
  const { agents } = useAgents();
  const nowMs = useNow(1000);
  const rows = timelineRows(job);

  if (rows.length === 0) {
    return <EmptyState>No phases reported for this job yet.</EmptyState>;
  }

  const win = timelineWindow(rows, nowMs);
  const span = win ? win.endMs - win.startMs : 0;
  const pct = (ms: number) => (win ? ((ms - win.startMs) / span) * 100 : 0);

  return (
    <div className="w-full select-none" aria-label="Run timeline">
      <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)] gap-x-3 text-[11px] text-lys-faint mb-1.5">
        <span className="hidden sm:block tracking-wider uppercase">Role · phase</span>
        {win ? (
          <span className="flex justify-between font-mono-code">
            <span>0s</span>
            <span>{formatDuration(span / 2)}</span>
            <span>{formatDuration(span)}</span>
          </span>
        ) : (
          <span>no phase times reported</span>
        )}
      </div>

      <ol className="flex flex-col gap-1.5">
        {rows.map((r) => {
          const actor = r.agentId ? resolveActorPresentation(r.agentId, agents) : null;
          const accent = actor?.accentColor || 'var(--lys-border-strong)';
          const isFailed = r.state === 'FAILED';
          const isRunning = r.state === 'RUNNING' || (r.startMs !== null && r.endMs === null && r.state !== 'COMPLETED');
          const tone = isFailed ? 'var(--lys-status-danger)' : accent;
          const end = r.endMs ?? (r.startMs !== null ? nowMs : null);
          const duration = r.startMs !== null && end !== null ? formatDuration(end - r.startMs) : null;
          const agentName = actor?.displayName || r.agentId || '—';
          const left = r.startMs !== null ? pct(r.startMs) : 0;
          const width = r.startMs !== null && end !== null ? Math.max(pct(end) - left, 1.5) : 0;

          return (
            <li
              key={r.key}
              aria-label={`${r.role ?? 'phase'} · ${r.name} · ${agentName} · ${STATE_LABEL[r.state]}${duration ? ` · ${duration}` : ''}`}
              className={`grid grid-cols-1 sm:grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)] gap-x-3 gap-y-0.5 sm:items-center ${r.superseded ? 'opacity-60' : ''}`}
            >
              <div className="min-w-0 flex items-baseline gap-2 sm:block">
                <div className="text-[10px] tracking-wider uppercase text-lys-faint truncate">{r.role ?? '—'}</div>
                <div title={r.name} className="text-[12px] font-medium text-lys-primary truncate">{phaseLabel(r.name)}</div>
              </div>

              <div className="relative h-8 bg-lys-surface-0 border border-lys-subtle overflow-hidden">
                {r.startMs !== null && win ? (
                  <>
                    <div
                      style={{
                        left: `${left}%`,
                        width: `${Math.min(width, 100 - left)}%`,
                        borderLeftColor: tone,
                        backgroundColor: `color-mix(in srgb, ${tone} ${isRunning ? 26 : 16}%, transparent)`
                      }}
                      className="absolute inset-y-0 border-l-2"
                    />
                    {/* The label sits over the bar and may run past it, so short phases stay readable. */}
                    <div
                      style={left + width > 60 ? { right: `${Math.max(100 - left - width, 0)}%` } : { left: `${left}%` }}
                      className={`absolute inset-y-0 flex items-center gap-1.5 px-2 whitespace-nowrap ${left + width > 60 ? 'flex-row-reverse' : ''}`}
                    >
                      {isRunning && <span style={{ backgroundColor: tone }} className="w-1.5 h-1.5 rounded-full flex-shrink-0" />}
                      <span style={{ color: tone }} className="text-[11px] font-medium">{agentName}</span>
                      <span className="text-[11px] text-lys-faint">{STATE_LABEL[r.state]}{duration ? ` · ${duration}` : ''}{r.commitSha ? ` · ${r.commitSha.slice(0, 7)}` : ''}</span>
                    </div>
                  </>
                ) : (
                  <div className="absolute inset-0 flex items-center gap-1.5 px-2 border border-dashed border-lys-subtle">
                    <span style={{ color: r.state === 'QUEUED' ? 'var(--lys-text-faint)' : tone }} className="text-[11px] truncate">{agentName}</span>
                    <span className="text-[11px] text-lys-faint truncate">{STATE_LABEL[r.state]}</span>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
};
