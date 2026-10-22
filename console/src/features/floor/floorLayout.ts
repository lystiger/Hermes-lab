import type { TraceEvent } from '../../api/types';
import type { TimelineRow } from '../jobs/runTimeline';

/** A timeline row plus the keys of the phases it waits on. Dependency keys match `TimelineRow.key`. */
export interface FloorPhase extends TimelineRow {
  dependencies?: string[];
}

export type FloorCardState = 'running' | 'failed' | 'done' | 'queued' | 'other';

export interface FloorCard {
  state: FloorCardState;
  /** Epoch ms from start to end (or `nowMs` while not ended); null when the phase never started. */
  elapsedMs: number | null;
}

/** A dependency is finished once it no longer holds anything back. */
function isFinished(row: TimelineRow): boolean {
  return row.state === 'COMPLETED' || row.state === 'SKIPPED' || row.superseded === true;
}

/**
 * Lays phases out in columns. A phase with no unfinished dependencies sits in the lowest column;
 * any other phase sits one column right of its latest unfinished dependency. Finished dependencies
 * do not push a phase right. Rows keep spec order within a column. A dependency cycle is broken
 * at the edge that closes it, so layout always terminates.
 */
export function floorLevels(phases: FloorPhase[]): FloorPhase[][] {
  const ordered = [...phases].sort((a, b) => a.order - b.order);
  const byKey = new Map(ordered.map((p) => [p.key, p]));
  const levelByKey = new Map<string, number>();
  const visiting = new Set<string>();

  const unfinishedDeps = (p: FloorPhase): FloorPhase[] =>
    (p.dependencies ?? [])
      .map((k) => byKey.get(k))
      .filter((d): d is FloorPhase => d !== undefined && d.key !== p.key && !isFinished(d));

  const levelOf = (p: FloorPhase): number => {
    const cached = levelByKey.get(p.key);
    if (cached !== undefined) return cached;
    visiting.add(p.key);
    let level = 0;
    for (const dep of unfinishedDeps(p)) {
      if (visiting.has(dep.key)) continue; // cycle: ignore the closing edge
      level = Math.max(level, levelOf(dep) + 1);
    }
    visiting.delete(p.key);
    levelByKey.set(p.key, level);
    return level;
  };

  const columns: FloorPhase[][] = [];
  for (const p of ordered) {
    const level = levelOf(p);
    (columns[level] ??= []).push(p);
  }
  return columns;
}

/**
 * Card state for one phase. `FAILED` is failed; `RUNNING` and `CLAIMED` (preparing) are running;
 * `COMPLETED` is done; `QUEUED` and `BLOCKED` are queued. Anything else is other. An UNKNOWN phase
 * whose latest event reads as a failure is shown as failed.
 */
export function floorCardState(
  row: Pick<TimelineRow, 'state' | 'startMs' | 'endMs'>,
  latestEvent: Pick<TraceEvent, 'kind'> | null | undefined,
  nowMs: number
): FloorCard {
  return {
    state: cardStateOf(row.state, latestEvent),
    elapsedMs: elapsedOf(row, nowMs)
  };
}

function cardStateOf(state: TimelineRow['state'], latestEvent: Pick<TraceEvent, 'kind'> | null | undefined): FloorCardState {
  switch (state) {
    case 'FAILED': return 'failed';
    case 'RUNNING':
    case 'CLAIMED': return 'running';
    case 'COMPLETED': return 'done';
    case 'QUEUED':
    case 'BLOCKED': return 'queued';
    case 'UNKNOWN':
      return latestEvent && /fail/i.test(latestEvent.kind) ? 'failed' : 'other';
    default: return 'other';
  }
}

function elapsedOf(row: Pick<TimelineRow, 'startMs' | 'endMs'>, nowMs: number): number | null {
  if (row.startMs === null) return null;
  const end = row.endMs ?? nowMs;
  return Math.max(0, end - row.startMs);
}
