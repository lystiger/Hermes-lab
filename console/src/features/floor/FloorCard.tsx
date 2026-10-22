import React from 'react';
import type { ActorRef } from '../../api/types';
import { cardState, type CardState } from './floorLayout';
import { formatCost, type TaskInsight } from './floorInsights';
import { formatDuration, phaseLabel, type TimelineRow } from '../jobs/runTimeline';

const STATE_LABEL: Record<CardState, string> = {
  running: 'Running',
  failed: 'Failed',
  done: 'Done',
  queued: 'Queued',
  replaced: 'Replaced'
};

const STATE_COLOR: Record<CardState, string> = {
  running: 'var(--lys-status-success)',
  failed: 'var(--lys-status-danger)',
  done: 'var(--lys-text-muted)',
  queued: 'var(--lys-text-faint)',
  replaced: 'var(--lys-status-warning)'
};

/** Findings shown on a card before the rest collapse into "+N more" (all of them stay in the tooltip). */
const VISIBLE_FINDINGS = 3;

export interface FloorCardProps {
  row: TimelineRow;
  /** Resolved presentation of the phase's agent; undefined when the phase has no agent yet. */
  actor?: ActorRef;
  /** Repair chain, findings and cost for this phase's task; undefined when Hermes reported no task record. */
  insight?: TaskInsight;
  /** Latest event line for this phase, if the console store has one. */
  latestEvent?: string;
  /** Current epoch ms, passed down so every card ticks from one clock. */
  nowMs: number;
}

/**
 * Read-only card for one phase on the floor: role, agent, status, elapsed time, cost and the latest event.
 * A check that failed or was replaced also shows the findings it reported, so the repair chain is readable.
 */
export const FloorCard: React.FC<FloorCardProps> = ({ row, actor, insight, latestEvent, nowMs }) => {
  const elapsedMs = row.startMs === null ? null : Math.max(0, (row.endMs ?? nowMs) - row.startMs);
  const state = cardState(row.state, elapsedMs);
  const role = row.role || phaseLabel(row.name);
  const mark = actor?.displayName?.trim().charAt(0).toUpperCase() || '?';
  const cost = insight ? formatCost(insight.costUsd, insight.totalTokens) : null;
  const showFindings = Boolean(insight?.findings.length) && (state === 'failed' || state === 'replaced');
  const chainLabel = insight?.kind ? `${insight.kind === 'repair' ? 'Repair' : 'Re-check'} ${insight.cycle ?? ''}`.trim() : null;

  return (
    <article
      aria-label={`${role} · ${STATE_LABEL[state]}${chainLabel ? ` · ${chainLabel}` : ''}`}
      title={row.name}
      className={`flex flex-col gap-2 p-3 bg-lys-surface-2 border-l-2 ${state === 'replaced' ? 'opacity-60' : ''}`}
      style={{ borderLeftColor: state === 'failed' ? 'var(--lys-status-danger)' : actor?.accentColor ?? 'var(--lys-border-subtle)' }}
    >
      <div className="flex items-center justify-between gap-2 min-w-0">
        <span className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] tracking-wider uppercase text-lys-faint truncate">{role}</span>
          {chainLabel && (
            <span className="text-[10px] tracking-wider uppercase px-1 border border-lys-subtle text-lys-muted shrink-0">{chainLabel}</span>
          )}
        </span>
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
        {cost && <span className="font-mono-code truncate" title="Reported by the agent for every run of this task">{cost}</span>}
      </div>

      {showFindings && insight ? (
        <FindingList findings={insight.findings} summary={insight.summary} />
      ) : (
        <div className="text-[12px] text-lys-muted truncate" title={latestEvent}>
          {latestEvent || 'No events yet'}
        </div>
      )}

      {state === 'replaced' && insight?.supersededBy && (
        <div className="text-[11px] text-lys-faint truncate" title={insight.supersededBy}>Replaced by {insight.supersededBy}</div>
      )}
    </article>
  );
};

const FindingList: React.FC<{ findings: string[]; summary: string | null }> = ({ findings, summary }) => {
  const hidden = findings.length - VISIBLE_FINDINGS;
  return (
    <div className="flex flex-col gap-1" title={findings.join('\n')}>
      {summary && <p className="text-[12px] text-lys-primary line-clamp-2">{summary}</p>}
      <ul aria-label="Findings" className="flex flex-col gap-1">
        {findings.slice(0, VISIBLE_FINDINGS).map((finding) => (
          <li key={finding} className="text-[11px] text-lys-muted line-clamp-2">{finding}</li>
        ))}
      </ul>
      {hidden > 0 && <span className="text-[11px] text-lys-faint">+{hidden} more</span>}
    </div>
  );
};
