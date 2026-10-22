import React from 'react';
import { ActorRef } from '../../api/types';
import { Card } from '../../components/Card';
import { UNKNOWN } from '../../api/unknown';
import { FloorCard as FloorCardState, FloorCardState as State, FloorPhase } from './floorLayout';
import { formatDuration, phaseLabel } from '../jobs/runTimeline';

const STATE_LABEL: Record<State, string> = {
  running: 'Running',
  failed: 'Failed',
  done: 'Done',
  queued: 'Queued',
  other: 'Other'
};

const STATE_TONE: Record<State, string> = {
  running: 'var(--lys-status-success)',
  failed: 'var(--lys-status-danger)',
  done: 'var(--lys-text-faint)',
  queued: 'var(--lys-text-muted)',
  other: 'var(--lys-text-muted)'
};

interface FloorCardProps {
  phase: FloorPhase;
  card: FloorCardState;
  /** The agent running the phase, resolved from the registry. Its accent colours the mark. */
  agent: ActorRef | null;
  /** One line of what the phase is doing right now. */
  liveLine: string;
}

/** One phase on the live floor. Read-only: the agent is an initial mark, not an image. */
export const FloorCard: React.FC<FloorCardProps> = ({ phase, card, agent, liveLine }) => {
  const accent = agent?.accentColor;
  const role = phase.role || phaseLabel(phase.name);
  const tone = STATE_TONE[card.state];

  return (
    <Card accent={tone} as="article" label={`${role}, ${STATE_LABEL[card.state]}`} bodyClassName="p-3 flex flex-col gap-2 min-w-0">
      <div className="flex items-start gap-2.5 min-w-0">
        <span
          aria-hidden="true"
          className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full border font-display text-[13px] font-semibold"
          style={{
            color: accent,
            borderColor: accent ? `color-mix(in srgb, ${accent} 40%, transparent)` : undefined,
            background: accent ? `color-mix(in srgb, ${accent} 14%, transparent)` : undefined
          }}
        >
          {agent?.displayName?.charAt(0).toUpperCase() ?? UNKNOWN}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-lys-primary truncate" title={phase.name}>{role}</div>
          <div className="text-[11px] text-lys-muted truncate">{agent?.displayName ?? UNKNOWN}</div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 text-[11px] uppercase tracking-wider">
        <span style={{ color: tone }}>{STATE_LABEL[card.state]}</span>
        <span className="font-mono-code normal-case tracking-normal text-lys-muted">
          {card.elapsedMs === null ? UNKNOWN : formatDuration(card.elapsedMs)}
        </span>
      </div>

      <div className="text-[12px] text-lys-secondary truncate" title={liveLine} aria-live="polite">
        {liveLine}
      </div>
    </Card>
  );
};
