import React from 'react';
import type { ActorRef } from '../../api/types';
import { cardState, type CardState } from './floorLayout';
import { formatDuration, phaseLabel, type TimelineRow } from '../jobs/runTimeline';

const STATE_LABEL: Record<CardState, string> = {
  running: 'Running',
  failed: 'Failed',
  done: 'Done',
  queued: 'Queued'
};

const STATE_COLOR: Record<CardState, string> = {
  running: 'var(--lys-status-success)',
  failed: 'var(--lys-status-danger)',
  done: 'var(--lys-text-muted)',
  queued: 'var(--lys-text-faint)'
};

export interface FloorCardProps {
  row: TimelineRow;
  /** Resolved presentation of the phase's agent; undefined when the phase has no agent yet. */
  actor?: ActorRef;
  /** Latest event line for this phase, if the console store has one. */
  latestEvent?: string;
  /** Current epoch ms, passed down so every card ticks from one clock. */
  nowMs: number;
}

/**
 * Read-only card for one phase on the floor. Shows the role, the agent's initial in its accent colour,
 * status, elapsed time and the latest event line. It has no actions: the floor only reports.
 */
export const FloorCard: React.FC<FloorCardProps> = ({ row, actor, latestEvent, nowMs }) => {
  const elapsedMs = row.startMs === null ? null : Math.max(0, (row.endMs ?? nowMs) - row.startMs);
  const state = cardState(row.state, elapsedMs);
  const role = row.role || phaseLabel(row.name);
  const mark = actor?.displayName?.trim().charAt(0).toUpperCase() || '?';

  return (
    <article
      aria-label={`${role} · ${STATE_LABEL[state]}`}
      title={row.name}
      className="flex flex-col gap-2 p-3 bg-lys-surface-2 border-l-2"
      style={{ borderLeftColor: actor?.accentColor ?? 'var(--lys-border-subtle)' }}
    >
      <div className="flex items-center justify-between gap-2 min-w-0">
        <span className="text-[10px] tracking-wider uppercase text-lys-faint truncate">{role}</span>
        <span style={{ color: STATE_COLOR[state] }} className="text-[11px] shrink-0">{STATE_LABEL[state]}</span>
      </div>

      <div className="flex items-center gap-2 min-w-0">
        <span
          aria-hidden="true"
          style={{ color: actor?.accentColor, borderColor: actor?.accentColor }}
          className="inline-flex items-center justify-center w-6 h-6 border text-[12px] font-semibold shrink-0"
        >
          {mark}
        </span>
        <span className="text-[13px] text-lys-primary truncate" title={actor?.displayName}>
          {actor?.displayName || row.agentId || '—'}
        </span>
      </div>

      <div className="flex items-center justify-between gap-2 text-[11px] text-lys-muted">
        <span className="font-mono-code">{elapsedMs === null ? '—' : formatDuration(elapsedMs)}</span>
      </div>

      <div className="text-[12px] text-lys-muted truncate" title={latestEvent}>
        {latestEvent || 'No events yet'}
      </div>
    </article>
  );
};
